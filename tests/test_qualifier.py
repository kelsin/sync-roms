import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms.screenscraper import qualify, set_qualifier  # noqa: E402


class Qualify(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(qualify({"name": "Starfy", "qualifier": "Japan"}), {"name": "Starfy (Japan)", "qualifier": "Japan"})

    def test_before_translated(self):
        entry = {"name": "Chrono - Translated", "qualifier": "Aeon Genesis", "translated": True}
        self.assertEqual(qualify(entry)["name"], "Chrono (Aeon Genesis) - Translated")

    def test_idempotent(self):
        once = qualify({"name": "Chrono - Translated", "qualifier": "Aeon Genesis", "translated": True})
        self.assertEqual(qualify(once), once)
        self.assertEqual(qualify(qualify({"name": "A", "qualifier": "B"})), {"name": "A (B)", "qualifier": "B"})

    def test_unchanged_without_qualifier_or_name(self):
        self.assertEqual(qualify({"name": "A"}), {"name": "A"})
        self.assertEqual(qualify({"qualifier": "B"}), {"qualifier": "B"})

    def test_returns_copy(self):
        entry = {"name": "A", "qualifier": "B"}
        qualify(entry)
        self.assertEqual(entry["name"], "A")


class SetQualifier(unittest.TestCase):
    def test_sets(self):
        self.assertEqual(set_qualifier({"name": "A"}, "Japan"), {"name": "A (Japan)", "qualifier": "Japan"})

    def test_sets_translated(self):
        out = set_qualifier({"name": "A - Translated", "translated": True}, "FastROM")
        self.assertEqual(out["name"], "A (FastROM) - Translated")

    def test_changes(self):
        out = set_qualifier({"name": "A (Japan) - Translated", "qualifier": "Japan", "translated": True}, "Aeon Genesis")
        self.assertEqual(out, {"name": "A (Aeon Genesis) - Translated", "qualifier": "Aeon Genesis", "translated": True})

    def test_same_again(self):
        entry = {"name": "A (Japan)", "qualifier": "Japan"}
        self.assertEqual(set_qualifier(entry, "Japan"), entry)

    def test_removes(self):
        for empty in (None, ""):
            self.assertEqual(set_qualifier({"name": "A (Japan) - Translated", "qualifier": "Japan", "translated": True}, empty),
                             {"name": "A - Translated", "translated": True})
        self.assertEqual(set_qualifier({"name": "A"}, None), {"name": "A"})

    def test_returns_copy(self):
        entry = {"name": "A (Japan)", "qualifier": "Japan"}
        set_qualifier(entry, None)
        self.assertEqual(entry, {"name": "A (Japan)", "qualifier": "Japan"})


if __name__ == "__main__":
    unittest.main()
