"""The standard fake theme base and a cache of its builds, shared by the custom-theme tests (not a test module)."""
import atexit
import hashlib
import json
import os
import shutil
import tempfile
from unittest import mock

import isolate  # noqa: F401  (a sync_roms import below must come after it)
from PIL import Image

from sync_roms import custom_themes

CONFIG = {"name": "SPRUCE", "author": "spruce", "description": "x", "screensaver": {"bgColor": "#282828"}, "extra": 1}


def png(path, size, color=(0, 0, 0, 0)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGBA", size, color).save(path)


def make_base(path, ssh=True):
    with open(os.path.join(_mk(path), "config.json"), "w") as f:
        json.dump(CONFIG, f)
    png(os.path.join(path, "skin", "background.png"), (640, 480), (40, 40, 40, 255))
    for name in ("app_loading_bg.png", "bg-gamelist.png", "bg-title.png", "tips-bar-bg.png", "menu-5line-bg.png", "menu-6line-bg.png"):
        png(os.path.join(path, "skin", name), (640, 480), (40, 40, 40, 255))
    for name in ("menu-5line-bg.png", "menu-6line-bg.png"):
        png(os.path.join(path, "skin_640_480", name), (640, 480), (40, 40, 40, 255))
    png(os.path.join(path, "icons", "gba.png"), (120, 130))
    png(os.path.join(path, "icons", "sel", "gba.png"), (120, 130))
    png(os.path.join(path, "icons_720x540", "gba.png"), (134, 146))
    if ssh:
        png(os.path.join(path, "icons", "app", "SSH.png"), (70, 70))


def _mk(path):
    os.makedirs(path, exist_ok=True)
    return path


def hashes(root):
    out = {}
    for dirpath, _, files in os.walk(root):
        for file in files:
            p = os.path.join(dirpath, file)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = hashlib.sha256(f.read()).hexdigest()
    return dict(sorted(out.items()))


_BUILT = {}  # (style module, palette name) -> built folder, made once from the standard fake base
_BUILT_ROOT = []


def _built_root():
    if not _BUILT_ROOT:
        _BUILT_ROOT.append(tempfile.mkdtemp())
        make_base(os.path.join(_BUILT_ROOT[0], "base"))
    return _BUILT_ROOT[0]


def _cleanup():
    for root in _BUILT_ROOT:
        shutil.rmtree(root, ignore_errors=True)
    _BUILT_ROOT.clear()
    _BUILT.clear()


atexit.register(_cleanup)  # per process, so a per-module run, a shard and the single-process run all clean up


def _cached(real):
    """A style's build that builds each palette of the standard fake base once and hands every caller a fresh copy;
    any other base gets the real build."""
    def build(base_dir, out_dir, palette=None):
        args = (palette,) if palette else ()
        standard = os.path.join(_built_root(), "base")
        if hashes(base_dir) != hashes(standard):
            return real(base_dir, out_dir, *args)
        key = (real.__module__, palette.name if palette else None)
        if key not in _BUILT:
            _BUILT[key] = real(standard, os.path.join(_built_root(), "out", str(len(_BUILT))), *args)
        dest = os.path.join(out_dir, os.path.basename(_BUILT[key]))
        if os.path.lexists(dest):
            shutil.rmtree(dest)
        shutil.copytree(_BUILT[key], dest)
        return dest
    return build


class CachedBuilds:
    """Mixin: cache_builds() swaps each style's real build (covered by Build and PublishRealBuild) for copies of one build.

    Patching a build internal (pixel_build.preview, a helper, the font) while the cache is active would silently get
    stale cached output, so such tests belong in a real-build class like PublishRealBuild."""

    def cache_builds(self):
        for module in custom_themes.STYLES.values():
            self.enterContext(mock.patch.object(module, "build", _cached(module.build)))
