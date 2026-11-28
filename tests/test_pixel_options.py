import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402
from test_custom_themes import make_base as make_theme_base  # noqa: E402
from test_frames import make_base as make_frames_base  # noqa: E402
from test_frames import synthetic  # noqa: E402

from sync_roms import custom_themes  # noqa: E402
from sync_roms.custom_themes import palettes, pixel_options, templates  # noqa: E402
from sync_roms.custom_themes.pixel import recipe, recolor  # noqa: E402

ROOT = []


def make_base(path):
    """The custom themes' fake base with the frames' skins, and skin files that aren't frames but show the bar gray."""
    make_theme_base(path)
    make_frames_base(path)
    synthetic(os.path.join(path, "skin", "extra-bar.png"), (40, 20), (2, 2, 30, 15))
    synthetic(os.path.join(path, "skin_1280x720", "extra-bar.png"), (60, 30), (3, 3, 45, 22))


def setUpModule():
    root = tempfile.mkdtemp()
    ROOT.append(root)
    base = os.path.join(root, "base")
    make_base(base)
    ROOT.append(pixel_options.build(base, os.path.join(root, "out")))
    ROOT.append(custom_themes.pixel_consoles.build(base, os.path.join(root, "legacy"), palettes.get("Gruvbox")))
    ROOT.append(custom_themes.pixel_controllers.build(base, os.path.join(root, "legacy"), palettes.get("Nord")))


def tearDownModule():
    shutil.rmtree(ROOT[0], ignore_errors=True)
    ROOT.clear()


def tree(root, skip_options=True):
    out = []
    for dirpath, dirs, files in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        if skip_options and rel_dir == ".":
            dirs[:] = [d for d in dirs if d != "options"]
        for file in files:
            out.append(file if rel_dir == "." else f"{rel_dir}/{file}")
    return sorted(out)


def rgba(path):
    with Image.open(path) as im:
        return im.size, im.convert("RGBA").tobytes()


def apply(theme_dir, variant, palette):
    """The theme options format's apply algorithm (docs/theme-options-format.md), as the device runs it."""
    options = os.path.join(theme_dir, "options")
    with open(os.path.join(options, "manifest.json")) as f:
        manifest = json.load(f)
    colors = {role: getattr(palette, role) for role in recipe.ROLES}
    variant_dir = os.path.join(options, "variants", variant)
    for rel in tree(variant_dir, skip_options=False):
        target = os.path.join(theme_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(variant_dir, *rel.split("/")), target)
    template_dir = os.path.join(options, "templates")
    for rel in tree(template_dir, skip_options=False):
        with open(os.path.join(template_dir, *rel.split("/")), "rb") as f:
            w, h, pixels = templates.render(f.read(), colors)
        Image.frombytes("RGBA", (w, h), pixels).save(os.path.join(theme_dir, *rel[:-len(".tpl")].split("/")))
    for file in os.listdir(theme_dir):
        if file.startswith("config") and file.endswith(".json"):
            path = os.path.join(theme_dir, file)
            with open(path) as f:
                config = json.load(f)
            for key, role in manifest["colors"]["configKeys"].items():
                recolor.set_path(config, key, colors[role])
            with open(path, "w") as f:
                json.dump(config, f, indent=4)
    igm = os.path.join(theme_dir, "igm.json")
    if os.path.exists(igm):
        with open(igm) as f:
            config = json.load(f)
        for key, spec in manifest["colors"]["igmKeys"].items():
            recolor.set_path(config, key, colors[spec["role"]] + spec["suffix"])
        with open(igm, "w") as f:
            json.dump(config, f, indent=4)
    with open(os.path.join(options, "applied.json"), "w") as f:
        json.dump({"variant": variant, "palette": palette.name, "colors": colors}, f)


class PixelOptions(unittest.TestCase):
    @property
    def built(self):
        return ROOT[1]

    def assertSameTheme(self, got, want, skip=(), pixels=False):
        """Every file of `want` is in `got` with the same content: configs without their name and description, igm.json
        without its name, PNGs (with `pixels`) by size and RGBA."""
        self.assertEqual(tree(got), tree(want))
        for rel in tree(want):
            if rel in skip:
                continue
            a, b = os.path.join(got, *rel.split("/")), os.path.join(want, *rel.split("/"))
            if rel.startswith("config") and rel.endswith(".json") or rel == "igm.json":
                with open(a) as f, open(b) as g:
                    x, y = json.load(f), json.load(g)
                drop = ("name",) if rel == "igm.json" else ("name", "description")
                for key in drop:
                    x.pop(key, None)
                    y.pop(key, None)
                self.assertEqual(x, y, rel)
            elif pixels and rel.endswith(".png"):
                self.assertEqual(rgba(a), rgba(b), rel)
            else:
                with open(a, "rb") as f, open(b, "rb") as g:
                    self.assertEqual(f.read(), g.read(), rel)

    def test_registered_built_once(self):
        self.assertIs(custom_themes.STYLES["Pixel"], pixel_options)
        self.assertFalse(custom_themes.needs_palettes(["Pixel"]))
        self.assertEqual((pixel_options.BASE, pixel_options.PALETTES, pixel_options.OPTIONS), ("SPRUCE", False, True))
        self.assertEqual(self.built, os.path.join(ROOT[0], "out", "Pixel"))

    def test_top_level_is_the_consoles_gruvbox_theme(self):
        self.assertSameTheme(self.built, ROOT[2], skip={"CREDITS.txt"})
        with open(os.path.join(self.built, "config.json")) as f:
            config = json.load(f)
        self.assertEqual((config["name"], config["description"]),
                         ("Pixel", "Pixel-art consoles or controllers on black, in any palette."))

    def test_variant_files(self):
        variants = os.path.join(self.built, "options", "variants")
        self.assertEqual(sorted(os.listdir(variants)), ["consoles", "controllers"])
        consoles, controllers = tree(os.path.join(variants, "consoles")), tree(os.path.join(variants, "controllers"))
        self.assertEqual(consoles, controllers)
        self.assertIn("icons/md.png", consoles)  # drawn as a console or as its controller
        self.assertIn("icons/sel/md.png", consoles)
        self.assertNotIn("icons/gba.png", consoles)  # a handheld, drawn the same in both
        self.assertIn("skin/ic-game-n.png", consoles)
        self.assertFalse([r for r in consoles if r.rsplit("/", 1)[-1].startswith("config")])
        for rel in consoles:  # the consoles copy is what the top level shows
            with open(os.path.join(variants, "consoles", *rel.split("/")), "rb") as f, \
                    open(os.path.join(self.built, *rel.split("/")), "rb") as g:
                self.assertEqual(f.read(), g.read(), rel)

    def test_templates(self):
        found = tree(os.path.join(self.built, "options", "templates"))
        self.assertIn("skin/bg-title.png.tpl", found)  # a frame
        self.assertIn("skin/extra-bar.png.tpl", found)  # a bar-gray skin file
        self.assertIn("skin_1280x720/extra-bar.png.tpl", found)
        self.assertNotIn("skin/ic-game-n.png.tpl", found)  # drawn by the build
        self.assertTrue(all(r.startswith("skin") for r in found))

    def test_applying_controllers_nord_equals_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            theme = os.path.join(tmp, "Pixel")
            shutil.copytree(self.built, theme)
            apply(theme, "controllers", palettes.get("Nord"))
            self.assertSameTheme(theme, ROOT[3], skip={"CREDITS.txt", "preview.png"}, pixels=True)

    def test_applying_consoles_gruvbox_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            theme = os.path.join(tmp, "Pixel")
            shutil.copytree(self.built, theme)
            apply(theme, "consoles", palettes.get("Gruvbox"))
            self.assertSameTheme(theme, self.built, pixels=True)

    def test_no_template_on_a_variant_file(self):
        options = os.path.join(self.built, "options")
        variant = set(tree(os.path.join(options, "variants", "consoles")))
        targets = {r[:-len(".tpl")] for r in tree(os.path.join(options, "templates"))}
        self.assertTrue(targets)
        self.assertFalse(variant & targets)

    def test_manifest_shape(self):
        options = os.path.join(self.built, "options")
        with open(os.path.join(options, "manifest.json")) as f:
            manifest = json.load(f)
        self.assertEqual(manifest["formatVersion"], 1)
        self.assertEqual(manifest["variants"], {"default": "consoles", "list": [
            {"id": "consoles", "name": "Consoles"}, {"id": "controllers", "name": "Controllers"}]})
        colors = manifest["colors"]
        self.assertEqual(colors["roles"], [{"id": r, "name": r.capitalize()} for r in recipe.ROLES])
        self.assertEqual(len(colors["roles"]), 6)
        self.assertEqual(colors["configKeys"], recolor.CONFIG_KEYS)
        self.assertEqual(colors["igmKeys"], recolor.IGM_KEYS)
        self.assertEqual(colors["defaultPalette"], "Gruvbox")
        self.assertEqual(len(colors["palettes"]), 41)
        self.assertEqual([p["name"] for p in colors["palettes"]], palettes.names())
        self.assertEqual(colors["palettes"][0], {"name": "Gruvbox", "colors": {
            "text": "#EBDBB2", "list": "#FBF1C7", "selected": "#FBF1C7", "accent": "#D65D0E", "dim": "#7C6F64",
            "bar": "#504945"}})
        with open(os.path.join(options, "applied.json")) as f:
            self.assertEqual(json.load(f), {"variant": "consoles", "palette": "Gruvbox",
                                            "colors": colors["palettes"][0]["colors"]})

    def test_no_selected_json(self):
        self.assertFalse(os.path.exists(os.path.join(self.built, "options", "selected.json")))

    def test_rebuild_replaces_and_cleans_up(self):
        out = os.path.dirname(self.built)
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "out")
            shutil.copytree(self.built, os.path.join(target, "Pixel"))
            with open(os.path.join(target, "Pixel", "stale.txt"), "w") as f:
                f.write("x")
            self.assertEqual(pixel_options.build(os.path.join(ROOT[0], "base"), target), os.path.join(target, "Pixel"))
            self.assertEqual(os.listdir(target), ["Pixel"])
            self.assertFalse(os.path.exists(os.path.join(target, "Pixel", "stale.txt")))
        self.assertEqual(os.listdir(out), ["Pixel"])


if __name__ == "__main__":
    unittest.main()
