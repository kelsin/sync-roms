"""Images the list editors show beside the highlighted row."""
import os
import shutil
import tarfile
import tempfile

from . import inventory, mirroring, runtime, s3, scrape_plan, store, themeart

GAME_MEDIA = ("covers", "miximages", "titlescreens", "screenshots")
_indexes = {}  # system -> scrape_index of its scrapes/ folder
OUTLINES = "_inc/systems/artwork-outline/"
_outlines = []  # [folder or None] once resolved this run


def reset():
    _indexes.clear()
    _outlines.clear()


def collection(art_id):
    """A collection's art file, or None when it has none."""
    return themeart.art_png(art_id) if art_id else None


def _index(system):
    if system not in _indexes:
        _indexes[system] = scrape_plan.scrape_index(
            inventory.files(f"{scrape_plan.SCRAPES}/{system}/", sizes=False))
    return _indexes[system]


def game(key):
    """A local file with the scraped image of the game at bucket key (e.g. gba/Game.zip), or None."""
    try:
        media = _index(key.split("/", 1)[0]).get(store.key_title(key), {})
        for kind in GAME_MEDIA:
            if kind in media:
                image = media[kind][0]
                break
        else:
            return None
        root = s3.read_root()
        if root:
            path = s3.safe_join(root, image)
            if os.path.isfile(path):
                return path
            if not runtime._mirror_root:
                return None
            # the mirror only holds scrapes for listed ROMs: look in storage itself
            if runtime.ROOT:
                path = s3.safe_join(runtime.ROOT, image)
                return path if os.path.isfile(path) else None
            with mirroring.storage_reads():
                return _download(image)
        return _download(image)
    except (*s3.ERRORS, ValueError):
        return None


def _download(image):
    path = os.path.join(store.data_dir(), "previews", image)
    if not os.path.exists(path):
        s3.download((image, path, None))
    return path


def _unpack(archive_path, part):
    """Write the theme's outline pictures flat into part (the archive's top folder is stripped)."""
    shutil.rmtree(part, ignore_errors=True)
    os.makedirs(part)
    with tarfile.open(archive_path, "r|gz") as archive:
        for member in archive:
            rel = member.name.split("/", 1)[1] if "/" in member.name else ""
            if not member.isfile() or not rel.startswith(OUTLINES) or not rel.endswith(".png"):
                continue
            with open(s3.safe_join(part, os.path.basename(rel)), "wb") as f:
                shutil.copyfileobj(archive.extractfile(member), f)


def _resolve_outlines():
    commit = themeart._stored_commit()
    if not commit:
        return None
    base = os.path.join(store.data_dir(), "theme-art")
    folder = os.path.join(base, commit)
    if os.path.isdir(folder):
        return folder
    part = folder + ".part"
    try:
        root = s3.read_root()
        if root:
            _unpack(s3.safe_join(root, themeart.ESDE_ARCHIVE), part)
        else:
            fd, tmp = tempfile.mkstemp(suffix=".tar.gz")
            os.close(fd)
            try:
                s3.download((themeart.ESDE_ARCHIVE, tmp, None))
                _unpack(tmp, part)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        try:
            os.rename(part, folder)
        except OSError:
            if not os.path.isdir(folder):  # else another process finished first
                raise
            shutil.rmtree(part, ignore_errors=True)
    except (*s3.ERRORS, *themeart.ARCHIVE_ERRORS, ValueError):
        shutil.rmtree(part, ignore_errors=True)
        return None
    for name in os.listdir(base):
        if name != commit:
            shutil.rmtree(os.path.join(base, name), ignore_errors=True)
    return folder


def system(system):
    """The theme's outline picture for a systems.json entry, or None when the theme has none."""
    name = system.get("folders", {}).get("esde")
    if not name:
        return None
    if not _outlines:
        _outlines.append(_resolve_outlines())
    if not _outlines[0]:
        return None
    path = os.path.join(_outlines[0], name + ".png")
    return path if os.path.exists(path) else None
