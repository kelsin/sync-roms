"""Workaround for spruceOS's Art Book themes: their icons/overlay/fds.png is a copy of fc.png (the NES logo). Replaced
with the right wordmark only while the two are byte-identical, so it stops once upstream fixes the file."""
import os

from . import cardfs, store, ui

THEMES = ("ART_BOOK_NEXT", "ART_BOOK_NOIR", "ART_BOOK_OUTLINE")
IMAGE = os.path.join(store.REPO_DATA, "themes", "spruce-fds", "fds.png")


def _buggy(base):
    """Paths of the themes' fds.png that are byte-identical to the same theme's fc.png."""
    found = []
    for name in THEMES:
        folder = os.path.join(base, "Themes", name, "icons", "overlay")
        try:
            fds, fc = cardfs.read(os.path.join(folder, "fds.png")), cardfs.read(os.path.join(folder, "fc.png"))
        except OSError:
            continue
        if fds == fc:
            found.append(os.path.join(folder, "fds.png"))
    return found


def install(layout_name, base, dry_run):
    """Fix the buggy fds.png files of a spruce card. Returns the paths fixed (or, with dry_run, that would be)."""
    if layout_name != "spruce":
        return []
    paths = _buggy(base)
    if dry_run:
        for path in paths:
            print(ui.dim(f"🎨 would replace {os.path.relpath(path, base).replace(os.sep, '/')} (it shows the NES logo)"))
        return paths
    if paths:
        with open(IMAGE, "rb") as f:
            data = f.read()
        for path in paths:
            cardfs.write_bytes(path, data)
    return paths
