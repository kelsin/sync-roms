import os
import tempfile
import unittest

import helpers  # noqa: F401
from PIL import Image

from sync_roms import pixel_art_page
from sync_roms.custom_themes.pixel import app_icons, build, menu, ui_settings, ui_status, variants
from sync_roms.custom_themes.pixel.sprite import render


class SpriteSectionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.img = os.path.join(cls.tmp.name, "img")
        cls.sections = pixel_art_page.sprite_sections(cls.img)
        cls.by_id = {s["id"]: s for s in cls.sections}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_sprite_is_on_the_page(self):
        consoles, controllers = build.systems("CONSOLES"), build.systems("CONTROLLERS")
        shared = [i for i in consoles if consoles[i] is controllers[i]]
        own = [i for i in consoles if i not in shared]
        counts = {
            "menu": len(menu.SPRITES) + 2,
            "systems-shared": len(shared),
            "systems-consoles": len(own),
            "systems-controllers": len(own),
            "regions": sum(len(r) * 2 for r in variants.VARIANTS.values()),
            "apps": len(app_icons.ICONS),
            "settings": len(ui_settings.ICONS),
            "status": len(ui_status.ICONS),
        }
        self.assertEqual([s["id"] for s in self.sections], list(counts))
        for sid, n in counts.items():
            self.assertEqual(len(self.by_id[sid]["items"]), n, sid)

    def test_images_are_one_pixel_per_art_pixel(self):
        item = next(i for i in self.by_id["systems-shared"]["items"] if i["img"].endswith("/gb.png"))
        sprite = build.systems("CONSOLES")["gb"]()
        for key, state in (("img", "sel"), ("dim", "n")):
            with Image.open(os.path.join(self.img, *item[key].split("/")[1:])) as im:
                self.assertEqual(im.convert("RGBA").tobytes(), render(sprite, 1, state).tobytes())
        want = render(sprite, 1, "sel")
        self.assertEqual((item["w"], item["h"]), want.size)

    def test_files_and_notes(self):
        item = next(i for i in self.by_id["systems-shared"]["items"] if i["img"].endswith("/gb.png"))
        self.assertEqual(item["files"], [{"path": "icons/gb.png", "size": [120, 130]},
                                         {"path": "icons/sel/gb.png", "size": [120, 130]}])
        unused = [i for i in self.by_id["regions"]["items"] if i["note"] == "not used by the themes"]
        self.assertTrue(unused)
        self.assertTrue(all(not i["files"] for i in unused))
        status = self.by_id["status"]["items"][0]
        self.assertEqual(status["note"], "not in the SPRUCE base")
        self.assertNotIn("dim", status)

    def test_image_paths_unique(self):
        paths = [p for s in self.sections for i in s["items"] for p in (i["img"], i.get("dim")) if p]
        self.assertEqual(len(paths), len(set(paths)))


if __name__ == "__main__":
    unittest.main()
