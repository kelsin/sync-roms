import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402

import sync_roms  # noqa: E402
from sync_roms.custom_themes import totk_james  # noqa: E402

DATA = os.path.join(os.path.dirname(sync_roms.__file__), "data", "themes", "totk-james")


class ArtData(unittest.TestCase):
    def test_cards_present_and_sized(self):
        for cid in ("sidon", "riju", "mineru", "rauru"):
            for state in ("f", "n"):
                with Image.open(os.path.join(DATA, "cards", f"{cid}-{state}.png")) as im:
                    self.assertEqual(im.size, (156, 328))
                    self.assertEqual(im.mode, "RGBA")

    def test_title_size(self):
        with Image.open(os.path.join(DATA, "bg-title.png")) as im:
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


if __name__ == "__main__":
    unittest.main()
