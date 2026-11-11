import contextlib
import io
import os
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import frontend, runtime, themeart, ui  # noqa: E402

def archive(files):
    """A .tar.gz stream like GitHub's, its files under one top folder."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return buf


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def read(path):
    with open(path) as f:
        return f.read()


class Assets(unittest.TestCase):
    def test_the_surprise_files_are_in_the_repo(self):
        self.assertEqual(themeart._art_files(), ["_inc/systems/_metadata-global/surprise.xml", themeart.ART_PNG,
                                                 themeart.LOGO_SVG, "surprise/theme.xml"])


class Settings(unittest.TestCase):
    def test_get_and_set_a_string(self):
        text = '<?xml version="1.0"?>\n<string name="Theme" value="a&amp;b" />\n'
        self.assertEqual(frontend.get_string(text, "Theme"), "a&b")
        self.assertIsNone(frontend.get_string(text, "Other"))
        self.assertEqual(frontend.set_string(text, "esde", "Theme", "x"), text.replace("a&amp;b", "x"))
        cfg = '<config>\n</config>\n'
        self.assertEqual(frontend.set_string(cfg, "knulli", "subset.S.a", "custom"),
                         '<config>\n\t<string name="subset.S.a" value="custom" />\n</config>\n')


class Card(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = tmp.name
        self.warned = []
        patcher = mock.patch.object(ui, "warn", self.warned.append)
        patcher.start()
        self.addCleanup(patcher.stop)


class Esde(Card):
    """An ES-DE card, with storage a folder (runtime.ROOT) that may hold the theme archive."""
    def setUp(self):
        super().setUp()
        storage = tempfile.TemporaryDirectory()
        self.addCleanup(storage.cleanup)
        self.storage = storage.name
        patcher = mock.patch.object(runtime, "ROOT", self.storage)
        patcher.start()
        self.addCleanup(patcher.stop)

    def store(self, commit, files):
        top = f"art-book-next-es-de-{commit}"
        write(os.path.join(self.storage, themeart.ESDE_COMMIT), commit + "\n")
        with open(os.path.join(self.storage, themeart.ESDE_ARCHIVE), "wb") as f:
            f.write(archive({f"{top}/{k}": v for k, v in files.items()}).getvalue())

    def settings(self, theme):
        write(frontend.settings_path("esde", self.base), f'<?xml version="1.0"?>\n<string name="Theme" value="{theme}" />\n')

    def install(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return themeart.install("esde", self.base, "Surprise")

    def copy(self, *rel):
        return os.path.join(self.base, "ES-DE", "themes", themeart.ESDE_COPY, *rel)

    def test_another_theme_is_left_alone(self):
        self.store("abc", {"theme.xml": b"<theme/>"})
        self.settings("linear-es-de")
        self.assertFalse(self.install())
        self.assertFalse(os.path.exists(self.copy()))

    def test_art_book_next_is_copied_with_the_surprise_files_and_selected(self):
        self.store("abc", {"theme.xml": b"<theme/>", "_inc/a.png": b"png"})
        self.settings(themeart.ESDE_THEME)
        self.assertTrue(self.install())
        self.assertEqual(read(self.copy("theme.xml")), "<theme/>")
        self.assertTrue(os.path.exists(self.copy(*themeart.ART_PNG.split("/"))))
        self.assertTrue(os.path.exists(self.copy("surprise", "theme.xml")))
        self.assertEqual(read(self.copy(themeart.ESDE_MARKER)).strip(), "abc")
        self.assertIn(f'value="{themeart.ESDE_COPY}"', read(frontend.settings_path("esde", self.base)))
        self.assertFalse(self.install())  # nothing new the second time

    def test_a_newer_commit_replaces_the_whole_copy(self):
        self.settings(themeart.ESDE_THEME)
        self.store("abc", {"theme.xml": b"<old/>", "gone.xml": b"x"})
        self.install()
        self.store("def", {"theme.xml": b"<new/>"})  # same size, different content
        self.assertTrue(self.install())
        self.assertEqual(read(self.copy("theme.xml")), "<new/>")
        self.assertFalse(os.path.exists(self.copy("gone.xml")))
        self.assertTrue(os.path.exists(self.copy("surprise", "theme.xml")))

    def test_no_archive_in_storage_warns_and_keeps_the_theme(self):
        self.settings(themeart.ESDE_THEME)
        self.assertFalse(self.install())
        self.assertIn("sync-roms themes update", self.warned[0])
        self.assertIn(f'value="{themeart.ESDE_THEME}"', read(frontend.settings_path("esde", self.base)))

    def test_a_broken_archive_keeps_the_old_copy(self):
        self.settings(themeart.ESDE_THEME)
        self.store("abc", {"theme.xml": b"<old/>"})
        self.install()
        self.store("def", {"theme.xml": b"<new/>"})
        with open(os.path.join(self.storage, themeart.ESDE_ARCHIVE), "r+b") as f:
            f.truncate(30)
        self.assertFalse(self.install())
        self.assertTrue(self.warned)
        self.assertEqual(read(self.copy("theme.xml")), "<old/>")

    def test_an_archive_path_that_climbs_out_is_refused(self):
        self.settings(themeart.ESDE_THEME)
        self.store("abc", {"../../evil.txt": b"x"})
        self.assertFalse(self.install())
        self.assertTrue(self.warned)
        self.assertFalse(os.path.exists(os.path.join(self.base, "ES-DE", "evil.txt")))


class Update(Esde):
    def run_update(self, latest, tarball=b"", dry_run=False):
        def github(url, accept=None):
            return io.BytesIO(latest.encode() if "api.github.com" in url else tarball)
        with mock.patch.object(themeart, "_github", github), contextlib.redirect_stdout(io.StringIO()):
            return themeart.update_storage(dry_run)

    def test_storage_gets_the_latest_archive_and_commit(self):
        tarball = archive({"top/theme.xml": b"<theme/>"}).getvalue()
        self.assertEqual(self.run_update("abc", tarball), 0)
        self.assertEqual(read(os.path.join(self.storage, themeart.ESDE_COMMIT)).strip(), "abc")
        with open(os.path.join(self.storage, themeart.ESDE_ARCHIVE), "rb") as f:
            self.assertEqual(f.read(), tarball)

    def test_the_latest_already_in_storage_is_left_alone(self):
        self.store("abc", {"theme.xml": b"<theme/>"})
        self.assertEqual(self.run_update("abc", b"not used"), 0)

    def test_a_missing_storage_folder_or_failed_upload_fails(self):
        with mock.patch.object(runtime, "ROOT", os.path.join(self.storage, "gone")):
            self.assertEqual(self.run_update("abc"), 1)
        with mock.patch.object(themeart.s3, "put_file", mock.Mock(side_effect=PermissionError("denied"))):
            self.assertEqual(self.run_update("abc", archive({"top/a": b"a"}).getvalue()), 1)
        self.assertIn("denied", self.warned[-1])

    def test_a_dry_run_or_a_bad_download_changes_nothing(self):
        self.store("abc", {"theme.xml": b"<theme/>"})
        self.assertEqual(self.run_update("def", archive({"top/a": b"a"}).getvalue(), dry_run=True), 0)
        self.assertEqual(self.run_update("def", b"not a tar.gz"), 1)
        self.assertEqual(read(os.path.join(self.storage, themeart.ESDE_COMMIT)).strip(), "abc")


class Knulli(Card):
    def path(self, *rel):
        return os.path.join(self.base, "theme-customizations", "art-book-next", *rel)

    def test_art_and_settings_for_the_collection(self):
        self.assertTrue(themeart.install("knulli", self.base, "Surprise"))
        self.assertTrue(os.path.exists(self.path("artwork", "Surprise.png")))
        self.assertTrue(os.path.exists(self.path("logos", "Surprise.svg")))
        settings = read(frontend.settings_path("knulli", self.base))
        for name, value in themeart.knulli_settings("Surprise").items():
            self.assertIn(f'<string name="{name}" value="{value}" />', settings)
        self.assertFalse(themeart.install("knulli", self.base, "Surprise"))  # nothing new the second time

    def test_a_grouping_choice_already_made_is_kept(self):
        path = frontend.settings_path("knulli", self.base)
        write(path, '<config>\n\t<string name="UseCustomCollectionsSystemEx" value="true" />\n</config>\n')
        themeart.install("knulli", self.base, "Surprise")
        settings = read(path)
        self.assertIn('name="UseCustomCollectionsSystemEx" value="true"', settings)
        self.assertIn('name="subset.Surprise.system-view-artwork" value="custom"', settings)

    def test_another_theme_is_left_alone(self):
        path = frontend.settings_path("knulli", self.base)
        write(path, '<config>\n\t<string name="ThemeSet" value="es-theme-carbon" />\n</config>\n')
        self.assertFalse(themeart.install("knulli", self.base, "Surprise"))
        self.assertFalse(os.path.exists(self.path()))
        self.assertNotIn("subset.", read(path))


if __name__ == "__main__":
    unittest.main()
