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
         "Solarized", "Synthwave", "Sunset", "Ocean", "Sakura", "Forest", "Grape",
         "Jigglypuff", "Pikachu", "Snorlax", "Bulbasaur", "Charmander", "Squirtle", "Eevee", "Monochrome"]


def full_config():
    text = {"font": "nunwen.ttf", "size": 25, "color": "#EBDBB2"}
    return {
        "name": "Spruce", "author": "tenlevels", "description": "x", "unrelated": {"color": "#123456"},
        "batteryPercentage": dict(text), "title": dict(text), "hint": dict(text, contextbuttons=True),
        "currentpage": dict(text), "total": dict(text, color="#D65D0E"),
        "grid": {"font": "nunwen.ttf", "grid1x4": 25, "grid3x4": 18, "color": "#7C6F64", "selectedcolor": "#FBF1C7"},
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
    bar_png(os.path.join(path, "skin", "div-line-h.png"))  # a frame file not redrawn: only recolored
    bar_png(os.path.join(path, "skin_720x480", "div-line-h.png"))


class Palettes(unittest.TestCase):
    def test_palettes_data(self):
        self.assertEqual(len(palettes.PALETTES), 35)
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
        self.assertEqual(custom_themes.styles(), ["Pixel Consoles", "Pixel Controllers", "ToTK - James", "ToTK - Kelsin"])
        for style, module in custom_themes.STYLES.items():
            self.assertEqual((module.STYLE, module.BASE), (style, "ToTK" if style.startswith("ToTK") else "SPRUCE"))


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
            self.assertEqual(pixels(os.path.join(folder, "skin_720x480", "div-line-h.png"))[5, 2], bar + (255,))
        self.assertNotEqual(configs[0], configs[1])
        self.assertEqual(icons[0], icons[1])

    def test_build_uses_the_pixel_font(self):
        base = os.path.join(self.root, "os", "spruceos", "themes", "SPRUCE")
        with open(os.path.join(base, "nunwen.ttf"), "wb") as f:
            f.write(b"font")
        folder = custom_themes.build(["Pixel Consoles"], [palettes.get("Gruvbox")], os.path.join(self.tmp.name, "out"))[
            "Pixel Consoles - Gruvbox"]
        font = "fusion-pixel-12px-proportional-ja.ttf"
        self.assertTrue(os.path.isfile(os.path.join(folder, font)))
        self.assertTrue(os.path.isfile(os.path.join(folder, "FONT-LICENSE.txt")))
        self.assertFalse(os.path.exists(os.path.join(folder, "nunwen.ttf")))
        with open(os.path.join(folder, "CREDITS.txt")) as f:
            self.assertIn("Fusion Pixel", f.read())

        def fonts(node):
            if isinstance(node, dict):
                yield from ([node] if "font" in node else [])
                for child in node.values():
                    yield from fonts(child)
            elif isinstance(node, list):
                for child in node:
                    yield from fonts(child)

        for file in ("config.json", "config_720x480.json"):
            with open(os.path.join(folder, file)) as f:
                config = json.load(f)
            found = list(fonts(config))
            self.assertEqual(len(found), 8, file)
            self.assertEqual({entry["font"] for entry in found}, {font}, file)
            sizes = [v for entry in found for k, v in entry.items() if k in ("size", "grid1x4", "grid3x4")]
            self.assertEqual(len(sizes), 8, file)
            self.assertLessEqual(set(sizes), {12, 24}, file)
            self.assertEqual((config["batteryPercentage"]["size"], config["title"]["size"], config["grid"]["grid1x4"],
                              config["grid"]["grid3x4"]), (24, 24, 24, 12), file)  # 25 and 18, rounded down

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
        make_base(os.path.join(self.root, "os", "spruceos", "themes", "ToTK"))
        self.out = os.path.join(self.tmp.name, "out")

    def test_duplicate_palette_flags_collapse(self):
        self.assertEqual(commands.run(["themes", "build", "--palette", "Arcade", "--palette", "Arcade", "--out", self.out]), 0)
        self.assertEqual(sorted(os.listdir(self.out)), ["Pixel Consoles - Arcade", "Pixel Controllers - Arcade", "ToTK - James", "ToTK - Kelsin"])

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
        self.assertEqual(len(publish.call_args.args[1]), 35)
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

    def test_palette_and_all_palettes_exclusive(self):
        for command in ("build", "publish"):
            code, text = self.fails(["themes", command, "--palette", "Arcade", "--all-palettes"])
            self.assertEqual(code, 2)
            self.assertIn("not allowed with", text)

    def test_duplicate_styles_collapse(self):
        import argparse
        args = argparse.Namespace(names=["Pixel Consoles", "Pixel Controllers", "Pixel Consoles"])
        self.assertEqual(commands.style_args(args), ["Pixel Consoles", "Pixel Controllers"])
        self.assertIsNone(commands.style_args(argparse.Namespace(names=[])))

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
        make_base(os.path.join(self.root, "os", "spruceos", "themes", "ToTK"))

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


    def test_old_single_palette_folder_left_alone(self):
        old = self.put(T + "Pixel Consoles/config.json", b"old")
        entry = {"files": {"config.json": ["a" * 64, 3]}}
        custom_themes.manifest.update(lambda d: d.update({"Pixel Consoles": copy.deepcopy(entry)}))
        chosen = [palettes.get("Gruvbox"), palettes.get("Candy")]
        self.assertEqual(custom_themes.publish(["Pixel Consoles"], chosen), 0)
        with open(old, "rb") as f:
            self.assertEqual(f.read(), b"old")
        self.assertEqual(os.listdir(os.path.dirname(old)), ["config.json"])
        state = self.read_json(runtime.CUSTOM_THEMES_STATE)
        self.assertEqual(state["Pixel Consoles"], entry)
        self.assertIn("Pixel Consoles - Gruvbox", state)

    def test_many_themes_one_line_each(self):
        stale = self.put(T + "Pixel Consoles - Gruvbox/old.png", b"x")
        custom_themes.manifest.update(lambda d: d.update({"Pixel Consoles - Gruvbox": {"files": {"old.png": ["b" * 64, 1]}}}))
        chosen = [palettes.get(n) for n in ("Gruvbox", "Candy", "Mint")]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            custom_themes.publish(None, chosen, dry_run=True)
        lines = out.getvalue().splitlines()
        names = [custom_themes.theme_name(s, p.name) for s in custom_themes.styles()[:2] for p in chosen]
        self.assertGreater(len(names), custom_themes.COMPACT_OVER)
        themed = [line for line in lines if line.startswith("🎨 Pixel ")]
        self.assertEqual(sorted(line.split(":")[0][2:] for line in themed), sorted(names))
        for line in themed:
            self.assertRegex(line, r"new \d+ \(.+\) · changed \d+ \(.+\) · same \d+ · stale \d+$")
        self.assertFalse([line for line in lines if "New:" in line])
        self.assertEqual(sum("old.png" in line for line in lines), 1)
        self.assertTrue(os.path.exists(stale))
        at = next(i for i, line in enumerate(lines) if line.startswith("🎨 Pixel Consoles - Gruvbox:"))
        self.assertIn("old.png", lines[at + 1])


class Names(unittest.TestCase):
    def test_theme_names_never_collide_with_old_folders(self):
        names = {custom_themes.theme_name(s, p) for s in custom_themes.styles()[:2] for p in palettes.names()}
        self.assertEqual(len(names), 70)
        self.assertFalse(names & set(custom_themes.styles()))
        self.assertTrue(all(re.fullmatch(r"Pixel (Consoles|Controllers) - .+", n) for n in names))


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


class PaletteSheet(helpers.StorageDir):
    def test_render_panel_size_and_colors(self):
        from sync_roms.custom_themes import palette_sheet
        from sync_roms.custom_themes.pixel import preview
        p = palettes.get("Gruvbox")
        img = palette_sheet.render_panel(p)
        self.assertEqual((img.size, img.mode), ((320, 240), "RGB"))
        half = lambda pt: (pt[0] // 2, pt[1] // 2)
        self.assertEqual(img.getpixel(half(preview.LAYOUT["row_bar"])), hexrgb(p.bar))
        self.assertEqual([img.getpixel(half(pt)) for pt in preview.LAYOUT["swatches"]],
                         [hexrgb(c) for c in (p.text, p.list, p.selected, p.accent, p.dim, p.bar)])

    def test_render_sheet_size(self):
        from sync_roms.custom_themes import palette_sheet
        img = palette_sheet.render_sheet(palettes.PALETTES.values())
        self.assertEqual(len(palettes.PALETTES), 35)
        self.assertEqual(img.size, (5 * 320 + 6 * 8, 7 * 240 + 8 * 8))
        self.assertEqual(img.getpixel((0, 0)), (28, 28, 28))

    def test_write_sheet_creates_png(self):
        from sync_roms.custom_themes import palette_sheet
        path = os.path.join(self.tmp.name, "a", "b", "palettes.png")
        self.assertEqual(palette_sheet.write_sheet(path), path)
        with Image.open(path) as img:
            self.assertEqual(img.format, "PNG")

    def test_font_path_is_the_bundled_font(self):
        from sync_roms.custom_themes import palette_sheet
        self.assertTrue(os.path.isfile(palette_sheet.font_path()))
        self.assertEqual(os.path.basename(palette_sheet.font_path()), "fusion-pixel-12px-proportional-ja.ttf")

    def test_palettes_command_opens_viewer(self):
        from sync_roms.custom_themes import palette_sheet
        path = os.path.join(self.data, "cache", "themes", "palettes.png")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("webbrowser.open", return_value=True) as opened:
            self.assertEqual(commands.run(["themes", "palettes"]), 0)
        self.assertIn(path, out.getvalue())
        self.assertTrue(os.path.isfile(path))
        opened.assert_called_once()
        with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr") as err, \
                contextlib.redirect_stdout(io.StringIO()), mock.patch("webbrowser.open", return_value=False):
            commands.run(["themes", "palettes"])
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("open the file above yourself", "".join(c.args[0] for c in err.write.call_args_list))


class PaletteSheetErrors(helpers.StorageDir):
    def test_write_sheet_is_atomic(self):
        from sync_roms.custom_themes import palette_sheet
        folder = os.path.join(self.tmp.name, "sheet")
        os.makedirs(folder)
        path = os.path.join(folder, "palettes.png")
        with open(path, "wb") as f:
            f.write(b"old")

        def half_written(image, fp, *args, **kwargs):
            with open(fp, "wb") as f:
                f.write(b"partial")
            raise OSError("disk full")
        with mock.patch.object(Image.Image, "save", half_written), self.assertRaises(OSError):
            palette_sheet.write_sheet(path)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"old")
        self.assertEqual(os.listdir(folder), ["palettes.png"])

    def test_palettes_command_write_error_exits_1(self):
        from sync_roms.custom_themes import palette_sheet
        with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr") as err, \
                contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(palette_sheet, "write_sheet", side_effect=OSError(28, "No space left on device")), \
                mock.patch("webbrowser.open") as opened:
            commands.run(["themes", "palettes"])
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("No space left on device", "".join(c.args[0] for c in err.write.call_args_list))
        opened.assert_not_called()


class Picker(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        from sync_roms.custom_themes import palette_picker
        self.pp = palette_picker

    def test_swatches(self):
        p = palettes.get("Famicom")
        parts = self.pp.swatches(p)
        colors = [p.text, p.list, p.selected, p.accent, p.dim, p.bar]
        self.assertEqual(len(parts), 6)
        for (text, style), color in zip(parts, colors):
            self.assertEqual(text, "  ")
            self.assertEqual(style, f"{color} on {color}")

    def test_pick_passes_rows_and_returns_names(self):
        calls = []

        def fake(title, labels, **kw):
            calls.append((title, labels, kw))
            return [n in ("Candy", "Gruvbox", "Monochrome") for n in labels]
        with mock.patch.object(self.pp.picker, "filter_list", side_effect=fake):
            got = self.pp.pick("Palettes", ["Monochrome", "Candy"])
        self.assertEqual(got, ["Gruvbox", "Candy", "Monochrome"])
        title, labels, kw = calls[0]
        self.assertEqual(title, "Palettes")
        self.assertEqual(labels, NAMES)
        self.assertTrue(kw["multi"])
        self.assertEqual(kw["initial"], [n in ("Candy", "Monochrome") for n in NAMES])
        self.assertEqual(kw["extras"], [self.pp.swatches(palettes.get(n)) for n in NAMES])
        self.assertTrue(kw["hint"])
        self.assertIs(kw["esc_asks"], False)
        path = kw["preview"](0)
        self.assertEqual(path, os.path.join(self.data, "cache", "themes", "palette-previews", "Gruvbox.png"))
        with Image.open(path) as img:
            self.assertEqual((img.format, img.size), ("PNG", (320, 240)))
        with mock.patch.object(self.pp.picker, "filter_list", return_value=None):
            self.assertIsNone(self.pp.pick("Palettes", []))

    def test_saved_drops_unknown_names(self):
        self.assertEqual(self.pp.saved(), [])
        usersettings.save_settings({"custom_theme_palettes": ["Nope", "Candy", 3, "Arcade"]})
        self.assertEqual(self.pp.saved(), ["Arcade", "Candy"])
        usersettings.save_settings({"custom_theme_palettes": "Candy"})
        self.assertEqual(self.pp.saved(), [])

    def test_save_roundtrip_sorted(self):
        usersettings.save_settings({"bucket": "b"})
        self.pp.save(["Monochrome", "Gruvbox", "Candy"])
        self.assertEqual(usersettings.load_settings()["custom_theme_palettes"], ["Gruvbox", "Candy", "Monochrome"])
        self.assertEqual(usersettings.load_settings()["bucket"], "b")
        self.assertEqual(self.pp.saved(), ["Gruvbox", "Candy", "Monochrome"])


from sync_roms import picker  # noqa: E402
from sync_roms.custom_themes import palette_picker as _palette_picker  # noqa: E402

real_pick = _palette_picker.pick


class PaletteArgs(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        from sync_roms.custom_themes import palette_picker
        self.pp = palette_picker
        self.enterContext(mock.patch.object(ui, "ASSUME_YES", False))
        self.terminal = self.enterContext(mock.patch.object(ui, "has_terminal", return_value=False))
        self.picked = self.enterContext(mock.patch.object(palette_picker, "pick"))

    def args(self, palette=None, all_palettes=False):
        import argparse
        return argparse.Namespace(palette=palette, all_palettes=all_palettes)

    def names(self, chosen):
        return [p.name for p in chosen]

    def exits(self, args):
        with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr") as err, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            commands.palette_args(args)
        return raised.exception.code, "".join(c.args[0] for c in err.write.call_args_list) + out.getvalue()

    def test_palette_args_prefers_flags_over_saved(self):
        self.pp.save(["Candy"])
        self.terminal.return_value = True
        self.assertEqual(self.names(commands.palette_args(self.args(["NES"]))), ["NES"])
        self.assertEqual(len(commands.palette_args(self.args(all_palettes=True))), 35)
        self.picked.assert_not_called()
        self.assertEqual(self.pp.saved(), ["Candy"])

    def test_palette_args_uses_saved_without_terminal_or_yes(self):
        self.pp.save(["Mint", "Arcade"])
        self.assertEqual(self.names(commands.palette_args(self.args())), ["Arcade", "Mint"])
        self.terminal.return_value = True
        with mock.patch.object(ui, "ASSUME_YES", True):
            self.assertEqual(self.names(commands.palette_args(self.args())), ["Arcade", "Mint"])
        self.picked.assert_not_called()

    def test_palette_args_none_saved_exits_2(self):
        code, text = self.exits(self.args())
        self.assertEqual(code, 2)
        for word in ("--palette", "--all-palettes", "Gruvbox", "Monochrome"):
            self.assertIn(word, text)

    def test_palette_args_runs_picker_with_terminal_and_saves(self):
        self.pp.save(["Candy"])
        self.terminal.return_value = True
        self.picked.return_value = ["Arcade", "Sakura"]
        chosen = commands.palette_args(self.args())
        self.assertEqual(chosen, [palettes.get("Arcade"), palettes.get("Sakura")])
        self.assertEqual(self.picked.call_args.args[1], ["Candy"])
        self.assertEqual(self.pp.saved(), ["Arcade", "Sakura"])

    def test_palette_args_cancel_does_not_save(self):
        self.pp.save(["Candy"])
        self.terminal.return_value = True
        self.picked.return_value = None
        code, text = self.exits(self.args())
        self.assertEqual(code, 0)
        self.assertIn("cancel", text.lower())
        self.assertEqual(self.pp.saved(), ["Candy"])

    def test_esc_in_the_real_list_cancels_without_saving(self):
        self.pp.save(["Candy"])
        self.terminal.return_value = True

        def run(model):  # the list's own model: toggle a row, then Esc
            for k in ("space", "escape"):
                got = model.key(k)
                if got is not picker.KEEP:
                    return got
            raise AssertionError("the list is still open after Esc")
        with mock.patch.object(self.pp, "pick", real_pick), mock.patch.object(picker, "_run", run), \
                mock.patch.object(picker, "_draws_images", return_value=False):
            code, text = self.exits(self.args())
        self.assertEqual(code, 0)
        self.assertIn("cancel", text.lower())
        self.assertEqual(self.pp.saved(), ["Candy"])

    def test_palette_args_nothing_chosen_exits_2(self):
        self.pp.save(["Candy"])
        self.terminal.return_value = True
        self.picked.return_value = []
        code, text = self.exits(self.args())
        self.assertEqual(code, 2)
        self.assertIn("no palette chosen", text.lower())
        self.assertEqual(self.pp.saved(), ["Candy"])


def visible_backgrounds(app, row):
    """The colors a terminal shows behind each blank run of a list row: reverse swaps foreground and background."""
    lines = app.screen_stack[0].query_one("_ListLines")
    strip = lines.render_lines(lines.region.at_offset((0, 0)))[row]
    shown = []
    for s in strip:
        if s.text.strip() or not s.style:
            continue
        color = s.style.color if s.style.reverse else s.style.bgcolor
        shown.append(color.name if color else None)
    return shown


class SwatchRendering(unittest.TestCase):
    """The swatch is visible on a plain row and on the highlighted one (which the list draws reversed)."""

    def shown(self, style):
        rows = {}

        async def script(pilot):
            await pilot.pause()
            rows["cur"], rows["other"] = visible_backgrounds(pilot.app, 0), visible_backgrounds(pilot.app, 1)
            await pilot.press("escape")
        with mock.patch.object(ui, "has_terminal", return_value=True):
            helpers.pilot_list(script, "t", ["a", "b"], multi=True, esc_asks=False,
                               extras=[[("  ", style)], [("  ", style)]])
        return rows

    def test_background_only_is_lost_on_the_highlighted_row(self):
        rows = self.shown("on #ff0000")
        self.assertIn("#ff0000", rows["other"])
        self.assertNotIn("#ff0000", rows["cur"])

    def test_swatch_style_shows_on_both_rows(self):
        from sync_roms.custom_themes import palette_picker
        style = palette_picker.swatches(palettes.Palette("x", *["#FF0000"] * 6))[0][1]
        rows = self.shown(style)
        self.assertIn("#ff0000", rows["other"])
        self.assertIn("#ff0000", rows["cur"])


if __name__ == "__main__":
    unittest.main()
