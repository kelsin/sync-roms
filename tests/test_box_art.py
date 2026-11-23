import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import gen_box_art  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "sync_roms", "data", "themes",
                    "art-book-next")
SPRITES = os.path.join(DATA, "sprites")
with open(os.path.join(DATA, "box-palette.json")) as f:
    PALETTE = json.load(f)


def read(name):
    with open(os.path.join(SPRITES, name)) as f:
        return f.read()


class BoxArtTest(unittest.TestCase):
    def test_sizes_and_mode(self):
        for name, size in gen_box_art.SIZES.items():
            im = gen_box_art.sizes("action-classics")[name]
            self.assertEqual((im.size, im.mode), (size, "RGB"))

    def test_render_is_deterministic(self):
        self.assertEqual(gen_box_art.render("action-classics").tobytes(),
                         gen_box_art.render("action-classics").tobytes())

    def test_badge_is_stable_and_from_the_list(self):
        self.assertEqual(gen_box_art.badge("rpg"), gen_box_art.badge("rpg"))
        self.assertIn(gen_box_art.badge("rpg")[0], gen_box_art.BADGES)
        self.assertGreater(len({gen_box_art.badge(i)[0] for i in gen_box_art.ids()}), 6)

    def test_every_badge_fits_one_line(self):
        for b in gen_box_art.BADGES:
            self.assertEqual(len(gen_box_art.wrap(b)), 1, b)

    def test_every_title_and_badge_renders(self):  # every character is in the font, every title wraps to <= 3 lines
        for art_id in gen_box_art.ids():
            self.assertLessEqual(len(gen_box_art.wrap(gen_box_art.title(art_id))), 3, art_id)

    def test_sprite_fits_under_a_three_line_title(self):
        lay = gen_box_art.layout("dungeon-crawlers")
        x0, y0, x1, y1 = lay["picture"]
        x, y = lay["sprite"]
        self.assertTrue(x0 + 2 <= x and x + 64 <= x1 - 1 and y0 + 2 <= y and y + 64 <= y1 - 1)

    def test_badge_has_a_clear_pixel_above_it(self):  # the footer's top row stays footer colour
        im = gen_box_art.render("action-classics")
        self.assertEqual({im.getpixel((x, 108)) for x in range(6, 83)}, {(0x14, 0x12, 0x1C)})

    def test_sprites_have_a_clear_border_and_known_colours(self):
        for f in sorted(os.listdir(SPRITES)):
            rows = read(f).splitlines()
            self.assertEqual([len(r) for r in rows], [32] * 32, f)
            self.assertTrue(set("".join(rows)) <= set(PALETTE) | {"."}, f)
            self.assertEqual(set(rows[0] + rows[-1] + "".join(r[0] + r[-1] for r in rows)), {"."}, f)


if __name__ == "__main__":
    unittest.main()
