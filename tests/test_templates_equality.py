import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402
from test_custom_themes import CONFIG  # noqa: E402
from test_frames import make_base  # noqa: E402

from sync_roms.custom_themes import palettes, templates  # noqa: E402
from sync_roms.custom_themes.pixel import frames, recipe, recolor  # noqa: E402

RICH = dict(CONFIG, title={"color": "#111111", "x": 1}, list={"selectedcolor": "#222222"}, grid={}, hint="notadict",
            screensaver={"bgColor": "#282828", "widgets": [
                {"type": "clock", "color": "#333333", "size": 3}, {"type": "date"}, {"type": "battery", "color": "x"},
                {"type": "weather", "color": "#444444"}, "junk"]})
NO_PARENTS = {"name": "x", "screensaver": {"widgets": "nope"}}


def old_recolor_config(config, palette):
    def paint(key, **colors):
        section = config.get(key)
        if isinstance(section, dict):
            section.update(colors)
    for key in ("batteryPercentage", "title", "hint", "currentpage"):
        paint(key, color=palette.text)
    paint("total", color=palette.accent)
    paint("grid", color=palette.dim, selectedcolor=palette.accent)
    paint("list", color=palette.list, selectedcolor=palette.selected)
    widgets = {"clock": palette.selected, "date": palette.text, "battery": palette.accent}
    screensaver = config.get("screensaver")
    for widget in screensaver.get("widgets", []) if isinstance(screensaver, dict) else []:
        if isinstance(widget, dict) and widget.get("type") in widgets:
            widget["color"] = widgets[widget["type"]]


def old_igm_config(palette, font):
    return {
        "name": palette.name,
        "colors": {
            "dim_bg": "#000000E6",
            "panel_bg": "#00000000",
            "selection": palette.bar + "FF",
            "accent": palette.accent + "FF",
            "title_line": palette.dim + "FF",
            "text": palette.list + "FF",
            "text_selected": palette.selected + "FF",
            "text_title": palette.text + "FF",
            "text_shadow": "#00000000",
            "battery": palette.text + "FF",
        },
        "layout": {"shadow": False},
        "font": {"path": font, "size_small_pct": 5.0},
    }


def colors_of(palette):
    return {role: getattr(palette, role) for role in recipe.ROLES}


def rgba(path):
    with Image.open(path) as im:
        return im.size, im.convert("RGBA").tobytes()


class SetPathTests(unittest.TestCase):
    def test_sets_where_parent_exists(self):
        data = {"a": {"b": 1}, "w": [{"t": "x"}, {"t": "y"}, {"t": "x"}, "junk"]}
        self.assertTrue(recolor.set_path(data, "a.c", 2))
        self.assertEqual(data["a"], {"b": 1, "c": 2})
        self.assertTrue(recolor.set_path(data, "w[t=x].k", 3))
        self.assertEqual(data["w"], [{"t": "x", "k": 3}, {"t": "y"}, {"t": "x", "k": 3}, "junk"])

    def test_false_and_nothing_created_when_parent_missing(self):
        data = {"a": 1, "w": [{"t": "y"}]}
        before = copy.deepcopy(data)
        for path in ("b.c", "a.c", "w[t=x].k", "z[t=x].k"):
            self.assertFalse(recolor.set_path(data, path, 1), path)
        self.assertEqual(data, before)


class EqualityTests(unittest.TestCase):
    def test_recolor_config_unchanged(self):
        for config in (CONFIG, RICH, NO_PARENTS, {}):
            for name in palettes.names():
                p = palettes.get(name)
                new, old = copy.deepcopy(config), copy.deepcopy(config)
                recolor.recolor_config(new, p)
                old_recolor_config(old, p)
                self.assertEqual(json.dumps(new), json.dumps(old), name)

    def test_igm_config_unchanged(self):
        for name in palettes.names():
            p = palettes.get(name)
            self.assertEqual(json.dumps(recolor.igm_config(p, "f.ttf")), json.dumps(old_igm_config(p, "f.ttf")), name)

    def test_frame_templates_match_every_palette(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = os.path.join(tmp, "first")
            make_base(first)
            recipes = {}
            frames.apply(first, palettes.get("Gruvbox"), recipes=recipes)
            self.assertTrue(recipes)
            data = {k: templates.from_canvas(c) for k, c in recipes.items()}
            for name in palettes.names():
                p = palettes.get(name)
                theme = os.path.join(tmp, "t")
                make_base(theme)
                written = frames.apply(theme, p, recipes={})
                self.assertEqual(sorted(written), sorted(data), name)
                for k in written:
                    w, h, pixels = templates.render(data[k], colors_of(p))
                    self.assertEqual(((w, h), pixels), rgba(os.path.join(theme, k)), f"{name} {k}")
                shutil.rmtree(theme)

    def test_bar_templates_match_every_palette(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src.png")
            img = Image.new("RGBA", (6, 4), (0, 0, 0, 0))
            for x in range(6):
                img.putpixel((x, 0), recolor.BAR_GRAY + (255,))
                img.putpixel((x, 1), recolor.BAR_GRAY + (100,))
                img.putpixel((x, 2), (10, 20, 30, 255))
            img.save(src)
            data = templates.from_bar_image(src)
            self.assertIsNotNone(data)
            for name in palettes.names():
                p = palettes.get(name)
                theme = os.path.join(tmp, "t", "skin")
                os.makedirs(theme, exist_ok=True)
                out = os.path.join(theme, "x.png")
                img.save(out)
                recolor.recolor_bar(os.path.dirname(theme), p)
                self.assertEqual(templates.render(data, colors_of(p))[2], rgba(out)[1], name)


if __name__ == "__main__":
    unittest.main()
