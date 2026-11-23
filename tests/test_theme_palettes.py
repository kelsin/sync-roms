import contextlib
import copy
import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402
from test_custom_themes import make_base  # noqa: E402

from sync_roms import commands, custom_themes, runtime, ui, upload, usersettings  # noqa: E402
from sync_roms.custom_themes import palettes  # noqa: E402
from sync_roms.custom_themes.pixel import recolor  # noqa: E402

GRAY = (80, 73, 69)
NAMES = ["Gruvbox", "Arcade", "Candy", "Mint", "Game Boy", "Pocket", "Virtual Boy", "Famicom", "NES", "SNES", "Genesis",
         "Dreamcast", "PlayStation", "Neo Geo", "PICO-8", "Commodore", "Amber CRT", "Green CRT", "Nord", "Dracula",
         "Solarized", "Synthwave", "Sunset", "Ocean", "Sakura", "Forest", "Grape", "Monochrome"]


def full_config():
    text = {"font": "nunwen.ttf", "size": 25, "color": "#EBDBB2"}
    return {
        "name": "Spruce", "author": "tenlevels", "description": "x", "unrelated": {"color": "#123456"},
        "batteryPercentage": dict(text), "title": dict(text), "hint": dict(text, contextbuttons=True),
        "currentpage": dict(text), "total": dict(text, color="#D65D0E"),
        "grid": {"font": "nunwen.ttf", "grid1x4": 25, "color": "#7C6F64", "selectedcolor": "#FBF1C7"},
        "list": {"font": "nunwen.ttf", "size": 24, "color": "#FBF1C7", "selectedcolor": "#FBF1C7"},
        "screensaver": {"bgColor": "#282828", "widgets": [
            {"type": "clock", "fontSize": 82, "color": "#FFFFFF", "font": "nunwen.ttf"},
            {"type": "date", "fontSize": 24, "color": "#EBDBB2"},
            {"type": "battery", "fontSize": 20, "color": "#88CC88"}]},
    }


def rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def bar_png(path):
    """The base gray bar with one red pixel at (0, 0) and a half-transparent gray one at (1, 0)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.new("RGBA", (8, 4), GRAY + (255,))
    img.putpixel((0, 0), (200, 10, 10, 255))
    img.putpixel((1, 0), GRAY + (128,))
    img.save(path)


def pixels(path):
    with Image.open(path) as im:
        return im.convert("RGBA").load()


def palette_base(path):
    make_base(path)
    with open(os.path.join(path, "config.json"), "w") as f:
        json.dump(full_config(), f)
    with open(os.path.join(path, "config_720x480.json"), "w") as f:
        json.dump(full_config(), f)
    bar_png(os.path.join(path, "skin", "bg-list-l.png"))
    bar_png(os.path.join(path, "skin_720x480", "bg-list-l.png"))


class Palettes(unittest.TestCase):
    def test_palettes_data(self):
        self.assertEqual(len(palettes.PALETTES), 28)
        self.assertEqual(palettes.names(), NAMES)
        self.assertEqual(list(palettes.PALETTES), NAMES)
        for name, p in palettes.PALETTES.items():
            self.assertEqual(p.name, name)
            for value in (p.text, p.list, p.selected, p.accent, p.dim, p.bar):
                self.assertRegex(value, r"^#[0-9A-F]{6}$", name)
        self.assertEqual(palettes.get("Candy").accent, "#FF7FB8")
        self.assertEqual(palettes.get("Gruvbox").bar, "#504945")
        with self.assertRaises(KeyError):
            palettes.get("Nope")

    def test_theme_name(self):
        self.assertEqual(custom_themes.theme_name("Pixel Consoles", "Gruvbox"), "Pixel Consoles - Gruvbox")

    def test_styles(self):
        self.assertEqual(custom_themes.styles(), ["Pixel Consoles", "Pixel Controllers"])
        for style, module in custom_themes.STYLES.items():
            self.assertEqual((module.STYLE, module.BASE), (style, "SPRUCE"))


class Recolor(unittest.TestCase):
    def test_recolor_config(self):
        p = palettes.get("Arcade")
        cfg = full_config()
        recolor.recolor_config(cfg, p)
        for key in ("batteryPercentage", "title", "hint", "currentpage"):
            self.assertEqual(cfg[key]["color"], p.text, key)
        self.assertEqual(cfg["total"]["color"], p.accent)
        self.assertEqual((cfg["grid"]["color"], cfg["grid"]["selectedcolor"]), (p.dim, p.accent))
        self.assertEqual((cfg["list"]["color"], cfg["list"]["selectedcolor"]), (p.list, p.selected))
        widgets = {w["type"]: w["color"] for w in cfg["screensaver"]["widgets"]}
        self.assertEqual(widgets, {"clock": p.selected, "date": p.text, "battery": p.accent})
        expected = full_config()
        for section in (cfg, expected):  # everything but the recolored values stays as it was
            for key in ("batteryPercentage", "title", "hint", "currentpage", "total"):
                section[key].pop("color")
            for key in ("grid", "list"):
                section[key].pop("color")
                section[key].pop("selectedcolor")
            for w in section["screensaver"]["widgets"]:
                w.pop("color")
        self.assertEqual(cfg, expected)

    def test_recolor_config_missing_sections(self):
        cfg = {"name": "x", "title": {"size": 3}, "screensaver": {"widgets": [{"type": "other", "color": "#000000"}]}}
        recolor.recolor_config(cfg, palettes.get("Arcade"))
        self.assertEqual(cfg["screensaver"]["widgets"][0]["color"], "#000000")
        self.assertEqual(cfg["title"]["color"], palettes.get("Arcade").text)
        recolor.recolor_config({}, palettes.get("Arcade"))

    def test_recolor_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            for folder in ("skin", "skin_720x480", "icons"):
                bar_png(os.path.join(tmp, folder, "bg-list-l.png"))
            with open(os.path.join(tmp, "icons", "bg-list-l.png"), "rb") as f:
                untouched = f.read()
            p = palettes.get("Famicom")
            recolor.recolor_bar(tmp, p)
            for folder in ("skin", "skin_720x480"):
                px = pixels(os.path.join(tmp, folder, "bg-list-l.png"))
                self.assertEqual(px[0, 0], (200, 10, 10, 255))
                self.assertEqual(px[1, 0], rgb(p.bar) + (128,))
                self.assertEqual(px[5, 2], rgb(p.bar) + (255,))
            with open(os.path.join(tmp, "icons", "bg-list-l.png"), "rb") as f:
                self.assertEqual(f.read(), untouched)


class Build(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(usersettings, "apply_settings"))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        palette_base(os.path.join(self.root, "os", "spruceos", "themes", "SPRUCE"))

    def test_build_two_palettes(self):
        out = os.path.join(self.tmp.name, "out")
        built = custom_themes.build(["Pixel Consoles"], [palettes.get("Gruvbox"), palettes.get("Candy")], out)
        self.assertEqual(list(built), ["Pixel Consoles - Gruvbox", "Pixel Consoles - Candy"])
        configs, icons = [], []
        for name, folder in built.items():
            self.assertEqual(folder, os.path.join(out, name))
            with open(os.path.join(folder, "config.json")) as f:
                config = json.load(f)
            self.assertEqual(config["name"], name)
            configs.append(config["title"]["color"])
            with open(os.path.join(folder, "config_720x480.json")) as f:
                self.assertEqual(json.load(f)["list"]["selectedcolor"], palettes.get(name.split(" - ")[1]).selected)
            with open(os.path.join(folder, "icons", "sel", "gba.png"), "rb") as f:
                icons.append(f.read())
            bar = rgb(palettes.get(name.split(" - ")[1]).bar)
            self.assertEqual(pixels(os.path.join(folder, "skin_720x480", "bg-list-l.png"))[5, 2], bar + (255,))
        self.assertNotEqual(configs[0], configs[1])
        self.assertEqual(icons[0], icons[1])

    def test_unknown_style_raises_keyerror(self):
        with self.assertRaises(KeyError):
            custom_themes.build(["Nope"], [palettes.get("Gruvbox")], os.path.join(self.tmp.name, "out"))

    def test_empty_palettes_raises_valueerror(self):
        with self.assertRaises(ValueError):
            custom_themes.build(None, [], os.path.join(self.tmp.name, "out"))


class Command(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(usersettings, "apply_settings"))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        make_base(os.path.join(self.root, "os", "spruceos", "themes", "SPRUCE"))
        self.out = os.path.join(self.tmp.name, "out")

    def test_duplicate_palette_flags_collapse(self):
        self.assertEqual(commands.run(["themes", "build", "--palette", "Arcade", "--palette", "Arcade", "--out", self.out]), 0)
        self.assertEqual(sorted(os.listdir(self.out)), ["Pixel Consoles - Arcade", "Pixel Controllers - Arcade"])

    def test_palette_order_kept(self):
        with mock.patch.object(custom_themes, "build", return_value={}) as build:
            commands.run(["themes", "build", "--palette", "NES", "--palette", "Arcade", "--palette", "NES"])
        self.assertEqual([p.name for p in build.call_args.args[1]], ["NES", "Arcade"])

    def test_all_palettes(self):
        with mock.patch.object(custom_themes, "build", return_value={}) as build:
            self.assertEqual(commands.run(["themes", "build", "Pixel Consoles", "--all-palettes"]), 0)
        self.assertEqual(build.call_args.args[0], ["Pixel Consoles"])
        self.assertEqual([p.name for p in build.call_args.args[1]], NAMES)

    def test_publish_all_palettes(self):
        with mock.patch.object(custom_themes, "publish", return_value=0) as publish:
            self.assertEqual(commands.run(["themes", "publish", "--all-palettes", "--dry-run"]), 0)
        self.assertIsNone(publish.call_args.args[0])
        self.assertEqual(len(publish.call_args.args[1]), 28)
        self.assertTrue(publish.call_args.args[2])

    def fails(self, argv):
        with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr") as err, \
                mock.patch.object(custom_themes, "build") as build, mock.patch.object(custom_themes, "publish") as publish:
            commands.run(argv)
        build.assert_not_called()
        publish.assert_not_called()
        return raised.exception.code, "".join(c.args[0] for c in err.write.call_args_list)

    def test_no_palette_exits_2(self):
        for command in ("build", "publish"):
            code, text = self.fails(["themes", command])
            self.assertEqual(code, 2)
            for word in ("--palette", "--all-palettes", "Gruvbox", "Monochrome"):
                self.assertIn(word, text)

    def test_unknown_palette_exits_2(self):
        code, text = self.fails(["themes", "build", "--palette", "Nope"])
        self.assertEqual(code, 2)
        self.assertIn("Nope", text)
        self.assertIn("Gruvbox", text)

    def test_unknown_style_lists_styles(self):
        code, text = self.fails(["themes", "publish", "Nope", "--palette", "Gruvbox"])
        self.assertEqual(code, 2)
        self.assertIn("Pixel Controllers", text)


T = "os/spruceos/themes/"


class Publish(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(usersettings, "apply_settings"))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(mock.patch.object(ui, "ASSUME_YES", True))
        make_base(os.path.join(self.root, "os", "spruceos", "themes", "SPRUCE"))

    def test_publish_two_palettes(self):
        mint = self.put(T + "Pixel Consoles - Mint/config.json", b"mint")
        custom_themes.manifest.update(lambda d: d.update({"Pixel Consoles - Mint": {"files": {"config.json": ["h" * 64, 4]}}}))
        chosen = [palettes.get("Gruvbox"), palettes.get("Candy")]
        self.assertEqual(custom_themes.publish(["Pixel Consoles"], chosen), 0)
        state = self.read_json(runtime.CUSTOM_THEMES_STATE)
        build = os.path.join(self.data, "cache", "themes", "build")
        for name in ("Pixel Consoles - Gruvbox", "Pixel Consoles - Candy"):
            tree = custom_themes.manifest.hash_tree(os.path.join(build, name))
            self.assertEqual(state[name]["files"], {rel: list(v) for rel, v in tree.items()})
            self.assertTrue(os.path.exists(os.path.join(self.root, T, name, "config.json")))
        self.assertEqual(state["Pixel Consoles - Mint"], {"files": {"config.json": ["h" * 64, 4]}})
        with open(mint, "rb") as f:
            self.assertEqual(f.read(), b"mint")
        self.assertEqual(os.listdir(os.path.dirname(mint)), ["config.json"])
        self.assertFalse(os.path.exists(os.path.join(self.root, T, "Pixel Controllers - Gruvbox")))
        before = copy.deepcopy(state)
        with mock.patch.object(upload, "run_uploads") as run:
            self.assertEqual(custom_themes.publish(["Pixel Consoles"], chosen), 0)
        run.assert_not_called()
        self.assertEqual(self.read_json(runtime.CUSTOM_THEMES_STATE), before)


class Names(unittest.TestCase):
    def test_theme_names_never_collide_with_old_folders(self):
        names = {custom_themes.theme_name(s, p) for s in custom_themes.styles() for p in palettes.names()}
        self.assertEqual(len(names), 56)
        self.assertFalse(names & set(custom_themes.styles()))
        self.assertTrue(all(re.fullmatch(r"Pixel (Consoles|Controllers) - .+", n) for n in names))


if __name__ == "__main__":
    unittest.main()
