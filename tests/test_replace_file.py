import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import cardfs, m3u, scrape_plan, store, themeart  # noqa: E402


class ReplaceFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = self.enterContext(tempfile.TemporaryDirectory())
        self.path = os.path.join(self.dir, "gamelist.xml")

    def read(self, path=None):
        with open(path or self.path, "rb") as f:
            return f.read()

    def test_writes_text_with_the_given_encoding_and_newline(self):
        store.replace_file(self.path, "é\nx\n", newline="\r\n")
        self.assertEqual(self.read(), "é\r\nx\r\n".encode())
        store.replace_file(self.path, "é\n", newline="")
        self.assertEqual(self.read(), "é\n".encode())

    def test_writes_bytes_as_they_are(self):
        store.replace_file(self.path, b"\x00\r\n\xff")
        self.assertEqual(self.read(), b"\x00\r\n\xff")

    def test_does_not_sync_to_disk(self):
        with mock.patch("os.fsync") as fsync:
            store.replace_file(self.path, "x")
        fsync.assert_not_called()

    def test_failed_replace_keeps_the_original_and_leaves_no_temp_file(self):
        store.replace_file(self.path, "old")
        with mock.patch("os.replace", side_effect=OSError("gone")):
            with self.assertRaises(OSError):
                store.replace_file(self.path, "new")
        self.assertEqual(self.read(), b"old")
        self.assertEqual(os.listdir(self.dir), ["gamelist.xml"])

    def test_gamelist_keeps_its_bytes_and_survives_a_failed_replace(self):
        entries = {"a.gba": {"name": "Aé"}}
        scrape_plan.update_gamelist(self.path, entries)
        self.assertEqual(self.read(), '<?xml version="1.0"?>\n<gameList>\n\t<game>\n\t\t<path>./a.gba</path>\n'
                                      '\t\t<name>Aé</name>\n\t</game>\n</gameList>\n'.encode())
        before = self.read()
        with mock.patch("os.replace", side_effect=OSError("gone")):
            with self.assertRaises(OSError):
                scrape_plan.update_gamelist(self.path, {"a.gba": {"name": "B"}})
        self.assertEqual(self.read(), before)
        self.assertEqual(os.listdir(self.dir), ["gamelist.xml"])

    def test_playlists_keep_their_line_endings(self):
        path = os.path.join(self.dir, "G.m3u")
        os.makedirs(os.path.join(self.dir, ".d"))
        open(os.path.join(self.dir, ".d", "a.chd"), "w").close()
        with open(path, "w", newline="") as f:
            f.write("a.chd\r\n")
        m3u.prefix_playlists(self.dir, ".d")
        self.assertEqual(self.read(path), b".d/a.chd\r\n")

    def test_write_bytes_writes_bytes_once(self):
        path = os.path.join(self.dir, "sub", "a.png")
        self.assertTrue(cardfs.write_bytes(path, b"\x89PNG\r\n"))
        self.assertEqual(self.read(path), b"\x89PNG\r\n")
        self.assertFalse(cardfs.write_bytes(path, b"\x89PNG\r\n"))

    def test_write_bytes_compares_with_the_file_itself_while_listings_and_reads_are_kept(self):
        path = os.path.join(self.dir, "a.png")
        with cardfs.caching():
            self.assertTrue(cardfs.write_bytes(path, b"old"))
            self.assertEqual(cardfs.read(path), b"old")  # kept until clear()
            self.assertTrue(cardfs.write_bytes(path, b"new"))
            self.assertEqual(self.read(path), b"new")  # written at once, not when caching() ends
            self.assertTrue(cardfs.write_bytes(path, b"old"))
            self.assertFalse(cardfs.write_bytes(path, b"old"))
        self.assertEqual(self.read(path), b"old")

    def test_settings_file_is_written_with_lf(self):
        path = os.path.join(self.dir, "es_settings.xml")
        themeart._write_settings(path, "esde", {"ThemeSet": "art-book-next-es-de"})
        data = self.read(path)
        self.assertIn(b"ThemeSet", data)
        self.assertNotIn(b"\r", data)
        self.assertEqual(os.listdir(self.dir), ["es_settings.xml"])


if __name__ == "__main__":
    unittest.main()
