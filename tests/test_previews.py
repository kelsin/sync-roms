import io
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import previews, runtime, s3, store, themeart  # noqa: E402


def listing(*keys):
    return {k: None for k in keys}


class PreviewsTests(unittest.TestCase):
    def setUp(self):
        previews.reset()
        self.addCleanup(previews.reset)

    def files(self, *keys):
        return mock.patch.object(previews.inventory, "files", return_value=listing(*keys))

    def isfile(self):
        return mock.patch.object(previews.os.path, "isfile", return_value=True)

    def root(self, value):
        return mock.patch.object(s3, "read_root", return_value=value)

    def test_collection_art_path(self):
        self.assertEqual(previews.collection("shmup"), themeart.art_png("shmup"))
        self.assertIsNone(previews.collection(None))

    def test_game_prefers_covers_then_mix_title_screenshot(self):
        with self.files("scrapes/gba/screenshots/G.png", "scrapes/gba/miximages/G.png"), self.root("/r"), self.isfile():
            self.assertTrue(previews.game("gba/G.zip").endswith("scrapes/gba/miximages/G.png"))

    def test_game_with_subfolder_and_dots(self):
        with self.files("scrapes/ps2/covers/USA/Dr. Mario.jpg"), self.root("/r"), self.isfile():
            self.assertEqual(previews.game("ps2/USA/Dr. Mario.chd"),
                             s3.safe_join("/r", "scrapes/ps2/covers/USA/Dr. Mario.jpg"))

    def test_game_without_art_is_none(self):
        with self.files("scrapes/gba/covers/Other.png"), self.root("/r"):
            self.assertIsNone(previews.game("gba/G.zip"))

    def test_folder_storage_returns_file_in_place(self):
        key = "scrapes/gba/covers/G.png"
        with self.files(key), self.root("/r"), self.isfile(), mock.patch.object(s3, "download") as dl:
            self.assertEqual(previews.game("gba/G.zip"), s3.safe_join("/r", key))
        dl.assert_not_called()

    def test_listed_but_missing_file_in_folder_mode_is_none(self):
        with self.files("scrapes/gba/covers/G.png"), self.root("/nowhere"):
            self.assertIsNone(previews.game("gba/G.zip"))

    def test_mirror_miss_falls_back_to_the_storage_folder(self):
        key = "scrapes/gba/covers/G.png"
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "storage", os.path.dirname(key)))
            want = os.path.join(tmp, "storage", key)
            with open(want, "wb") as f:
                f.write(b"x")
            with self.files(key), self.root(os.path.join(tmp, "mirror")), \
                    mock.patch.object(runtime, "_mirror_root", os.path.join(tmp, "mirror")), \
                    mock.patch.object(runtime, "ROOT", os.path.join(tmp, "storage")):
                self.assertEqual(previews.game("gba/G.zip"), want)

    def test_mirror_miss_with_a_bucket_downloads(self):
        key = "scrapes/gba/covers/G.png"
        path = os.path.join(store.data_dir(), "previews", key)
        shutil.rmtree(os.path.join(store.data_dir(), "previews"), ignore_errors=True)
        self.addCleanup(shutil.rmtree, os.path.join(store.data_dir(), "previews"), ignore_errors=True)

        def fake(job):
            self.assertIsNone(runtime._mirror_root)  # read past the mirror
            os.makedirs(os.path.dirname(job[1]), exist_ok=True)
            with open(job[1], "wb") as f:
                f.write(b"x")

        with tempfile.TemporaryDirectory() as tmp:
            with self.files(key), self.root(tmp), mock.patch.object(runtime, "_mirror_root", tmp), \
                    mock.patch.object(runtime, "ROOT", None), \
                    mock.patch.object(s3, "download", side_effect=fake) as dl:
                self.assertEqual(previews.game("gba/G.zip"), path)
                self.assertEqual(runtime._mirror_root, tmp)
        dl.assert_called_once_with((key, path, None))

    def test_bucket_downloads_once_into_previews(self):
        key = "scrapes/gba/covers/G.png"
        path = os.path.join(store.data_dir(), "previews", key)

        def fake(job):
            os.makedirs(os.path.dirname(job[1]), exist_ok=True)
            with open(job[1], "wb") as f:
                f.write(b"x")

        with self.files(key), self.root(None), mock.patch.object(s3, "download", side_effect=fake) as dl:
            self.assertEqual(previews.game("gba/G.zip"), path)
            self.assertEqual(previews.game("gba/G.zip"), path)
        dl.assert_called_once_with((key, path, None))

    def test_bucket_download_error_is_none(self):
        with self.files("scrapes/gba/covers/G.png"), self.root(None), \
                mock.patch.object(s3, "download", side_effect=OSError("boom")):
            self.assertIsNone(previews.game("gba/G.zip"))

    def test_index_read_once_per_system(self):
        with self.files("scrapes/gba/covers/G.png", "scrapes/gba/covers/H.png") as files, self.root("/r"):
            previews.game("gba/G.zip")
            previews.game("gba/H.zip")
        files.assert_called_once_with("scrapes/gba/", sizes=False)



class GameThumbTests(unittest.TestCase):
    KEY = "scrapes/gba/covers/G.png"

    def setUp(self):
        previews.reset()
        self.addCleanup(previews.reset)
        cache = os.path.join(store.data_dir(), "preview-cache")
        shutil.rmtree(cache, ignore_errors=True)
        self.addCleanup(shutil.rmtree, cache, ignore_errors=True)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.source = os.path.join(self.root, self.KEY)
        os.makedirs(os.path.dirname(self.source))
        self.write((600, 900), "RGBA")

    def write(self, size, mode="RGB"):
        from PIL import Image
        Image.new(mode, size, (255, 0, 0, 128) if mode == "RGBA" else "red").save(self.source)
        return os.path.getsize(self.source)

    def thumb(self, size=None, etag=None):
        size = os.path.getsize(self.source) if size is None else size
        with mock.patch.object(previews.inventory, "files", return_value={self.KEY: size}), \
                mock.patch.object(previews.inventory, "known", return_value=(size, etag) if etag else None), \
                mock.patch.object(s3, "read_root", return_value=self.root):
            previews.reset()
            return previews.game_thumb("gba/G.zip")

    def test_makes_a_300_px_wide_webp_keeping_alpha(self):
        from PIL import Image
        path = self.thumb()
        size = os.path.getsize(self.source)
        self.assertEqual(path, os.path.join(store.data_dir(), "preview-cache", "scrapes/gba/covers", f"G.s{size}.webp"))
        with Image.open(path) as image:
            self.assertEqual((image.format, image.size, image.mode), ("WEBP", (300, 450), "RGBA"))

    def test_etag_names_the_thumbnail_when_known(self):
        self.assertTrue(self.thumb(etag='"abc-2"').endswith("/G.abc-2.webp"))

    def test_a_cached_thumbnail_never_touches_the_source(self):
        size = os.path.getsize(self.source)
        first = self.thumb()
        os.remove(self.source)
        with mock.patch.object(previews.os.path, "isfile", side_effect=AssertionError("stat")):
            self.assertEqual(self.thumb(size), first)

    def test_a_changed_tag_makes_a_new_thumbnail_and_removes_the_old(self):
        old = self.thumb()
        self.write((300, 300))
        new = self.thumb()
        self.assertNotEqual(new, old)
        self.assertTrue(os.path.exists(new))
        self.assertFalse(os.path.exists(old))
        etag = self.thumb(etag='"e1"')
        self.assertFalse(os.path.exists(new))
        self.assertTrue(os.path.exists(etag))

    def test_other_games_thumbnails_with_a_similar_name_stay(self):
        other = os.path.join(store.data_dir(), "preview-cache", "scrapes/gba/covers", "G. Two.s1.webp")
        os.makedirs(os.path.dirname(other))
        open(other, "wb").close()
        self.thumb()
        self.assertTrue(os.path.exists(other))

    def test_corrupt_or_missing_source_is_none(self):
        with open(self.source, "wb") as f:
            f.write(b"not a picture")
        self.assertIsNone(self.thumb())
        os.remove(self.source)
        self.assertIsNone(self.thumb(5))
        self.assertFalse(os.path.exists(os.path.join(store.data_dir(), "preview-cache")))

    def test_a_source_missing_from_the_storage_folder_is_none_without_a_stat(self):
        os.remove(self.source)
        with mock.patch.object(previews.os.path, "isfile", return_value=True) as isfile:
            self.assertIsNone(self.thumb(5))
        isfile.assert_not_called()  # game_thumb swallows errors, so a raising stat would pass unseen

    def test_a_source_missing_from_the_mirror_is_read_from_the_storage_folder_without_a_stat(self):
        from PIL import Image
        mirror = os.path.join(self.root, "mirror")
        with mock.patch.object(runtime, "_mirror_root", mirror), mock.patch.object(runtime, "ROOT", self.root), \
                mock.patch.object(previews.inventory, "files", return_value={self.KEY: 7}), \
                mock.patch.object(previews.inventory, "known", return_value=None), \
                mock.patch.object(s3, "read_root", return_value=mirror), \
                mock.patch.object(previews.os.path, "isfile", return_value=False) as isfile:
            path = previews.game_thumb("gba/G.zip")
        isfile.assert_not_called()
        with Image.open(path) as image:
            self.assertEqual(image.size, (300, 450))

    def test_no_art_is_none(self):
        with mock.patch.object(previews.inventory, "files", return_value={}):
            self.assertIsNone(previews.game_thumb("gba/G.zip"))

    def test_without_a_tag_the_source_is_shown_as_is(self):
        with mock.patch.object(previews.inventory, "files", return_value={self.KEY: None}), \
                mock.patch.object(previews.inventory, "known", return_value=None), \
                mock.patch.object(s3, "read_root", return_value=self.root):
            self.assertEqual(previews.game_thumb("gba/G.zip"), self.source)


class PreviewImageTests(unittest.TestCase):
    def test_reads_the_file_in_one_go(self):
        from PIL import Image
        from sync_roms import picker
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.png")
            Image.new("RGB", (600, 900), "red").save(path)
            real = open
            with mock.patch("builtins.open", side_effect=real) as opened:
                image = picker._preview_image(path, 300)
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(image.size, (300, 450))
            image = picker._preview_image(path)
            self.assertEqual((image.size, image.filename), ((533, 800), path))


class SystemOutlineTests(unittest.TestCase):
    TOP = "art-book-next-es-de-abc/"
    OUT = "_inc/systems/artwork-outline/"

    def setUp(self):
        previews.reset()
        self.addCleanup(previews.reset)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.root = os.path.join(tmp, "root")
        self.archive = os.path.join(self.root, themeart.ESDE_ARCHIVE)
        os.makedirs(os.path.dirname(self.archive))
        with tarfile.open(self.archive, "w:gz") as t:
            for name in (self.OUT + "gba.png", self.OUT + "mame.png", "theme.xml"):
                data = b"png"
                info = tarfile.TarInfo(self.TOP + name)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        self.base = os.path.join(store.data_dir(), "theme-art")
        shutil.rmtree(self.base, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)

    def commit(self, value="abc"):
        return mock.patch.object(themeart, "_stored_commit", return_value=value)

    def root_patch(self, value="default"):
        return mock.patch.object(s3, "read_root", return_value=self.root if value == "default" else value)

    def test_system_outline_from_folder_archive(self):
        with self.commit(), self.root_patch():
            path = previews.system({"folders": {"esde": "gba"}})
        self.assertEqual(path, os.path.join(self.base, "abc", "gba.png"))
        self.assertTrue(os.path.exists(path))
        self.assertFalse(os.path.exists(os.path.join(self.base, "abc", "theme.xml")))

    def test_outline_unpacked_once(self):
        with self.commit(), self.root_patch():
            previews.system({"folders": {"esde": "gba"}})
            previews.reset()
            with mock.patch.object(previews.tarfile, "open", side_effect=AssertionError("opened")):
                self.assertTrue(previews.system({"folders": {"esde": "mame"}}).endswith("mame.png"))

    def test_new_commit_replaces_old_folder(self):
        os.makedirs(os.path.join(self.base, "old"))
        with self.commit(), self.root_patch():
            previews.system({"folders": {"esde": "gba"}})
        self.assertEqual(os.listdir(self.base), ["abc"])

    def test_no_archive_is_none_and_not_retried(self):
        with self.commit(None) as c, self.root_patch():
            self.assertIsNone(previews.system({"folders": {"esde": "gba"}}))
            self.assertIsNone(previews.system({"folders": {"esde": "gba"}}))
        self.assertEqual(c.call_count, 1)

    def test_failure_is_not_retried(self):
        with self.commit(), self.root_patch(), \
                mock.patch.object(previews.tarfile, "open", side_effect=tarfile.TarError("bad")) as opened:
            self.assertIsNone(previews.system({"folders": {"esde": "gba"}}))
            self.assertIsNone(previews.system({"folders": {"esde": "gba"}}))
        self.assertEqual(opened.call_count, 1)

    def test_interrupted_unpack_is_not_complete(self):
        with self.commit(), self.root_patch(), mock.patch.object(previews.shutil, "copyfileobj", side_effect=OSError("x")):
            self.assertIsNone(previews.system({"folders": {"esde": "gba"}}))
        self.assertFalse(os.path.exists(os.path.join(self.base, "abc")))

    def test_bucket_archive_downloaded_to_temp(self):
        seen = []

        def fake(job):
            seen.append(job[1])
            shutil.copy(self.archive, job[1])

        with self.commit(), self.root_patch(None), mock.patch.object(s3, "download", side_effect=fake) as dl:
            path = previews.system({"folders": {"esde": "gba"}})
        self.assertEqual(dl.call_args[0][0][0], themeart.ESDE_ARCHIVE)
        self.assertTrue(path.endswith("gba.png") and os.path.exists(path))
        self.assertFalse(os.path.exists(seen[0]))

    def test_bucket_temp_removed_when_unpack_fails(self):
        seen = []

        def fake(job):
            seen.append(job[1])
            shutil.copy(self.archive, job[1])

        with self.commit(), self.root_patch(None), mock.patch.object(s3, "download", side_effect=fake), \
                mock.patch.object(previews.shutil, "copyfileobj", side_effect=OSError("x")):
            self.assertIsNone(previews.system({"folders": {"esde": "gba"}}))
        self.assertFalse(os.path.exists(seen[0]))

    def test_unpack_lost_to_another_process_uses_its_folder(self):
        folder = os.path.join(self.base, "abc")

        def lose(src, dst):
            os.makedirs(dst)
            raise OSError("exists")

        with self.commit(), self.root_patch(), mock.patch.object(previews.os, "rename", side_effect=lose):
            self.assertEqual(previews._resolve_outlines(), folder)

    def test_system_without_esde_folder_is_none(self):
        with self.commit(), self.root_patch():
            self.assertIsNone(previews.system({"folders": {}}))
            self.assertIsNone(previews.system({"folders": {"esde": "nes"}}))


if __name__ == "__main__":
    unittest.main()
