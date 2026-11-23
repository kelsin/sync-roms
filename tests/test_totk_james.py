import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402

import sync_roms  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
