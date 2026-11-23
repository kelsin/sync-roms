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


def _parse(text):
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


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
