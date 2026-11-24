"""Storage's scrapes/ folder: the ROMs it is for, derived art names and cleanup."""
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor


from . import inventory, runtime, s3, scrape_plan, store, ui, vita


def bucket_roms(systems, all_files=False):
    """{storage folder: set of ROM paths in it}, from storage's real contents.

    By default only the ROMs a sync would install (the games the cards list, or every file of a
    full system). With all_files, every file in the system's storage folder.
    """
    todo = systems if all_files else [s for s in systems if s.get("full_system") or store.listed(s)]
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        listings = list(ex.map(lambda s: inventory.files(s["bucket"] + "/") if all_files else store.list_system(s), todo))
    roms = {s["bucket"]: set() for s in systems}
    for s, have in zip(todo, listings):
        keys = (k for k in have if not k.endswith("/") and not vita.is_extra(k)) if all_files else (k for k in store.available_keys(s, have) if k in have and not vita.is_extra(k))
        roms[s["bucket"]] = {k.split("/", 1)[1] for k in keys}
    return roms


def rom_stems(roms):
    """{system: ROM paths without their extension}, which is how scraped media is named."""
    return {system: {os.path.splitext(r)[0] for r in paths} for system, paths in roms.items()}


def _image_size(path):
    """(width, height) of a local image, or None when it can't be read."""
    Image = scrape_plan.pillow_image()
    try:
        with Image.open(path) as im:
            return im.size
    except (OSError, Image.DecompressionBombError):
        return None


def derived_art(system, stem, found, size=None):
    """[(key, source path or None, (max width, max height))] of the Onion and Spruce box art a ROM gets.

    found: {media type: local path} of the ROM's art (PICO-8 may add its cart picture as "cart"); size: the source's
    (width, height), read from the file when not given, to leave out Spruce sizes that would equal a larger one (an
    unreadable image leaves none out). Both Imgs folders are flat, so ROMs in subfolders get none.
    """
    order = scrape_plan.ONION_ART + (("cart",) if system == "pico8" else ())
    first = next((t for t in order if t in found), None)
    if "/" in stem or first is None:
        return []
    src = found[first]  # None for a type already in storage: the caller makes nothing from it
    base = f"{scrape_plan.SCRAPES}/{system}"
    out = [(f"{base}/{scrape_plan.ONION_TYPE}/{stem}.png", src, scrape_plan.ONION_MAX)]
    if scrape_plan.can_make_qoi():
        if size is None and src:
            size = _image_size(src)
        wanted = scrape_plan.spruce_tiers(size) if size else scrape_plan.SPRUCE_TYPES
        out += [(f"{base}/{kind}/{stem}.qoi", src, box) for kind, box in scrape_plan.SPRUCE_TIERS if kind in wanted]
    return out


def text_keys(existing):
    """Keys under scrapes/ of the metadata.json files we merge into."""
    return [k for k in existing if k.endswith("/metadata.json")]


def metadata_roms(remote_texts):
    """The storage keys ("system/rom") of the ROMs the scrapes/<system>/metadata.json texts have entries for."""
    out = set()
    for key, text in remote_texts.items():
        parts = key.split("/")
        if len(parts) != 3:
            continue
        try:
            out |= {f"{parts[1]}/{rom}" for rom in scrape_plan.parse_metadata(text, key)}
        except ValueError:  # plan_clean warns about it
            pass
    return out


def plan_clean(existing, roms, remote_texts):
    """What in scrapes/ no longer matches an available ROM.

    Returns (delete keys, rewrites [(key, text)], per-system counts, warnings).
    """
    stems = rom_stems(roms)
    delete, rewrites, warnings = [], [], []
    per = defaultdict(lambda: {"media": 0, "bytes": 0, "entries": 0})
    for key, size in sorted(existing.items()):
        parts = key.split("/")
        if len(parts) < 3 or parts[0] != scrape_plan.SCRAPES or key.endswith("/"):
            continue
        system = parts[1]
        if parts[2] == "metadata.json" and len(parts) == 3:
            try:
                data = scrape_plan.parse_metadata(remote_texts[key], key)
            except (KeyError, ValueError):
                warnings.append(f"{key} isn't valid JSON, skipped")
                continue
            keep = {k: v for k, v in data.items() if k in roms.get(system, ())}
            if len(keep) == len(data):
                continue
            per[system]["entries"] += len(data) - len(keep)
            if keep:
                rewrites.append((key, scrape_plan.dump_json(keep)))
            else:
                delete.append(key)
        elif (entry := scrape_plan.media_entry(key)) and entry[0] not in stems.get(system, ()):
            delete.append(key)
            per[system]["media"] += 1
            per[system]["bytes"] += size
    return delete, rewrites, per, warnings


def clean_scrapes(args):
    """Remove scrapes/ media and metadata for ROMs that aren't in storage (any ROM file, listed or not)."""
    print(ui.bold("🧹 Clean scrapes") + ui.dim(f"  {s3.access(True)}"))
    try:
        manifest = store.load_manifest()
        print("📏 Listing every ROM in storage...")
        roms = bucket_roms(manifest["systems"], all_files=True)
        print("☁️  Listing scrapes/...")
        existing = inventory.files(scrape_plan.SCRAPES + "/")
        remote_texts = s3.fetch_texts(text_keys(existing))
        uncached = inventory.uncached(metadata_roms(remote_texts))
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    for key in uncached:  # in storage all the same: what was scraped for them stays
        roms.setdefault(key.split("/", 1)[0], set()).add(key.split("/", 1)[1])
    if uncached:
        print(ui.yellow(f"  ⚠️  {len(uncached)} ROM(s) are in storage but not in the storage cache; their scrapes are kept "
                        f"(run {inventory.UPDATE_HINT})"))
    delete, rewrites, per, warnings = plan_clean(existing, roms, remote_texts)
    for w in warnings:
        print(ui.yellow(f"  ⚠️  {w}"))
    if not delete and not rewrites:
        print(ui.green("Nothing to clean ✨"))
        return 0
    print(ui.bold("\nFor ROMs that aren't in storage:"))
    for system in sorted(per):
        c = per[system]
        print(f"  {system}: {c['media']} media file(s) ({ui.human_size(c['bytes'])}), {c['entries']} metadata entr{'y' if c['entries'] == 1 else 'ies'}")
    ui.print_head(delete, 10, indent=5)
    if args.dry_run:
        print(ui.yellow("\n🧪 Dry run — nothing deleted"))
        return 0
    question = f"🗑️  Permanently delete {len(delete)} file(s) and rewrite {len(rewrites)} metadata file(s)?"
    if ui.ASSUME_YES:
        print(f"{question} (--yes)")
    else:
        if not ui.has_terminal():
            ui.fail("Pass --yes to delete without a terminal to confirm on", 2)
        if not ui.confirm(question, default=False):
            print(ui.yellow("↩️  Keeping everything"))
            return 0
    failed = 0
    try:
        for key, text in rewrites:
            s3.put_text(key, text)
        failed = len(s3.delete_keys(delete)) if delete else 0
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    print(ui.green("\n🎉 Done!") if not failed else ui.red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0
