"""Art Book themes' icons/overlay/fds.png is a copy of fc.png (the NES logo). Replaced with the right wordmark only
while the two are byte-identical, so it stops once upstream fixes the file."""
import os

from .. import cardfs, store

ID = "fds"
THEMES = ("ART_BOOK_NEXT", "ART_BOOK_NOIR", "ART_BOOK_OUTLINE")
IMAGE = os.path.join(store.REPO_DATA, "themes", "spruce-fds", "fds.png")


def plan(base):
    with open(IMAGE, "rb") as f:
        image = f.read()
    writes, seen, ours, theirs = [], False, False, False
    for name in THEMES:
        folder = os.path.join(base, "Themes", name, "icons", "overlay")
        try:
            fds, fc = cardfs.read(os.path.join(folder, "fds.png")), cardfs.read(os.path.join(folder, "fc.png"))
        except OSError:
            continue
        seen = True
        if fds == fc:
            writes.append((os.path.join(folder, "fds.png"), image))
        else:
            ours, theirs = ours or fds == image, theirs or fds != image
    if not seen:
        return [], None
    reason = ("upstream fixed it" if theirs and not ours else "an earlier sync applied it" if ours and not theirs
              else "upstream fixed it or an earlier sync applied it")
    return writes, reason
