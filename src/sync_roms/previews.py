"""Images the list editors show beside the highlighted row."""
import io
import os
import shutil
import tarfile
import tempfile

from . import inventory, mirroring, runtime, s3, scrape_plan, store, themeart

GAME_MEDIA = ("covers", "miximages", "titlescreens", "screenshots")
GAME_WIDTH = 300  # px: a game's picture is drawn this wide, at the top right of its list (filter_list preview_width)
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


def _image(key):
    """(key, size) of the scraped image of the game at bucket key, or None (size is None when the listing has none)."""
    media = _index(key.split("/", 1)[0]).get(store.key_title(key), {})
    for kind in GAME_MEDIA:
        if kind in media:
            return media[kind]
    return None


def game(key):
    """A local file with the scraped image of the game at bucket key (e.g. gba/Game.zip), or None."""
    try:
        found = _image(key)
        return _source(found[0]) if found else None
    except (*s3.ERRORS, ValueError):
        return None


def _source(image):
    """A local path of the storage file image: in the storage folder, the mirror or a download; None when it is missing."""
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


def _read(path):
    """The bytes of the file at path, or None when it is missing. It is opened without a stat first: on a network share
    each is a slow round trip."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except (FileNotFoundError, NotADirectoryError):
        return None


def _source_bytes(image):
    """The bytes of the storage file image, from the places _source looks in, in its order; None when it is missing."""
    root = s3.read_root()
    if root:
        data = _read(s3.safe_join(root, image))
        if data is not None or not runtime._mirror_root:
            return data
        # the mirror only holds scrapes for listed ROMs: look in storage itself
        if runtime.ROOT:
            return _read(s3.safe_join(runtime.ROOT, image))
        with mirroring.storage_reads():
            return _read(_download(image))
    return _read(_download(image))


def game_thumb(key):
    """A local GAME_WIDTH px wide WebP of the game's scraped image (see game), or None. It is kept in preview-cache/
    under the image's storage version (its ETag when known, else its size), so a game seen before loads from local disk
    without touching storage and a replaced image gets a new one. Without either the image itself is returned."""
    try:
        found = _image(key)
        if not found:
            return None
        image, size = found
        known = inventory.known(image)
        tag = known[1].strip('"') if known else (None if size is None else f"s{size}")
        if not tag:
            return _source(image)
        folder, name = os.path.split(s3.safe_join(os.path.join(store.data_dir(), "preview-cache"), image))
        stem = os.path.splitext(name)[0]
        path = os.path.join(folder, f"{stem}.{tag}.webp")
        if os.path.exists(path):
            return path
        data = _source_bytes(image)  # one read: Pillow's many small reads are each a slow round trip on a network share
        if data is None:
            return None
        from PIL import Image  # textual-image depends on Pillow
        picture = Image.open(io.BytesIO(data))
        picture.load()
        picture = picture.convert("RGBA" if picture.has_transparency_data else "RGB")
        picture = picture.resize((GAME_WIDTH, max(1, round(picture.height * GAME_WIDTH / picture.width))))
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as f:
                picture.save(f, "WEBP", quality=85)
            os.replace(tmp, path)
        except BaseException:
            os.remove(tmp)
            raise
        for old in os.listdir(folder):  # the same image's thumbnails of older versions (tags have no dots)
            if old != os.path.basename(path) and old.startswith(stem + ".") and old.endswith(".webp") \
                    and "." not in old[len(stem) + 1:-len(".webp")]:
                os.remove(os.path.join(folder, old))
        return path
    except Exception:  # noqa: BLE001 -- previews are cosmetic: an unreadable or corrupt image just shows none
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
