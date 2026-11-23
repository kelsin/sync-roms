"""Custom spruceOS themes sync-roms builds from a base theme. THEMES maps each theme's name to its module."""
import os
from dataclasses import dataclass, field

from .. import downloads, inventory, runtime, s3, store
from . import manifest, pixel_consoles, pixel_controllers

THEMES = {module.NAME: module for module in (pixel_consoles, pixel_controllers)}


def names():
    return sorted(THEMES, key=str.lower)


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


def build(selected, out=None):
    """Build the named themes (all when None) into out, or the cache's build folder; returns {name: built folder}.
    Raises KeyError for an unknown name and BaseMissing when a base theme isn't in storage."""
    chosen = names() if selected is None else list(selected)
    for name in chosen:
        if name not in THEMES:
            raise KeyError(name)
    out = out or os.path.join(store.cache_dir(), "themes", "build")
    bases = {}
    built = {}
    for name in chosen:
        module = THEMES[name]
        if module.BASE not in bases:
            bases[module.BASE] = fetch_base(module.BASE)
        built[name] = module.build(bases[module.BASE], out)
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
