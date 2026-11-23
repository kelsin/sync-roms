import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402

from sync_roms import custom_themes  # noqa: E402

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


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = os.path.join(self.tmp.name, "base")

    def test_registry_names(self):
        self.assertEqual(custom_themes.names(), ["Pixel Consoles", "Pixel Controllers"])
        for module in custom_themes.THEMES.values():
            self.assertEqual(module.BASE, "SPRUCE")

    def test_build_overlays_base(self):
        make_base(self.base)
        module = custom_themes.THEMES["Pixel Consoles"]
        dest = module.build(self.base, os.path.join(self.tmp.name, "out"))
        self.assertEqual(dest, os.path.join(self.tmp.name, "out", module.NAME))
        with Image.open(os.path.join(dest, "skin", "background.png")) as im:
            self.assertEqual(set(im.convert("RGBA").getdata()), {(0, 0, 0, 255)})
        with Image.open(os.path.join(dest, "icons", "sel", "gba.png")) as im:
            self.assertIsNotNone(im.convert("RGBA").getbbox())
        with open(os.path.join(dest, "config.json")) as f:
            config = json.load(f)
        self.assertEqual(config["name"], module.NAME)
        self.assertEqual(config["screensaver"]["bgColor"], "#000000")
        self.assertEqual(config["extra"], 1)
        with Image.open(os.path.join(dest, "icons_720x540", "gba.png")) as im:
            self.assertEqual(im.size, (134, 146))

    def test_build_is_deterministic(self):
        make_base(self.base)
        module = custom_themes.THEMES["Pixel Controllers"]
        a = module.build(self.base, os.path.join(self.tmp.name, "a"))
        b = module.build(self.base, os.path.join(self.tmp.name, "b"))
        self.assertEqual(hashes(a), hashes(b))

    def test_files_missing_in_base_are_skipped(self):
        make_base(self.base)
        os.remove(os.path.join(self.base, "skin", "bg-title.png"))
        os.remove(os.path.join(self.base, "skin", "background.png"))
        dest = custom_themes.THEMES["Pixel Consoles"].build(self.base, os.path.join(self.tmp.name, "out"))
        self.assertFalse(os.path.exists(os.path.join(dest, "skin", "bg-title.png")))

    def test_icon_folders_missing_in_base_are_created(self):
        os.makedirs(self.base)
        dest = custom_themes.THEMES["Pixel Controllers"].build(self.base, os.path.join(self.tmp.name, "out"))
        self.assertTrue(os.path.exists(os.path.join(dest, "icons", "sel", "gba.png")))

    def test_icons_missing_in_base_are_skipped(self):
        make_base(self.base, ssh=False)
        dest = custom_themes.THEMES["Pixel Consoles"].build(self.base, os.path.join(self.tmp.name, "out"))
        self.assertFalse(os.path.exists(os.path.join(dest, "icons", "app", "SSH.png")))


if __name__ == "__main__":
    unittest.main()
