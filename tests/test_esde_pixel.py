import contextlib
import importlib.util
import io
import os
import re
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)

from PIL import Image  # noqa: E402

from sync_roms import esde_pixel, frontend, ui  # noqa: E402
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


GAMELIST_TYPES = {"textlist", "image", "text", "datetime", "helpsystem"}


class GamelistView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dest = esde_build.build(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def parse(self, rel):
        return ET.parse(os.path.join(self.dest, rel)).getroot()

    def general(self):
        views = self.parse("theme.xml").findall("view[@name='gamelist']")
        self.assertEqual(len(views), 1)
        return views[0]

    def layout_view(self, ratio):
        views = self.parse(esde_build.layout_file(ratio)).findall("view[@name='gamelist']")
        self.assertEqual(len(views), 1, ratio)
        return views[0]

    def merged(self, ratio):
        """{(type, name): {property: value}}: theme.xml's gamelist view with the ratio's layout over it."""
        out = {}
        for view in (self.general(), self.layout_view(ratio)):
            for el in view:
                props = out.setdefault((el.tag, el.get("name")), {})
                props.update({child.tag: child.text for child in el})
        return out

    def test_gamelist_has_list_image_metadata(self):
        for ratio in esde_build.RATIOS:
            merged = self.merged(ratio)
            lists = [props for (tag, _), props in merged.items() if tag == "textlist"]
            self.assertEqual(len(lists), 1, ratio)
            images = [props for (tag, _), props in merged.items() if tag == "image"]
            self.assertTrue(any(p.get("imageType") == "miximage" for p in images), ratio)
            fields = {props.get("metadata") for (tag, _), props in merged.items() if tag in ("text", "datetime")}
            for field in ("genre", "players", "releasedate", "rating"):
                self.assertIn(field, fields, (ratio, field))
            self.assertEqual(merged[("datetime", "pixelReleased")]["metadata"], "releasedate")
            for key, props in merged.items():
                if props.get("visible") != "false":
                    self.assertIn("pos", props, (ratio, key))

    def test_list_colours(self):
        textlist = self.general().find("textlist")
        self.assertEqual(textlist.findtext("selectorColor"), "${pixelBar}")
        self.assertEqual(textlist.findtext("selectedColor"), "${pixelSelected}")
        self.assertEqual(textlist.findtext("primaryColor"), "${pixelList}")

    def test_labels_in_accent(self):
        labels = [el for el in self.general().findall("text") if el.get("name").endswith("Label")]
        self.assertEqual(len(labels), 4)
        for el in labels:
            self.assertEqual(el.findtext("color"), "${pixelAccent}", el.get("name"))
            self.assertTrue(el.findtext("text"), el.get("name"))

    def test_vertical_has_no_description(self):
        for ratio in esde_build.RATIOS:
            desc = self.merged(ratio)[("text", "pixelDescription")]
            self.assertEqual(desc["metadata"], "description")
            hidden = desc.get("visible") == "false"
            self.assertEqual(hidden, ratio == "5:3_vertical", ratio)

    def test_no_video(self):
        root = self.parse("theme.xml")
        self.assertEqual(root.findall(".//video"), [])
        for ratio in esde_build.RATIOS:
            self.assertEqual(self.parse(esde_build.layout_file(ratio)).findall(".//video"), [], ratio)

    def test_layout_elements_are_declared_in_theme_xml(self):
        declared = {(el.tag, el.get("name")) for el in self.general()}
        self.assertEqual({tag for tag, _ in declared}, GAMELIST_TYPES)
        for ratio in esde_build.RATIOS:
            self.assertEqual({(el.tag, el.get("name")) for el in self.layout_view(ratio)}, declared, ratio)

    def test_colours_are_variables(self):
        views = [self.general()] + [self.layout_view(ratio) for ratio in esde_build.RATIOS]
        for view in views:
            for el in view.iter():
                if el.tag == "color" or el.tag.endswith("Color"):
                    self.assertRegex(el.text, r"^\$\{pixel[A-Z]\w*\}$", el.tag)

    def test_layouts_hold_no_colours_or_paths(self):
        for ratio in esde_build.RATIOS:
            for el in self.layout_view(ratio).iter():
                self.assertFalse(el.tag == "color" or el.tag.endswith("Color") or el.tag.endswith("Path"), (ratio, el.tag))

    def test_font_paths_exist(self):
        for el in self.general().iter("fontPath"):
            self.assertTrue(os.path.isfile(os.path.join(self.dest, el.text)), el.text)

    def test_font_sizes_are_multiples_of_12(self):
        for ratio in esde_build.RATIOS:
            sizes = list(self.layout_view(ratio).iter("fontSize"))
            self.assertGreater(len(sizes), 0, ratio)
            for el in sizes:
                px = float(el.text) * FONT_REFERENCE[ratio]
                self.assertAlmostEqual(px / 12, round(px / 12), delta=0.01, msg=(ratio, px))
                self.assertGreaterEqual(round(px), 12, ratio)

    def test_boxes_stay_on_screen_and_apart(self):
        """The list, art, metadata rows and description lie on screen and don't overlap."""
        for ratio in esde_build.RATIOS:
            width, height = esde_build.SYSTEM_LAYOUTS[ratio].screen
            geo = esde_build.gamelist_geometry(ratio)
            boxes = [(name, box) for name, box in geo.items() if name != "help"]
            for name, (x, y, w, h) in boxes:
                self.assertGreaterEqual(x, 0, (ratio, name))
                self.assertGreaterEqual(y, 0, (ratio, name))
                self.assertLessEqual(x + w, width + 0.01, (ratio, name))
                self.assertLessEqual(y + h, height + 0.01, (ratio, name))
            for i, (a, (ax, ay, aw, ah)) in enumerate(boxes):
                for b, (bx, by, bw, bh) in boxes[i + 1:]:
                    apart = ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay
                    self.assertTrue(apart, (ratio, a, b))


class FourThreeSprites(unittest.TestCase):
    def test_sprite_pixels_are_whole_on_4_3_devices(self):
        """Selected and unfocused sprite pixels are whole screen pixels at 640x480, 960x720 and 1280x960."""
        lay = esde_build.SYSTEM_LAYOUTS["4:3"]
        for device_height in (480, 720, 960):
            factor = device_height / lay.screen[1]
            for size in (4 * lay.scale, 2 * lay.scale):  # sprite pixel in screen px: selected, unfocused
                self.assertEqual(size * factor, round(size * factor), (device_height, size))



def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def read(path):
    with open(path) as f:
        return f.read()


def files(folder):
    """{relative path with "/": bytes} of every file under folder."""
    out = {}
    for root, _, names in os.walk(folder):
        for name in names:
            path = os.path.join(root, name)
            with open(path, "rb") as f:
                out[os.path.relpath(path, folder).replace(os.sep, "/")] = f.read()
    return out


class Install(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(tempfile.TemporaryDirectory())
        self.warned = []
        self.enterContext(mock.patch.object(ui, "warn", self.warned.append))
        self.out = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.out))

    def copy(self, *rel):
        return os.path.join(self.base, "ES-DE", "themes", esde_build.THEME, *rel)

    def install(self):
        return esde_pixel.install("esde", self.base)

    def test_install_copies_theme_and_marker(self):
        self.assertTrue(self.install())
        self.assertEqual(esde_pixel.dest("esde", self.base), self.copy())
        got = files(self.copy())
        cached = files(esde_pixel.cached())
        self.assertEqual(got.keys(), cached.keys())
        self.assertEqual({k: v for k, v in got.items() if k != esde_pixel.MARKER},
                         {k: v for k, v in cached.items() if k != esde_pixel.MARKER})
        self.assertIn("theme.xml", got)
        self.assertIn("capabilities.xml", got)
        self.assertEqual(got[esde_pixel.MARKER].decode().strip(), esde_pixel.key())

    def test_second_install_changes_nothing(self):
        self.install()
        before = {p: os.stat(os.path.join(self.copy(), p)).st_mtime_ns for p in files(self.copy())}
        self.assertFalse(self.install())
        after = {p: os.stat(os.path.join(self.copy(), p)).st_mtime_ns for p in files(self.copy())}
        self.assertEqual(before, after)

    def test_stale_file_removed_but_collection_art_kept(self):
        self.install()
        write(self.copy("old", "gone.xml"), "<theme/>")
        write(self.copy("systems", "consoles", "OLD.png"), "x")
        write(self.copy(esde_pixel.OWNED), "my shmups\n")
        write(self.copy("systems", "consoles", "my shmups.png"), "art")
        write(self.copy("systems", "controllers", "My Shmups.png"), "art")  # cards ignore case
        write(self.copy("systems", "other", "my shmups.png"), "not ours")
        write(self.copy("My Shmups", "theme.xml"), "<theme/>")  # the collection's own theme folder
        write(self.copy("other", "theme.xml"), "<theme/>")
        os.remove(self.copy(esde_pixel.MARKER))  # an older build
        self.assertTrue(self.install())
        self.assertFalse(os.path.exists(self.copy("old")))
        self.assertFalse(os.path.exists(self.copy("systems", "consoles", "OLD.png")))
        self.assertFalse(os.path.exists(self.copy("systems", "other")))
        self.assertEqual(read(self.copy(esde_pixel.OWNED)), "my shmups\n")
        self.assertEqual(read(self.copy("systems", "consoles", "my shmups.png")), "art")
        self.assertEqual(read(self.copy("systems", "controllers", "My Shmups.png")), "art")
        self.assertEqual(read(self.copy("My Shmups", "theme.xml")), "<theme/>")
        self.assertFalse(os.path.exists(self.copy("other")))

    def test_stopped_copy_is_finished(self):
        self.install()
        os.remove(self.copy("theme.xml"))
        os.remove(self.copy(esde_pixel.MARKER))  # stopped before the marker, which is written last
        self.assertTrue(self.install())
        self.assertTrue(os.path.exists(self.copy("theme.xml")))
        self.assertEqual(read(self.copy(esde_pixel.MARKER)).strip(), esde_pixel.key())

    def test_an_older_marker_updates_and_says_so(self):
        self.install()
        write(self.copy(esde_pixel.MARKER), "old\n")
        esde_pixel.describe("esde", self.base)
        self.assertIn("🎨 would update Pixel for ES-DE in ES-DE/themes/pixel-sync-roms", self.out.getvalue())
        self.assertTrue(esde_pixel.step("esde", self.base, {}, False))
        self.assertIn("🎨 Updated Pixel for ES-DE", self.out.getvalue())

    def test_dry_run_names_the_install_and_writes_nothing(self):
        self.assertFalse(esde_pixel.step("esde", self.base, {}, True))
        self.assertIn("🎨 would install Pixel for ES-DE into ES-DE/themes/pixel-sync-roms", self.out.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.base, "ES-DE")))
        self.assertTrue(esde_pixel.step("esde", self.base, {}, False))
        self.assertIn("🎨 Installed Pixel for ES-DE", self.out.getvalue())
        self.out.truncate(0)
        self.out.seek(0)
        esde_pixel.describe("esde", self.base)  # current: nothing to say
        self.assertFalse(esde_pixel.step("esde", self.base, {}, False))
        self.assertEqual(self.out.getvalue(), "")

    def test_theme_flag_off_installs_nothing_and_keeps_existing(self):
        entry = {"theme": False}
        self.assertFalse(esde_pixel.step("esde", self.base, entry, False))
        self.assertFalse(esde_pixel.step("esde", self.base, entry, True))
        self.assertFalse(os.path.exists(self.copy()))
        write(self.copy("theme.xml"), "mine")
        write(self.copy("extra.txt"), "mine")
        self.assertFalse(esde_pixel.step("esde", self.base, entry, False))
        self.assertEqual(files(self.copy()), {"theme.xml": b"mine", "extra.txt": b"mine"})
        self.assertEqual(self.out.getvalue(), "")

    def test_other_layouts_get_nothing(self):
        for layout in ("knulli", "spruce", "nextui"):
            self.assertFalse(esde_pixel.step(layout, self.base, {}, False))
        self.assertEqual(os.listdir(self.base), [])

    def test_emudeck_problem_skips(self):
        roms = os.path.join(self.base, "Emulation", "roms")
        os.makedirs(roms)
        problem = frontend.emudeck_problem(self.base, roms)  # no ES-DE folder on this computer
        self.assertTrue(problem)
        skips = []
        for dry_run in (True, False):
            self.assertFalse(esde_pixel.step("emudeck", self.base, {}, dry_run, problem, skips.append))
        self.assertEqual(skips, [esde_pixel.LABEL] * 2)
        self.assertFalse(os.path.exists(frontend.esde_dir("emudeck", self.base)))
        self.assertEqual(os.listdir(self.base), ["Emulation"])

    def test_emudeck_installs_into_this_computer_s_es_de(self):
        es_dir = os.path.join(self.base, "machine-ES-DE")
        os.makedirs(es_dir)
        with mock.patch.dict(os.environ, {"ESDE_APPDATA_DIR": es_dir}):
            self.assertTrue(esde_pixel.step("emudeck", self.base, {}, False))
        self.assertTrue(os.path.exists(os.path.join(es_dir, "themes", esde_build.THEME, "theme.xml")))

    def test_never_touches_theme_setting(self):
        settings = frontend.settings_path("esde", self.base)
        for theme in ("", '<string name="Theme" value="art-book-next-sync-roms" />\n'):
            write(settings, f'<?xml version="1.0"?>\n{theme}')
            before = read(settings)
            esde_pixel.step("esde", self.base, {}, False)
            esde_pixel.step("esde", self.base, {}, True)
            self.assertEqual(read(settings), before)
        os.remove(settings)
        os.remove(self.copy(esde_pixel.MARKER))
        esde_pixel.install("esde", self.base)
        self.assertFalse(os.path.exists(settings))


class Cache(unittest.TestCase):
    def setUp(self):
        self.src = self.enterContext(tempfile.TemporaryDirectory())
        write(os.path.join(self.src, "code", "a.py"), "a")
        write(os.path.join(self.src, "code", "__pycache__", "a.cpython-312.pyc"), "compiled")
        write(os.path.join(self.src, "one.py"), "one")
        self.enterContext(mock.patch.object(esde_pixel, "SOURCES",
                                            (os.path.join(self.src, "code"), os.path.join(self.src, "one.py"))))
        self.built = []
        real = esde_build.build

        def counting(out_dir):
            self.built.append(out_dir)
            return real(out_dir)
        self.enterContext(mock.patch.object(esde_build, "build", counting))

    def test_cached_rebuilds_only_when_sources_change(self):
        path = esde_pixel.cached()
        self.assertEqual(path, os.path.join(esde_pixel.cache_root(), esde_build.THEME))
        self.assertTrue(os.path.exists(os.path.join(path, "theme.xml")))
        self.assertEqual(len(self.built), 1)
        self.assertEqual(esde_pixel.cached(), path)
        self.assertEqual(len(self.built), 1)
        write(os.path.join(self.src, "code", "__pycache__", "a.cpython-312.pyc"), "recompiled")  # not a source
        esde_pixel.cached()
        self.assertEqual(len(self.built), 1)
        write(os.path.join(self.src, "code", "a.py"), "b")
        esde_pixel.cached()
        self.assertEqual(len(self.built), 2)
        write(os.path.join(self.src, "code", "new.py"), "")
        esde_pixel.cached()
        self.assertEqual(len(self.built), 3)
        os.remove(os.path.join(path, esde_pixel.MARKER))  # a build stopped before its marker
        esde_pixel.cached()
        self.assertEqual(len(self.built), 4)
        os.remove(os.path.join(path, "theme.xml"))  # files gone from a build that has its marker
        esde_pixel.cached()
        self.assertEqual(len(self.built), 5)
        self.assertTrue(os.path.exists(os.path.join(path, "theme.xml")))
        esde_pixel.cached()
        self.assertEqual(len(self.built), 5)


class Sources(unittest.TestCase):
    def test_the_key_covers_the_build_s_inputs(self):
        sources = {os.path.normpath(p) for p in esde_pixel.SOURCES}
        root = os.path.dirname(esde_pixel.__file__)
        for rel in (("custom_themes", "esde"), ("custom_themes", "pixel"), ("custom_themes", "palettes.py"),
                    ("data", "themes", "fusion-pixel"), ("data", "themes", "art-book-next", "art-box", "Imgs"),
                    ("data", "systems.json")):
            self.assertIn(os.path.normpath(os.path.join(root, *rel)), sources)


if __name__ == "__main__":
    unittest.main()
