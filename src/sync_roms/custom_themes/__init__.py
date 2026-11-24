"""Custom spruceOS themes sync-roms builds from a base theme. STYLES maps each style's name to its module; a built
theme is one style in one palette (palettes.py), named `<style> - <palette>`;
a style with PALETTES = False is built once, as `<style>`."""
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .. import downloads, inventory, runtime, s3, store
from . import manifest, pixel_consoles, pixel_controllers, totk_james

STYLES = {module.STYLE: module for module in (pixel_consoles, pixel_controllers, totk_james)}


def styles():
    return sorted(STYLES, key=str.lower)


def theme_name(style, palette_name):
    """The theme's folder name in storage and on cards."""
    return f"{style} - {palette_name}"


class BaseMissing(ValueError):
    """Storage has no folder for the base theme."""

    def __init__(self, base):
        super().__init__(f"the base theme {base} isn't in storage")
        self.base = base


class DownloadFailed(OSError):
    """Some files of the base theme couldn't be downloaded."""


def fetch_base(base):
    """Local folder holding the base theme's files from storage (missing or different-size ones downloaded).
    Raises BaseMissing when storage has no such folder; an unmounted share raises the storage error instead."""
    s3.check_root()
    prefix = f"{runtime.SPRUCE_THEMES_PREFIX}{base}/"
    listing = inventory.files(prefix, sizes=True)
    if not listing:
        raise BaseMissing(base)
    folder = os.path.join(store.cache_dir(), "themes", "base", base)
    jobs = []
    for key, size in sorted(listing.items()):
        downloads.add_job(jobs, key, folder, key[len(prefix):], size)
    failed = downloads.run_downloads(downloads.plan_downloads(jobs), "Base theme", "🎨", folder)
    if failed:
        raise DownloadFailed(f"{failed} file(s) of the base theme {base} failed to download")
    _prune(folder, {p for _, p, _ in jobs})
    return folder


def _prune(folder, keep):
    """Delete the files under folder that aren't in keep (gone from storage), then any emptied folders."""
    for dirpath, _, files in os.walk(folder, topdown=False):
        for file in files:
            path = os.path.join(dirpath, file)
            if path not in keep:
                os.remove(path)
        if dirpath != folder and not os.listdir(dirpath):
            os.rmdir(dirpath)


def needs_palettes(styles):
    """Whether any of the named styles (all when None) is built in palettes."""
    chosen = list(STYLES) if styles is None else styles
    return any(getattr(STYLES[s], "PALETTES", True) for s in chosen if s in STYLES)


def build(styles, palettes, out=None):
    """Build each named style (all when None) in each palette into out, or the cache's build folder; returns
    {theme name: built folder}. Raises KeyError for an unknown style, ValueError for no palettes (when a style needs them) and
    BaseMissing when a base theme isn't in storage."""
    chosen = sorted(STYLES, key=str.lower) if styles is None else list(styles)
    for style in chosen:
        if style not in STYLES:
            raise KeyError(style)
    if not palettes and needs_palettes(chosen):
        raise ValueError("no palettes to build")
    out = out or os.path.join(store.cache_dir(), "themes", "build")
    bases = {}
    built = {}
    for style in chosen:
        module = STYLES[style]
        if module.BASE not in bases:
            bases[module.BASE] = fetch_base(module.BASE)
        if not getattr(module, "PALETTES", True):
            built[module.STYLE] = module.build(bases[module.BASE], out)
            continue
        for palette in palettes:
            built[theme_name(style, palette.name)] = module.build(bases[module.BASE], out, palette)
    return built


@dataclass
class Plan:
    name: str
    adopt: bool = False
    new: list = field(default_factory=list)
    changed: list = field(default_factory=list)
    same: list = field(default_factory=list)
    stale: list = field(default_factory=list)  # storage keys
    skipped: str | None = None


def plan_publish(name, built, listing, state, downloaded):
    """What publishing the built folder does to storage: listing is {key: size} under the theme's folder, state the
    manifest, downloaded the folders `themes update` made (never touched)."""
    if name in downloaded:
        return Plan(name, skipped=f"{name} is a downloaded theme")
    prefix = f"{runtime.SPRUCE_THEMES_PREFIX}{name}/"
    listing = {k: v for k, v in listing.items() if k.startswith(prefix)}
    recorded = (state.get(name) or {}).get("files", {})
    plan = Plan(name, adopt=bool(listing) and name not in state)
    tree = manifest.hash_tree(built)
    for rel, (digest, size) in sorted(tree.items()):
        key = prefix + rel
        if key not in listing:
            plan.new.append(rel)
        elif list(recorded.get(rel) or ()) != [digest, size] or listing[key] != size:
            plan.changed.append(rel)
        else:
            plan.same.append(rel)
    plan.stale = sorted(k for k in listing if k[len(prefix):] not in tree)
    return plan


def _tags(keys):
    with ThreadPoolExecutor(s3.STAT_WORKERS) as ex:
        return dict(zip(keys, ex.map(inventory.tag, keys)))


COMPACT_OVER = 4  # more themes than this in one publish: one line each


def publish(styles, palettes, dry_run=False):
    """Build the named styles (all when None) in each palette and make their storage folders match: upload new and changed
    files, delete the files a build no longer makes, and record each file's hash in the manifest. Returns the exit code.
    Raises BaseMissing, DownloadFailed, a storage error, or ValueError for a malformed manifest or themes.json."""
    from .. import spruce_themes, ui, upload
    s3.check_root()  # an unmounted share must never read as empty theme folders
    built = build(styles, palettes)
    state = manifest.read()
    downloaded = {v["folder"] for v in spruce_themes.read_state().values()}
    plans, trees, jobs, stale, sizes = [], {}, [], [], {}
    for name, folder in built.items():
        prefix = f"{runtime.SPRUCE_THEMES_PREFIX}{name}/"
        listing = inventory.files(prefix)
        plan = plan_publish(name, folder, listing, state, downloaded)
        plans.append(plan)
        if plan.skipped:
            print(ui.yellow(f"⚠️  {plan.skipped} (in {runtime.SPRUCE_THEMES_STATE}): left alone"))
            continue
        trees[name] = manifest.hash_tree(folder)
        recorded = (state.get(name) or {}).get("files", {})
        gone = [prefix + rel for rel in recorded if rel not in trees[name] and prefix + rel not in listing]
        candidates = set(plan.stale) | inventory.uncached(gone)  # published by another machine since the cache
        plan.stale = sorted(k for k, t in _tags(sorted(candidates)).items() if t is not None)  # not gone behind the cache
        for rel in plan.new + plan.changed:
            sizes[prefix + rel] = trees[name][rel][1]
            jobs.append((prefix + rel, os.path.join(folder, *rel.split("/")), trees[name][rel][1]))
        stale += plan.stale

        def size(rels):
            return ui.human_size(sum(trees[name][r][1] for r in rels))
        if len(built) > COMPACT_OVER:
            print(f"🎨 {name}: new {len(plan.new)} ({size(plan.new)}) · changed {len(plan.changed)} ({size(plan.changed)})"
                  f" · same {len(plan.same)} · stale {len(plan.stale)}")
            if plan.adopt:
                print(ui.yellow(f"   Adopting the existing folder {prefix}: every file is uploaded, the others deleted"))
            if plan.stale:
                ui.print_head(plan.stale, 5, indent=6, paint=ui.yellow)
            continue
        print(ui.bold(f"\n🎨 {name}") + ui.dim(f"  → {s3.location()}/{prefix}"))
        if plan.adopt:
            print(ui.yellow("   Adopting the existing folder: every file is uploaded, the others deleted"))
        print(f"   💿 New: {ui.bold(str(len(plan.new)))} ({size(plan.new)})")
        print(f"   ♻️  Changed: {ui.bold(str(len(plan.changed)))} ({size(plan.changed)})")
        print(f"   ⚡ Same: {len(plan.same)}")
        print(f"   🗑️  Stale, would delete: {ui.bold(str(len(plan.stale)))}")
        ui.print_head(plan.stale, 5, indent=6, paint=ui.yellow)
    skipped = any(p.skipped for p in plans)
    if not jobs and not stale:
        print(ui.green("\nNothing to upload ✨"))
        return 1 if skipped else 0
    if dry_run:
        print(ui.yellow("\n🧪 Dry run — nothing uploaded or deleted"))
        return 1 if skipped else 0
    question = f"☁️  Upload {len(jobs)} file(s)" + (f" and delete {len(stale)} stale file(s)" if stale else "") + \
        f" in {s3.location()}/{runtime.SPRUCE_THEMES_PREFIX}?"
    if ui.ASSUME_YES:
        print(f"{question} (--yes)")
    else:
        if not ui.has_terminal():
            ui.fail("Pass --yes to publish without a terminal to confirm on", 2)
        if not ui.confirm(question):
            print(ui.yellow("👋 Cancelled."))
            return 1 if skipped else 0
    active = [p for p in plans if not p.skipped]

    def claim(data):  # before the first upload: an interrupted run leaves folders the next one knows as its own
        for p in active:
            data.setdefault(p.name, {}).setdefault("files", {})
    manifest.update(claim)
    before = _tags([f"{runtime.SPRUCE_THEMES_PREFIX}{p.name}/{r}" for p in active for r in p.changed])
    failed = upload.run_uploads(jobs) if jobs else 0
    done = set(sizes)
    if failed:  # only files verifiably in storage with the built size (a changed one: its tag changed too) count
        listed = {}
        for p in active:
            listed.update(inventory.files(f"{runtime.SPRUCE_THEMES_PREFIX}{p.name}/"))
        after = _tags(list(before))
        done = {k for k in sizes if listed.get(k) == sizes[k] and (k not in before or after[k] != before[k])}
    errors = s3.delete_keys(stale) if stale else []
    for e in errors:
        print(ui.red(f"  ❌ couldn't delete {e.get('Key')}: {e.get('Message')}"))

    def record(data):
        for p in active:
            prefix = f"{runtime.SPRUCE_THEMES_PREFIX}{p.name}/"
            files = data.setdefault(p.name, {}).setdefault("files", {})
            for rel in list(files):
                if rel not in trees[p.name]:
                    del files[rel]
            for rel in p.same + [r for r in p.new + p.changed if prefix + r in done]:
                files[rel] = list(trees[p.name][rel])
    manifest.update(record)
    bad = max(failed, len(sizes) - len(done)) + len(errors)
    print(ui.green("\n🎉 Done!") if not bad else ui.red(f"\n⚠️  Done with {bad} failure(s)"))
    return 1 if bad or skipped else 0
