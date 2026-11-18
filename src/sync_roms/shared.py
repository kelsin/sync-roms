"""Files that live in storage and are mirrored in the data folder by their storage tag.

The mirror of storage key K is <data_dir>/storage/K (the storage file's exact text); each mirror's tag is kept in
<data_dir>/storage/.tags.json as {key: tag} (never in storage). A mirror is downloaded again only when the tag changes."""
import copy
import json
import os
import tempfile

from . import inventory, runtime, s3, store, ui

_TAGS = ".tags.json"


def local_path(key):
    return os.path.join(store.data_dir(), "storage", *key.split("/"))


def _tags_path():
    return os.path.join(store.data_dir(), "storage", _TAGS)


def read(key):
    """The storage file's text, from storage itself (never the local mirror, which holds only what syncs need)."""
    if runtime.ROOT:
        with open(s3.safe_join(runtime.ROOT, key), encoding="utf-8") as f:
            return f.read()
    return s3.s3_client().get_object(Bucket=runtime.BUCKET, Key=key)["Body"].read().decode("utf-8")


def _load_tags():
    try:
        with open(_tags_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_tags(tags):
    os.makedirs(os.path.dirname(_tags_path()), exist_ok=True)
    store.write_json(_tags_path(), tags, indent=2)


def _save_text(path, text):
    """Write text to path in one atomic step, making its folders."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + "-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


def _save_mirror(key, tag, text):
    _save_text(local_path(key), text)
    tags = _load_tags()
    tags[key] = tag
    _save_tags(tags)


def _drop_mirror(key):
    if os.path.exists(local_path(key)):
        os.remove(local_path(key))
    tags = _load_tags()
    if tags.pop(key, None) is not None:
        _save_tags(tags)


def load(key, parse, empty):
    """The storage file's parsed value, `empty` when it isn't in storage.

    parse(text) returns the value and raises ValueError when the text is malformed. The mirror is used when its tag
    matches storage's; on a storage error (or a malformed storage file) the mirror is used with a warning."""
    local_tag, local = _load_tags().get(key), empty
    try:
        with open(local_path(key), encoding="utf-8") as f:
            local = parse(f.read())
    except (OSError, ValueError):
        local_tag = None
    try:
        if runtime.ROOT and not os.path.isdir(runtime.ROOT):
            raise FileNotFoundError(f"{runtime.ROOT} is missing")
        tag = inventory.tag(key)
        if tag is None:
            _drop_mirror(key)
            return empty
        if tag == local_tag:
            return local
        text = read(key)
        data = parse(text)
    except (*s3.ERRORS, ValueError) as e:
        ui.warn(f"Couldn't check {key} in storage ({e}); using the local copy")
        return local
    try:
        _save_mirror(key, tag, text)
    except OSError as e:
        ui.warn(f"Couldn't save the local copy of {key} ({e})")
    return data


def write(key, text):
    """Put text in storage, then save the mirror and its tag."""
    s3.put_text(key, text)
    _save_mirror(key, inventory.tag(key), text)


def delete(key):
    """Delete the storage file, then its mirror and tag."""
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):  # an unmounted share: nothing to delete there
        raise FileNotFoundError(f"{runtime.ROOT} is missing")
    errors = s3.delete_keys([key])
    if errors:
        raise OSError(f"{key}: {errors[0].get('Message', errors[0])}")
    _drop_mirror(key)


def update(key, parse, empty, change, dump):
    """Change a storage file from its fresh content (not the mirror) and write it back. Returns the new value.

    A missing file counts as `empty` (and is created). change(data) mutates data or returns the new value; when it
    leaves an existing file's data equal to what was read, nothing is written."""
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):  # an unmounted share, not a missing file
        raise FileNotFoundError(f"{runtime.ROOT} is missing")
    try:
        data, existed = parse(read(key)), True
    except s3.ERRORS as e:
        if not s3.missing(e):
            raise
        data, existed = copy.deepcopy(empty), False
    before = copy.deepcopy(data)
    result = change(data)
    if result is not None:
        data = result
    if existed and data == before:
        return data
    write(key, dump(data))
    return data
