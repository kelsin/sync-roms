import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402

import sync_roms  # noqa: E402
from sync_roms.custom_themes import totk_james, totk_kelsin  # noqa: E402

DATA = os.path.join(os.path.dirname(sync_roms.__file__), "data", "themes", "totk-james")


class ArtData(unittest.TestCase):
    def test_cards_present_and_sized(self):
        for cid in ("sidon", "riju", "mineru", "rauru"):
            for state in ("f", "n"):
                with Image.open(os.path.join(DATA, "cards", f"{cid}-{state}.png")) as im:
                    self.assertEqual(im.size, (156, 328))
                    self.assertEqual(im.mode, "RGBA")

    def test_title_size(self):
        for name in ("bg-title.png", "bg-title-kelsin.png"):
            with Image.open(os.path.join(DATA, name)) as im:
                self.assertEqual(im.size, (196, 51))


def read(path):
    with open(path, "rb") as f:
        return f.read()


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = os.path.join(self.tmp.name, "base")
        self.out = os.path.join(self.tmp.name, "out")
        os.makedirs(os.path.join(self.base, "skin"))
        Image.new("RGBA", (196, 51), (0, 0, 0, 255)).save(os.path.join(self.base, "skin", "bg-title.png"))
        Image.new("RGBA", (4, 4)).save(os.path.join(self.base, "skin", "ic-game-f.png"))

    def config(self, text, encoding="utf-8"):
        with open(os.path.join(self.base, "config.json"), "w", encoding=encoding) as f:
            f.write(text)

    def test_build_lays_art_over_base(self):
        self.config(json.dumps({"name": "ToTK", "title": {"size": 30}}))
        dest = totk_james.build(self.base, self.out)
        self.assertEqual(dest, os.path.join(self.out, "ToTK - James"))
        skin = os.path.join(dest, "skin")
        self.assertEqual(read(os.path.join(skin, "bg-title.png")), read(os.path.join(DATA, "bg-title.png")))
        for state in ("f", "n"):
            self.assertEqual(read(os.path.join(skin, f"ic-collection-{state}.png")),
                             read(os.path.join(DATA, "cards", f"rauru-{state}.png")))
            for cid in totk_james.CHARACTERS:
                self.assertTrue(os.path.exists(os.path.join(skin, f"ic-collection-{cid}-{state}.png")))
        self.assertTrue(os.path.exists(os.path.join(skin, "ic-game-f.png")))
        with open(os.path.join(dest, "config.json"), encoding="utf-8") as f:
            config = json.load(f)
        self.assertEqual((config["name"], config["mainMenuTitle"], config["title"]), ("ToTK - James", "", {"size": 30}))
        self.assertIs(config["collectionsEnabled"], True)

    def test_build_replaces_previous_output(self):
        self.config("{}")
        stray = os.path.join(self.out, "ToTK - James", "stray.txt")
        os.makedirs(os.path.dirname(stray))
        open(stray, "w").close()
        totk_james.build(self.base, self.out)
        self.assertFalse(os.path.exists(stray))

    def test_bom_config(self):
        self.config(json.dumps({"name": "ToTK"}), "utf-8-sig")
        dest = totk_james.build(self.base, self.out)
        with open(os.path.join(dest, "config.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["mainMenuTitle"], "")

    def test_preview_gets_the_title(self):
        self.config("{}")
        Image.new("RGB", (640, 480), (9, 80, 7)).save(os.path.join(self.base, "preview.png"))
        dest = totk_james.build(self.base, self.out)
        with Image.open(os.path.join(dest, "preview.png")) as preview, \
                Image.open(os.path.join(DATA, "bg-title.png")) as title:
            self.assertEqual(preview.size, (640, 480))
            self.assertEqual(preview.convert("RGB").crop((0, 0, 196, 51)).tobytes(), title.convert("RGB").tobytes())
            self.assertEqual(preview.convert("RGB").getpixel((196, 0)), (9, 80, 7))
            self.assertEqual(preview.convert("RGB").getpixel((0, 51)), (9, 80, 7))

    def test_kelsin_build(self):
        self.config(json.dumps({"name": "ToTK"}))
        Image.new("RGB", (640, 480), (9, 80, 7)).save(os.path.join(self.base, "preview.png"))
        dest = totk_kelsin.build(self.base, self.out)
        self.assertEqual(dest, os.path.join(self.out, "ToTK - Kelsin"))
        title = os.path.join(DATA, "bg-title-kelsin.png")
        self.assertEqual(read(os.path.join(dest, "skin", "bg-title.png")), read(title))
        self.assertEqual(read(os.path.join(dest, "skin", "ic-collection-f.png")),
                         read(os.path.join(DATA, "cards", "rauru-f.png")))
        with Image.open(os.path.join(dest, "preview.png")) as preview, Image.open(title) as im:
            self.assertEqual(preview.convert("RGB").crop((0, 0, 196, 51)).tobytes(), im.convert("RGB").tobytes())
        with open(os.path.join(dest, "config.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["name"], "ToTK - Kelsin")

    def test_no_preview_in_base(self):
        self.config("{}")
        dest = totk_james.build(self.base, self.out)
        self.assertFalse(os.path.exists(os.path.join(dest, "preview.png")))


if __name__ == "__main__":
    unittest.main()
