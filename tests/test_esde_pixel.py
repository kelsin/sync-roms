import importlib.util
import os
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)

from PIL import Image  # noqa: E402

from sync_roms.custom_themes import palettes  # noqa: E402
from sync_roms.custom_themes.esde import build as esde_build  # noqa: E402
from sync_roms.custom_themes.esde import systems as esde_systems  # noqa: E402
from sync_roms.custom_themes.pixel import build as pixel_build  # noqa: E402
from sync_roms.custom_themes.pixel.sprite import Sprite  # noqa: E402


class SystemsMap(unittest.TestCase):
    def test_every_esde_system_is_mapped_or_pending(self):
        names = set(esde_systems.esde_names())
        mapped = set(esde_systems.ICONS) | set(esde_systems.EXTRA)
        self.assertEqual(names - mapped, esde_systems.PENDING)

    def test_pending_and_mapped_are_disjoint(self):
        self.assertFalse(esde_systems.PENDING & (set(esde_systems.ICONS) | set(esde_systems.EXTRA)))

    def test_icons_point_at_drawn_sprites(self):
        for kind in ("CONSOLES", "CONTROLLERS"):
            drawn = pixel_build.systems(kind)
            for name, icon in esde_systems.ICONS.items():
                self.assertIn(icon, drawn, (kind, name))

    def test_sprites_render(self):
        for kind in ("CONSOLES", "CONTROLLERS"):
            for name, draw in esde_systems.sprites(kind).items():
                self.assertIsInstance(draw(), Sprite, (kind, name))

    def test_reuse(self):
        self.assertEqual(esde_systems.ICONS["mame-advmame"], esde_systems.ICONS["mame"])
        self.assertEqual(esde_systems.ICONS["naomi2"], "naomi")
        self.assertEqual(esde_systems.ICONS["naomigd"], "naomi")
        self.assertEqual(esde_systems.ICONS["msx2"], "msx")
        self.assertEqual(esde_systems.ICONS["fbneo"], "arcade")
        self.assertIn("mark3", esde_systems.EXTRA)


def existing_range():
    """The smallest and largest width or height of the Spruce set's sprites, both kinds."""
    sizes = []
    for kind in ("CONSOLES", "CONTROLLERS"):
        for draw in pixel_build.systems(kind).values():
            x0, y0, x1, y1 = draw().bounds()
            sizes += [x1 - x0, y1 - y0]
    return min(sizes), max(sizes)


class Batches(unittest.TestCase):
    def assert_drawn(self, names):
        low, high = existing_range()
        for name in names:
            self.assertIn(name, esde_systems.EXTRA, name)
            self.assertNotIn(name, esde_systems.PENDING, name)
            for kind in ("CONSOLES", "CONTROLLERS"):
                sprite = esde_systems.EXTRA[name][kind]()
                self.assertIsInstance(sprite, Sprite, (name, kind))
                x0, y0, x1, y1 = sprite.bounds()
                for size in (x1 - x0, y1 - y0):
                    self.assertGreaterEqual(size, low, (name, kind))
                    self.assertLessEqual(size, high, (name, kind))

    def test_batch_3_drawn(self):
        self.assert_drawn(["gc", "wii", "wiiu", "switch", "n64dd"])

    def test_batch_4_drawn(self):
        self.assert_drawn(["ps2", "ps3", "ps4", "psvita", "xbox", "xbox360", "xboxone"])

    def test_batch_5_drawn(self):
        self.assert_drawn(["3do", "cdimono1", "pcfx", "atarijaguarcd", "arcadia", "gamecom", "uzebox"])

    def test_batch_6_drawn(self):
        self.assert_drawn(["model2", "model3", "stv", "triforce", "type-x", "daphne", "lowresnx", "lutro"])

    def test_nothing_pending(self):
        self.assertEqual(esde_systems.PENDING, set())


def load_tool(name):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SpriteSheet(unittest.TestCase):
    def test_sheet_has_a_row_per_name_and_the_reference_row(self):
        tool = load_tool("esde_sprite_sheet")
        img = tool.sheet(["gb", "nes"])
        self.assertEqual(img.height, 3 * tool.ROW)
        self.assertGreaterEqual(img.width, 4 * tool.CELL)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower())


def tree_bytes(root):
    out = {}
    for base, _dirs, files in os.walk(root):
        for file in files:
            path = os.path.join(base, file)
            with open(path, "rb") as f:
                out[os.path.relpath(path, root)] = f.read()
    return out


class ThemeFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dest = esde_build.build(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def parse(self, rel):
        return ET.parse(os.path.join(self.dest, rel)).getroot()

    def test_build_returns_the_theme_folder(self):
        self.assertEqual(self.dest, os.path.join(self.tmp.name, "pixel-sync-roms"))
        self.assertEqual(esde_build.THEME, "pixel-sync-roms")
        for rel in ("capabilities.xml", "theme.xml", "art/tile.png", "README.md",
                    "font/fusion-pixel-12px-proportional-ja.ttf", "font/OFL.txt"):
            self.assertTrue(os.path.isfile(os.path.join(self.dest, rel)), rel)

    def test_capabilities_declares_variants_schemes_ratios(self):
        root = self.parse("capabilities.xml")
        self.assertEqual(root.tag, "themeCapabilities")
        self.assertEqual(root.findtext("themeName"), "Pixel")
        variants = {v.get("name"): v for v in root.findall("variant")}
        self.assertEqual(set(variants), {"consoles", "controllers"})
        self.assertEqual(variants["consoles"].findtext("label"), "Consoles")
        self.assertEqual(variants["controllers"].findtext("label"), "Controllers")
        for v in variants.values():
            self.assertEqual(v.findtext("selectable"), "true")
        schemes = {c.get("name"): c.findtext("label") for c in root.findall("colorScheme")}
        self.assertEqual(len(palettes.PALETTES), 35)
        self.assertEqual(len(root.findall("colorScheme")), 35)
        self.assertEqual(schemes, {slug(name): name for name in palettes.PALETTES})
        self.assertEqual({a.text for a in root.findall("aspectRatio")}, set(esde_build.RATIOS))

    def test_every_scheme_sets_every_colour(self):
        root = self.parse("theme.xml")
        schemes = {c.get("name"): c for c in root.findall("colorScheme")}
        self.assertEqual(set(schemes), {slug(name) for name in palettes.PALETTES})
        for name, palette in palettes.PALETTES.items():
            variables = schemes[slug(name)].find("variables")
            for field in ("text", "list", "selected", "accent", "dim", "bar"):
                key = "pixel" + field.capitalize()
                self.assertEqual(variables.findtext(key), getattr(palette, field).lstrip("#").upper() + "FF", (name, key))
        self.assertEqual(schemes["snes"].find("variables").findtext("pixelBar"), "5B50D8FF")

    def test_every_system_has_both_sprites(self):
        for name in esde_systems.esde_names():
            for folder in ("consoles", "controllers"):
                with Image.open(os.path.join(self.dest, "systems", folder, f"{name}.png")) as im:
                    self.assertEqual(im.size, pixel_build.ICON_SIZE, (folder, name))

    def test_variant_paths(self):
        root = self.parse("theme.xml")
        variants = {v.get("name"): v for v in root.findall("variant")}
        self.assertEqual(variants["consoles"].find("variables").findtext("pixelSystemArt"),
                         "./systems/consoles/${system.theme}.png")
        self.assertEqual(variants["controllers"].find("variables").findtext("pixelSystemArt"),
                         "./systems/controllers/${system.theme}.png")

    def test_every_ratio_has_a_layout(self):
        root = self.parse("theme.xml")
        includes = {a.get("name"): a.findtext("include") for a in root.findall("aspectRatio")}
        self.assertEqual(set(includes), set(esde_build.RATIOS))
        for ratio, include in includes.items():
            rel = "layouts/" + ratio.replace(":", "-").replace(".", "-") + ".xml"
            self.assertEqual(include, "./" + rel)
            self.assertEqual(self.parse(rel).tag, "theme")

    def test_every_xml_parses(self):
        count = 0
        for rel in tree_bytes(self.dest):
            if rel.endswith(".xml"):
                self.parse(rel)
                count += 1
        self.assertEqual(count, 2 + len(esde_build.RATIOS))

    def test_build_is_deterministic(self):
        with tempfile.TemporaryDirectory() as other:
            again = esde_build.build(other)
            self.assertEqual(tree_bytes(again), tree_bytes(self.dest))

    def test_build_replaces_the_folder(self):
        with tempfile.TemporaryDirectory() as other:
            stale = os.path.join(other, "pixel-sync-roms", "stale.txt")
            os.makedirs(os.path.dirname(stale))
            open(stale, "w").close()
            esde_build.build(other)
            self.assertFalse(os.path.exists(stale))


# The screen size in pixels that ES-DE's fontSize is a fraction of: the height, or the width on a vertical screen.
FONT_REFERENCE = {"16:9": 1080, "16:10": 800, "4:3": 960, "3:2": 640, "1:1": 720, "8:7": 1080, "5:3_vertical": 480}


class SystemView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dest = esde_build.build(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def parse(self, rel):
        return ET.parse(os.path.join(self.dest, rel)).getroot()

    def system_views(self):
        """Every `<view name="system">` of theme.xml (general and per variant) and the layout files."""
        root = self.parse("theme.xml")
        views = root.findall("view[@name='system']") + root.findall("variant/view[@name='system']")
        for ratio in esde_build.RATIOS:
            views += self.parse(esde_build.layout_file(ratio)).findall("view[@name='system']")
        return views

    def test_carousel_per_ratio(self):
        for ratio in esde_build.RATIOS:
            views = self.parse(esde_build.layout_file(ratio)).findall("view[@name='system']")
            self.assertEqual(len(views), 1, ratio)
            carousels = views[0].findall("carousel")
            self.assertEqual(len(carousels), 1, ratio)
            want = "vertical" if ratio == "5:3_vertical" else "horizontal"
            self.assertEqual(carousels[0].findtext("type"), want, ratio)

    def test_colours_are_variables(self):
        seen = 0
        for view in self.system_views():
            for el in view.iter():
                if el.tag == "color" or el.tag.endswith("Color"):
                    self.assertRegex(el.text, r"^\$\{pixel[A-Z]\w*\}$", el.tag)
                    seen += 1
        self.assertGreater(seen, 0)

    def test_colour_variables_exist(self):
        root = self.parse("theme.xml")
        names = {el.tag for el in root.find("variables")}
        names |= {el.tag for el in root.find("colorScheme/variables")}
        for view in self.system_views():
            for el in view.iter():
                for var in re.findall(r"\$\{(pixel\w*)\}", el.text or ""):
                    self.assertTrue(var in names or var == "pixelSystemArt", var)

    def test_paths_only_in_theme_xml(self):
        """`./` paths resolve from the file they are in, so the layout files hold none."""
        for ratio in esde_build.RATIOS:
            for el in self.parse(esde_build.layout_file(ratio)).iter():
                self.assertNotIn("./", el.text or "", (ratio, el.tag))
                self.assertNotIn("pixelSystemArt", el.text or "", (ratio, el.tag))

    def test_system_art_is_set_per_variant(self):
        root = self.parse("theme.xml")
        for view in root.findall("view"):
            self.assertNotIn("pixelSystemArt", ET.tostring(view, encoding="unicode"))
        for name in esde_build.VARIANTS:
            carousel = root.find(f"variant[@name='{name}']/view[@name='system']/carousel[@name='systemCarousel']")
            self.assertEqual(carousel.findtext("staticImage"), "${pixelSystemArt}", name)

    def test_paths_exist(self):
        root = self.parse("theme.xml")
        for el in root.iter():
            if el.tag in ("path", "fontPath"):
                self.assertTrue(os.path.isfile(os.path.join(self.dest, el.text)), el.text)

    def test_layout_elements_are_declared_in_theme_xml(self):
        """A layout only places elements theme.xml declares (same type and name), so they merge."""
        declared = {(el.tag, el.get("name")) for el in self.parse("theme.xml").find("view[@name='system']")}
        for ratio in esde_build.RATIOS:
            view = self.parse(esde_build.layout_file(ratio)).find("view[@name='system']")
            self.assertEqual({(el.tag, el.get("name")) for el in view}, declared, ratio)

    def test_sprites_stay_crisp(self):
        general = self.parse("theme.xml").find("view[@name='system']")
        self.assertEqual(general.find("carousel").findtext("imageInterpolation"), "nearest")
        self.assertEqual(general.find("image[@name='pixelTile']").findtext("interpolation"), "nearest")

    def test_font_sizes_land_on_twelves(self):
        for ratio in esde_build.RATIOS:
            for el in self.parse(esde_build.layout_file(ratio)).iter("fontSize"):
                px = float(el.text) * FONT_REFERENCE[ratio]
                self.assertAlmostEqual(px / 12, round(px / 12), delta=0.01, msg=(ratio, px))
                self.assertGreaterEqual(round(px), 12, ratio)


if __name__ == "__main__":
    unittest.main()
