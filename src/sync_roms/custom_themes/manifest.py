"""The custom themes manifest in storage: {theme folder: {"files": {rel path: [sha256, size]}}}."""
import hashlib
import json
import os

from .. import runtime, s3, shared


def hash_tree(folder):
    """{relative path with "/": (sha256 hex, size)} of the files under folder, leaving out .DS_Store and ._* files."""
    result = {}
    for dirpath, _, files in os.walk(folder):
        for name in files:
            if name == ".DS_Store" or name.startswith("._"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, "rb") as f:
                data = f.read()
            result[os.path.relpath(path, folder).replace(os.sep, "/")] = (hashlib.sha256(data).hexdigest(), len(data))
    return result


def _safe(rel):
    """A path that stays inside its theme folder: no empty, "." or ".." part, no leading "/" or backslash."""
    return isinstance(rel, str) and "\\" not in rel and all(part not in ("", ".", "..") for part in rel.split("/"))


def _entry(value):
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], int)


def _parse(text):
    """The manifest as {theme: {"files": {rel: [sha256, size]}}}, leaving out what doesn't have that shape, so a
    hand-edited file can never name a key outside a theme's folder."""
    data = json.loads(text)
    if not isinstance(data, dict):
        return {}
    out = {}
    for name, theme in data.items():
        if not isinstance(theme, dict):
            continue
        files = theme.get("files")
        files = files if isinstance(files, dict) else {}
        out[name] = {"files": {rel: v for rel, v in files.items() if _safe(rel) and _entry(v)}}
    return out


def _dump(data):
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def read():
    """The manifest, {} when storage has none (an unmounted share raises the storage error instead)."""
    s3.check_root()
    try:
        return _parse(shared.read(runtime.CUSTOM_THEMES_STATE))
    except s3.ERRORS as e:
        if not s3.missing(e):
            raise
        return {}


def update(change):
    """Change the manifest from its fresh content through change(data), which mutates the dict; returns the new one."""
    return shared.update(runtime.CUSTOM_THEMES_STATE, _parse, {}, change, _dump)
