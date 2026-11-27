import json
import os
import re
import tempfile
import unittest
from unittest import mock

import helpers  # noqa: F401
from PIL import Image
from test_custom_themes import make_base as make_theme_base
from test_frames import BASE as FRAMES_BASE
from test_frames import make_base as make_frames_base

from sync_roms import pixel_art_page, store
from sync_roms.custom_themes import palettes, theme_name
from sync_roms.custom_themes.pixel import app_icons, build, frames, menu, ui_settings, ui_status, variants
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


TRANSPARENT = ("bg-grid-s", "div-line-v-02", "navbg", "num-bg", "preview-bg", "statbg", "thumb-default")


def fake_base(path):
    """The theme base the frames tests use, with the real base's transparent files and without its hint files."""
    make_theme_base(path)
    files = {n: v for n, v in FRAMES_BASE.items() if not n.startswith("context-")}
    make_frames_base(path, files=files, copies={})
    for name in TRANSPARENT:
        Image.new("RGBA", FRAMES_BASE[f"{name}.png"][0], (0, 0, 0, 0)).save(os.path.join(path, "skin", f"{name}.png"))


class FrameSectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = os.path.join(cls.tmp.name, "base")
        fake_base(base)
        cls.theme, cls.canvases = pixel_art_page.build_frames_theme(base, os.path.join(cls.tmp.name, "out"))
        cls.img = os.path.join(cls.tmp.name, "img")
        cls.section = pixel_art_page.frame_section(cls.img, cls.canvases)
        cls.sprites = pixel_art_page.sprite_sections(os.path.join(cls.tmp.name, "sprites"), cls.theme)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_frames_section_covers_what_themes_draw(self):
        self.assertEqual(self.section["id"], "frames")
        want = {n for n in frames.FRAMES if n[5:-4] not in TRANSPARENT}
        paths = {i["files"][0]["path"] for i in self.section["items"]}
        self.assertEqual(paths, want)
        hints = [i for i in self.section["items"] if i.get("note")]
        self.assertEqual({i["files"][0]["path"] for i in hints}, {f"skin/{n}" for n in pixel_art_page.HINT_SIZES})
        for item in hints:
            name = item["files"][0]["path"][5:]
            self.assertEqual(item["note"], "not in the SPRUCE base")
            size = pixel_art_page.HINT_SIZES[name]
            self.assertEqual(item["files"][0]["size"], list(size))
            self.assertEqual((item["w"] * item["cell"], item["h"] * item["cell"]), size)

    def test_frame_image_is_cells(self):
        item = next(i for i in self.section["items"] if i["files"][0]["path"] == "skin/bg-title.png")
        canvas = self.canvases["skin/bg-title.png"]
        self.assertEqual(item["cell"], canvas.cell)
        self.assertEqual(item["files"][0]["size"], list(canvas.size))
        with Image.open(os.path.join(self.img, *item["img"].split("/")[1:])) as cells, \
                Image.open(os.path.join(self.theme, "skin", "bg-title.png")) as built:
            crop = built.convert("RGBA").crop((canvas.ox, canvas.oy, canvas.ox + canvas.cols * canvas.cell,
                                               canvas.oy + canvas.rows * canvas.cell))
            self.assertEqual(cells.convert("RGBA").resize(crop.size, Image.NEAREST).tobytes(), crop.tobytes())

    def test_sprite_sizes_come_from_the_theme(self):
        by_id = {s["id"]: s for s in self.sprites}
        with Image.open(os.path.join(self.theme, "icons", "gba.png")) as im:
            gba = list(im.size)
        item = next(i for i in by_id["systems-shared"]["items"] if i["img"].endswith("/gba.png"))
        self.assertEqual(item["files"][0], {"path": "icons/gba.png", "size": gba})
        for sid in ("settings", "status"):
            for item in by_id[sid]["items"]:
                path = os.path.join(self.theme, *item["files"][0]["path"].split("/"))
                if os.path.isfile(path):
                    self.assertNotIn("note", item)
                    with Image.open(path) as im:
                        self.assertEqual(item["files"][0]["size"], list(im.size))
                else:
                    self.assertEqual(item["note"], "not in the SPRUCE base")
        self.assertTrue(any(i.get("note") for i in by_id["status"]["items"]))


class BoxSectionTest(unittest.TestCase):
    def test_box_reduction_exact(self):
        folder = os.path.join(store.REPO_DATA, "themes", "art-book-next", "art-box", "Imgs")
        ids = sorted(n[:-4] for n in os.listdir(folder) if n.endswith(".png"))
        with tempfile.TemporaryDirectory() as tmp:
            section = pixel_art_page.box_section(tmp)
            self.assertEqual(section["id"], "boxes")
            self.assertEqual([i["label"] for i in section["items"]], ids)
            for item in section["items"]:
                self.assertEqual((item["w"], item["h"]), (84, 120))
                name = item["label"]
                self.assertEqual([f["path"] for f in item["files"]], [f"Collections/{d}/{name}.png" for d in ("Imgs", "Imgs_med", "Imgs_small")])
                self.assertEqual([f["size"] for f in item["files"]], [[336, 480], [210, 300], [140, 200]])
                with Image.open(os.path.join(tmp, *item["img"].split("/")[1:])) as small, \
                        Image.open(os.path.join(folder, f"{name}.png")) as src:
                    self.assertEqual(small.convert("RGB").resize((336, 480), Image.NEAREST).tobytes(),
                                     src.convert("RGB").tobytes())


SECTION_IDS = ["menu", "systems-shared", "systems-consoles", "systems-controllers", "regions", "apps", "settings",
               "status", "frames", "boxes"]


def page_data(html):
    return json.loads(re.search(r'id="page-data">(.*?)</script>', html, re.S).group(1))


class WriteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = os.path.join(cls.tmp.name, "base")
        fake_base(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def read(self, out, name):
        with open(os.path.join(out, name), encoding="utf-8") as f:
            return f.read()

    def test_write_page(self):
        out = os.path.join(self.tmp.name, "page")
        os.makedirs(out)
        open(os.path.join(out, "stale.txt"), "w").close()
        pixel_art_page.write(out, base_dir=self.base)
        self.assertFalse(os.path.exists(os.path.join(out, "stale.txt")))
        html = self.read(out, "index.html")
        data = page_data(html)
        self.assertEqual(data["palette"], pixel_art_page.PALETTE)
        self.assertEqual(data["home"], "/")
        self.assertEqual([s["id"] for s in data["sections"]], SECTION_IDS)
        for section in data["sections"]:
            self.assertTrue(section["items"], section["id"])
            for item in section["items"]:
                for key in ("img", "dim"):
                    if key in item:
                        self.assertTrue(item[key].startswith("img/"), item[key])
                        self.assertTrue(os.path.isfile(os.path.join(out, *item[key].split("/"))), item[key])
        text = html + self.read(out, "page.css") + self.read(out, "page.js")
        self.assertIsNone(re.search(r'(src|href)=["\']?(https?:)?//', text))

    def test_data_escaped(self):
        out = os.path.join(self.tmp.name, "escaped")
        label = "</script><b>&"
        item = {"label": label, "img": "img/x.png", "w": 1, "h": 1, "files": []}
        with mock.patch.object(pixel_art_page, "sprite_sections",
                               lambda img_dir, theme_dir=None: [{"id": "menu", "title": "Menu", "items": [item]}]):
            pixel_art_page.write(out, base_dir=self.base)
        html = self.read(out, "index.html")
        self.assertNotIn("</script><b>", html)
        self.assertEqual(page_data(html)["sections"][0]["items"][0]["label"], label)


if __name__ == "__main__":
    unittest.main()
