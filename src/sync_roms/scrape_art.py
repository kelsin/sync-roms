"""`sync-roms scrape art`: make the Onion and Spruce box art of the ROMs already scraped into storage."""
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import inventory, s3, scrape_files, scrape_online, scrape_plan, ui, upload

EST_SPRUCE_BYTES = 540_000  # per ROM, all its sizes together; what a dry run reports, not a measurement
EST_ONION_BYTES = 150_000
TARGETS = ("onion", "spruce")
BATCH = 500  # sources downloaded at a time, so a large system never fills the disk


@dataclass
class ArtPlan:
    make: dict = field(default_factory=dict)  # target -> [(ROM stem, source key)]
    have: dict = field(default_factory=dict)  # target -> ROMs that already have its files
    estimate_bytes: dict = field(default_factory=dict)
    no_source: int = 0  # ROMs with media but neither a cover nor a miximage


def plan_art(listing, targets, replace, carts=()):
    """What to make from `listing` ({key: size} of scrapes/<system>/): per target, the ROMs to make and where from.

    A ROM is a candidate with a cover or miximage (the cover is the source); PICO-8 carts (storage keys) are also
    candidates, their own picture being the source. ROMs in subfolders get none: both Imgs folders are flat.
    """
    found, stems = {}, set()
    for key in listing:
        parts = key.split("/")
        if len(parts) != 4 or parts[0] != scrape_plan.SCRAPES:
            continue
        stem = os.path.splitext(parts[3])[0]
        found.setdefault(stem, {})[parts[2]] = key
        if parts[2] in scrape_plan.MEDIA_TYPES:
            stems.add(stem)
    sources = {}
    for stem, types in found.items():
        first = next((t for t in scrape_plan.ONION_ART if t in types), None)
        if first:
            sources[stem] = types[first]
    for cart in carts:
        name = cart.split("/", 1)[-1]
        if "/" not in name and name.endswith(".p8.png") and (stem := os.path.splitext(name)[0]) not in sources:
            sources[stem] = cart
            stems.add(stem)
    plan = ArtPlan(no_source=len(stems - sources.keys()))
    for target in targets:
        kind = scrape_plan.ONION_TYPE if target == "onion" else "spruce"
        have = {s for s in sources if kind in found.get(s, {})}
        plan.have[target] = len(have)
        plan.make[target] = [(s, k) for s, k in sorted(sources.items()) if replace or s not in have]
        plan.estimate_bytes[target] = len(plan.make[target]) * (EST_ONION_BYTES if target == "onion" else EST_SPRUCE_BYTES)
    return plan


def _source_type(key):
    parts = key.split("/")
    return parts[2] if parts[0] == scrape_plan.SCRAPES else "cart"


def _jobs(system, stems, paths, listing, replace, targets):
    """(upload jobs, ROMs whose source can't be read)"""
    jobs, unreadable = [], []
    qoi = scrape_plan.can_make_qoi()
    for stem, key in stems:
        path = paths.get(key)
        size = scrape_files._image_size(path) if qoi and path else None
        if path is None or (qoi and size is None):
            unreadable.append(f"{system}/{stem}")
            continue
        for out_key, src, box in scrape_files.derived_art(system, stem, {_source_type(key): path}, size):
            spruce = f"/{scrape_plan.ONION_TYPE}/" not in out_key
            if ("spruce" if spruce else "onion") in targets and (replace or out_key not in listing):
                jobs.append((out_key, src, os.path.getsize(src), box))
    return jobs, unreadable


def _show_plan(system, plan, targets):
    for target in targets:
        note = "up to 3 per ROM" if target == "spruce" else "1 per ROM"
        print(f"  {system} {target}: {len(plan.make[target])} ROM(s) to make ({note}), {plan.have[target]} already have it")
    if plan.no_source:
        print(ui.dim(f"  {system}: {plan.no_source} ROM(s) have no cover or miximage"))


def art_command(args):
    """args: system (storage folder name or None for all), target (onion, spruce or both), dry_run, replace, workers."""
    which = getattr(args, "target", None) or "both"
    if which not in ("onion", "spruce", "both"):
        ui.fail(f"--for takes onion, spruce or both, not {which!r}", 2)
    targets = TARGETS if which == "both" else (which,)
    if "spruce" in targets and not scrape_plan.can_make_qoi():
        ui.fail("Spruce box art needs Pillow to make QOI images (run with `uv run`, or use --for onion)", 2)
    replace, dry_run = getattr(args, "replace", False), getattr(args, "dry_run", False)
    workers = getattr(args, "workers", None) or os.cpu_count() or 4
    print(ui.bold("🖼️  Make box art") + ui.dim(f"  {', '.join(targets)}"))
    made = skipped = failed = made_here = 0
    total_bytes = 0
    try:
        for system in scrape_online._pick_systems(args.system):
            name = system["bucket"]
            listing = scrape_plan.scrape_listing(name)
            carts = list(inventory.files("pico8/")) if name == "pico8" else ()
            plan = plan_art(listing, targets, replace, carts)
            if not any(plan.make.values()) and not any(plan.have.values()) and not plan.no_source:
                continue
            if dry_run:
                _show_plan(name, plan, targets)
                total_bytes += sum(plan.estimate_bytes.values())
                continue
            sources = {s: k for t in targets for s, k in plan.make[t]}
            stems = list(sources)
            skipped += max(plan.have.values(), default=0) if not replace else 0
            failed_here = made_here = 0
            for i in range(0, len(stems), BATCH):
                batch = [(s, sources[s]) for s in stems[i:i + BATCH]]
                tmp = tempfile.mkdtemp()
                try:
                    keys = sorted({k for _, k in batch})
                    sizes = {**listing, **{c: None for c in carts}}

                    def get(n):
                        path = os.path.join(tmp, f"{n}{os.path.splitext(keys[n])[1]}")
                        try:
                            s3.download((keys[n], path, sizes.get(keys[n]) or 0))
                            return keys[n], path
                        except (OSError, *s3.ERRORS):
                            return keys[n], None
                    with ThreadPoolExecutor(workers) as ex:
                        paths = dict(ex.map(get, range(len(keys))))
                    jobs, unreadable = _jobs(name, batch, paths, listing, replace, targets)
                    for rom in unreadable:
                        ui.failure(ui.yellow(f"  ⚠️  {rom}: its picture can't be read; skipped"))
                    bad = upload.run_uploads(jobs, quiet=True) if jobs else 0
                    failed_here += len(unreadable) + bad
                    made_here += len(jobs) - bad
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
            print(f"  {name}: {made_here} file(s) made" + (f", {failed_here} failed" if failed_here else ""))
            made += made_here
            made_here = 0
            failed += failed_here
    except KeyboardInterrupt:
        print(ui.yellow(f"\nStopped; {made + made_here} file(s) made so far."))
        return 130
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    if dry_run:
        print(f"Total: about {ui.human_size(total_bytes)} to make, an estimate from average sizes; nothing was read or written")
        return 0
    print(f"{made} file(s) made, {skipped} ROM(s) skipped (already have it), {failed} failed")
    return 1 if failed else 0
