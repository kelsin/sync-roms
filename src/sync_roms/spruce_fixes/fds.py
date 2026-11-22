"""Art Book themes' icons/overlay/fds.png is a copy of fc.png (the NES logo). Replaced with the right wordmark only
while the two are byte-identical, so it stops once upstream fixes the file. PyUI's resized copies
(`icons_<W>x<H>/overlay/`) get the wordmark resized as PyUI resizes icons."""
import io
import os

from . import pyui
from .. import cardfs, store

ID = "fds"
THEMES = ("ART_BOOK_NEXT", "ART_BOOK_NOIR", "ART_BOOK_OUTLINE")
IMAGE = os.path.join(store.REPO_DATA, "themes", "spruce-fds", "fds.png")


def plan(base):
    with open(IMAGE, "rb") as f:
        image = f.read()
    writes, seen, ours, theirs = [], False, False, False
    for name in THEMES:
        root = os.path.join(base, "Themes", name)
        for icons, size in pyui.folders(root, "icons"):
            folder = os.path.join(root, icons, "overlay")
            try:
                fds, fc = cardfs.read(os.path.join(folder, "fds.png")), cardfs.read(os.path.join(folder, "fc.png"))
            except OSError:
                continue
            seen = True
            wanted = image if size is None else _resized(image, pyui.scale(root, size))
            if fds == fc:
                writes.append((os.path.join(folder, "fds.png"), wanted))
            else:
                ours, theirs = ours or fds == wanted, theirs or fds != wanted
    if not seen:
        return [], None
    reason = ("upstream fixed it" if theirs and not ours else "an earlier sync applied it" if ours and not theirs
              else "upstream fixed it or an earlier sync applied it")
    return writes, reason


def _resized(image, scale):
    """image as PyUI resizes an icon by scale (the same bytes at 1.0)."""
    if scale == 1.0:
        return image
    from PIL import Image
    picture = Image.open(io.BytesIO(image))
    out = io.BytesIO()
    picture.resize((int(picture.width * scale), int(picture.height * scale)), Image.LANCZOS).save(out, "PNG")
    return out.getvalue()
