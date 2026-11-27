import contextlib
import io
import os
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
from xml.dom import minidom

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import esde_pixel, frontend, github, runtime, store, themeart, ui  # noqa: E402

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


SURPRISE = {"Surprise": "surprise"}


class Assets(unittest.TestCase):
    def test_every_listed_art_and_surprise_have_a_picture(self):
        for art_id in [*themeart.art_choices(), themeart.SURPRISE_ART]:
            self.assertTrue(themeart.art_png(art_id), art_id)
        self.assertIsNone(themeart.art_png("nope"))
        self.assertIsNone(themeart.art_png("../art/surprise"))

    def test_every_art_has_box_art_in_three_sizes(self):
        from PIL import Image
        for art_id in [*themeart.art_choices(), themeart.SURPRISE_ART]:
            for size, dims in (("Imgs", (336, 480)), ("Imgs_med", (210, 300)), ("Imgs_small", (140, 200))):
                with Image.open(themeart.art_png(art_id, f"art-box/{size}")) as im:
                    self.assertEqual(im.size, dims, (art_id, size))

    def test_every_art_has_zelda_art_in_three_sizes(self):
        from PIL import Image
        folder = os.path.join(store.REPO_DATA, "themes", "totk-james", "collections")
        for art_id in [*themeart.art_choices(), themeart.SURPRISE_ART]:
            for size, dims in (("Imgs", (336, 480)), ("Imgs_med", (210, 300)), ("Imgs_small", (140, 200))):
                with Image.open(os.path.join(folder, size, f"{art_id}.png")) as im:
                    self.assertEqual(im.size, dims, (art_id, size))
                    self.assertEqual(im.mode, "P", (art_id, size))
                    self.assertEqual(im.convert("RGBA").getpixel((0, 0))[3], 0, (art_id, size))

    def test_every_art_has_its_own_emoji_and_no_art_has_the_default(self):
        ids = [*themeart.art_choices(), themeart.SURPRISE_ART]
        emoji = [themeart.art_emoji(i) for i in ids]
        self.assertEqual(len(set(emoji)), len(ids))
        self.assertNotIn(themeart.DEFAULT_EMOJI, emoji)
        self.assertEqual(themeart.art_emoji(None), themeart.DEFAULT_EMOJI)
        self.assertEqual(themeart.art_emoji("nope"), themeart.DEFAULT_EMOJI)

    def test_a_collection_has_the_emoji_of_its_art_else_the_default(self):
        self.assertFalse(hasattr(themeart, "set_art"))
        self.assertEqual(themeart.collection_emoji({}), themeart.DEFAULT_EMOJI)
        self.assertEqual(themeart.collection_emoji({"art": "surprise"}), themeart.art_emoji("surprise"))

    def test_a_logo_spells_the_name_in_capitals_and_fits(self):
        svg = themeart.logo_svg("Shmups 2!")
        self.assertEqual(svg.count("<path "), 8)  # S H M U P S 2 !: the space has no outline
        self.assertIn('viewBox="0 0 200 40"', svg)
        long = themeart.logo_svg("A very long collection name that has to shrink")
        scale = float(long.split("scale(")[1].split(" ")[0])
        self.assertLess(scale, 18.7 / 625)


class Logos(unittest.TestCase):
    def test_accents_fold_and_a_name_the_font_cant_draw_gets_no_logo(self):
        self.assertEqual(themeart.logo_svg("Pokémon").count("<path "), 7)
        self.assertIsNone(themeart.logo_svg("東方"))
        self.assertIsNone(themeart.logo_svg("  "))


class Usable(unittest.TestCase):
    def test_unknown_art_and_names_of_systems_or_built_in_collections_are_skipped(self):
        warned = []
        with mock.patch.object(ui, "warn", warned.append):
            got = themeart.usable("esde", {"Favs": "rpg", "Odd": "nope", "SNES": "rpg", "Now-Playing": "rpg",
                                           "auto-favorites": "rpg"})
        self.assertEqual(list(got), ["Favs"])
        self.assertEqual(len(warned), 4)

    def test_names_differing_only_in_case_keep_the_first(self):
        with mock.patch.object(ui, "warn", lambda *a: None):
            self.assertEqual(list(themeart.usable("esde", {"RPG Faves": "rpg", "Rpg Faves": "horror"})), ["RPG Faves"])
        with mock.patch.object(ui, "warn", lambda *a: None):
            self.assertEqual(list(themeart.usable("knulli", {"Lightgun": "shmups"})), [])
        with mock.patch.object(ui, "warn", lambda *a: None):
            self.assertEqual(list(themeart.usable("emudeck", {"SNES": "rpg", "Favs": "rpg"})), ["Favs"])


class Settings(unittest.TestCase):
    def test_nextui_has_no_theme_art(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as base, mock.patch.object(themeart, "install_knulli") as k, \
                contextlib.redirect_stdout(out):
            self.assertFalse(themeart.install("nextui", base, {"Favs": "surprise"}))
            themeart.describe("nextui", base, {"Favs": "surprise"})
            k.assert_not_called()
            self.assertEqual(os.listdir(base), [])
        self.assertEqual(out.getvalue(), "")

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
        self.base = self.enterContext(tempfile.TemporaryDirectory())
        self.warned = []
        self.enterContext(mock.patch.object(ui, "warn", self.warned.append))


class Esde(Card):
    """An ES-DE card, with storage a folder (runtime.ROOT) that may hold the theme archive."""
    def setUp(self):
        super().setUp()
        self.storage = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(runtime, "ROOT", self.storage))

    def store(self, commit, files):
        top = f"art-book-next-es-de-{commit}"
        write(os.path.join(self.storage, themeart.ESDE_COMMIT), commit + "\n")
        with open(os.path.join(self.storage, themeart.ESDE_ARCHIVE), "wb") as f:
            f.write(archive({f"{top}/{k}": v for k, v in files.items()}).getvalue())

    def settings(self, theme):
        write(frontend.settings_path("esde", self.base), f'<?xml version="1.0"?>\n<string name="Theme" value="{theme}" />\n')

    def install(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return themeart.install("esde", self.base, {**SURPRISE, "My Shmups": "shmups"})

    def copy(self, *rel):
        return os.path.join(self.base, "ES-DE", "themes", themeart.ESDE_COPY, *rel)

    def test_another_theme_is_left_alone(self):
        self.store("abc", {"theme.xml": b"<theme/>"})
        self.settings("linear-es-de")
        self.assertFalse(self.install())
        self.assertFalse(os.path.exists(self.copy()))

    def test_a_new_card_gets_the_theme_before_es_de_is_set_up(self):
        self.store("abc", {"theme.xml": b"<theme/>"})
        self.assertTrue(self.install())
        self.assertEqual(read(self.copy("theme.xml")), "<theme/>")
        self.assertIn(f'value="{themeart.ESDE_COPY}"', read(frontend.settings_path("esde", self.base)))

    def test_art_book_next_is_copied_with_the_surprise_files_and_selected(self):
        self.store("abc", {"theme.xml": b"<theme/>", "_inc/a.png": b"png"})
        self.settings(themeart.ESDE_THEME)
        self.assertTrue(self.install())
        self.assertEqual(read(self.copy("theme.xml")), "<theme/>")
        self.assertTrue(os.path.exists(self.copy("_inc", "systems", "artwork-outline", "surprise.png")))
        self.assertTrue(os.path.exists(self.copy("surprise", "theme.xml")))
        self.assertIn("<path ", read(self.copy("_inc", "systems", "logos", "my shmups.svg")))
        self.assertTrue(os.path.exists(self.copy("my shmups", "theme.xml")))
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

    def test_an_update_writes_only_the_changed_file_and_the_marker(self):
        self.settings(themeart.ESDE_THEME)
        self.store("abc", {"a.xml": b"<a/>", "b.xml": b"<b/>", "c.xml": b"<c/>"})
        self.install()
        self.store("def", {"a.xml": b"<a/>", "b.xml": b"<B/>", "c.xml": b"<c/>"})
        with mock.patch.object(themeart.store, "replace_file", wraps=themeart.store.replace_file) as put:
            self.assertTrue(self.install())
        wrote = {os.path.relpath(c.args[0], self.copy()) for c in put.call_args_list}
        self.assertEqual(wrote, {"b.xml", themeart.ESDE_MARKER})
        self.assertEqual(read(self.copy("b.xml")), "<B/>")
        self.assertEqual(read(self.copy(themeart.ESDE_MARKER)).strip(), "def")

    def test_an_update_deletes_a_removed_file_and_keeps_the_art_sync_roms_wrote(self):
        self.settings(themeart.ESDE_THEME)
        self.store("abc", {"theme.xml": b"<t/>", "old/x.xml": b"x"})
        self.install()
        art = ("_inc", "systems", "artwork-outline", "my shmups.png")
        self.assertTrue(os.path.exists(self.copy(*art)))
        os.makedirs(self.copy("stale-dir.disabled"), exist_ok=True)
        self.store("def", {"theme.xml": b"<t/>"})
        self.install()
        self.assertFalse(os.path.exists(self.copy("old")))
        for kept in (art, ("my shmups", "theme.xml"), ("surprise", "theme.xml"), (themeart.ESDE_OWNED,)):
            self.assertTrue(os.path.exists(self.copy(*kept)), kept)

    def test_a_file_the_archive_spells_in_other_capitals_is_not_deleted(self):
        self.settings(themeart.ESDE_THEME)
        self.store("abc", {"Foo.png": b"x"})
        self.install()
        self.store("def", {"foo.png": b"x"})
        with mock.patch.object(themeart.os, "remove") as remove:
            self.install()
        remove.assert_not_called()
        self.assertIn("foo.png", [n.lower() for n in os.listdir(self.copy())])

    def test_an_archive_failing_midway_deletes_nothing(self):
        self.settings(themeart.ESDE_THEME)
        self.store("abc", {"a.xml": b"<a/>", "gone.xml": b"x"})
        self.install()
        self.store("def", {"a.xml": b"<A/>", "b.xml": os.urandom(100000)})
        with open(os.path.join(self.storage, themeart.ESDE_ARCHIVE), "r+b") as f:
            f.truncate(os.path.getsize(f.name) // 2)
        self.assertFalse(self.install())
        self.assertTrue(os.path.exists(self.copy("gone.xml")))
        self.assertEqual(read(self.copy(themeart.ESDE_MARKER)).strip(), "abc")

    def test_a_leftover_disabled_folder_is_removed(self):
        self.settings(themeart.ESDE_THEME)
        write(self.copy("..", themeart.ESDE_COPY + "-disabled", "x"), "x")
        self.store("abc", {"theme.xml": b"<t/>"})
        self.install()
        self.assertFalse(os.path.exists(self.copy() + "-disabled"))

    THEME = {"theme.xml": b"<theme/>", "_inc/systems/artwork-outline/snes.png": b"png",
             "_inc/systems/logos/snes.svg": b"<svg/>", "_inc/systems/_metadata-global/snes.xml": b"<theme/>",
             "snes/theme.xml": b"<theme/>"}

    def art(self, folder):
        return [self.copy("_inc", "systems", "artwork-outline", f"{folder}.png"), self.copy("_inc", "systems", "logos", f"{folder}.svg"),
                self.copy("_inc", "systems", "_metadata-global", f"{folder}.xml"), self.copy(folder, "theme.xml")]

    def test_art_of_a_collection_that_is_gone_is_removed_and_the_rest_kept(self):
        self.store("abc", self.THEME)
        self.settings(themeart.ESDE_THEME)
        self.install()
        write(self.copy("_inc", "systems", "artwork-outline", "mine.png"), "mine")  # the user's own
        for path in self.art("my shmups"):
            self.assertTrue(os.path.exists(path), path)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(themeart.install("esde", self.base, dict(SURPRISE)))
        for path in self.art("my shmups"):
            self.assertFalse(os.path.exists(path), path)
        self.assertFalse(os.path.exists(self.copy("my shmups")))
        for path in self.art("surprise") + self.art("snes") + [self.copy("_inc", "systems", "artwork-outline", "mine.png")]:
            self.assertTrue(os.path.exists(path), path)
        self.assertEqual(read(self.copy(themeart.ESDE_OWNED)).splitlines(), ["surprise"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(themeart.install("esde", self.base, dict(SURPRISE)))  # nothing left to remove

    def test_art_of_a_collection_that_is_gone_does_not_survive_a_theme_update(self):
        self.store("abc", self.THEME)
        self.settings(themeart.ESDE_THEME)
        self.install()
        self.store("def", self.THEME)
        with contextlib.redirect_stdout(io.StringIO()):
            themeart.install("esde", self.base, dict(SURPRISE))
        for path in self.art("my shmups"):
            self.assertFalse(os.path.exists(path), path)
        for path in self.art("surprise") + self.art("snes"):
            self.assertTrue(os.path.exists(path), path)

    def test_the_last_collection_s_art_is_removed_without_copying_the_theme(self):
        self.store("abc", self.THEME)
        self.settings(themeart.ESDE_THEME)
        self.install()
        self.store("def", {"theme.xml": b"<newer/>"})
        settings = read(frontend.settings_path("esde", self.base))
        with mock.patch.object(themeart.s3, "download") as download:
            self.assertTrue(themeart.install("esde", self.base, {}))
            self.assertFalse(themeart.install("esde", self.base, {}))
        download.assert_not_called()
        for path in self.art("my shmups") + self.art("surprise"):
            self.assertFalse(os.path.exists(path), path)
        for path in self.art("snes"):
            self.assertTrue(os.path.exists(path), path)
        self.assertEqual(read(self.copy(themeart.ESDE_OWNED)), "")
        self.assertEqual(read(self.copy(themeart.ESDE_MARKER)).strip(), "abc")
        self.assertEqual(read(frontend.settings_path("esde", self.base)), settings)

    THEIRS = {"_inc/systems/_metadata-global/foo.xml": b"<theirs/>", "foo/theme.xml": b"<theirs/>"}

    def foo_is_the_theme_s(self):
        """Whether the theme copy has the theme's own foo, without the files only sync-roms wrote for it."""
        metadata, folder = (read(self.copy("_inc", "systems", "_metadata-global", "foo.xml")), read(self.copy("foo", "theme.xml")))
        return (metadata, folder, os.path.exists(self.copy("_inc", "systems", "artwork-outline", "foo.png"))) == ("<theirs/>", "<theirs/>", False)

    def test_a_listed_name_a_theme_update_ships_is_the_theme_s_and_is_not_removed(self):
        self.store("abc", self.THEME)
        self.settings(themeart.ESDE_THEME)
        with contextlib.redirect_stdout(io.StringIO()):
            themeart.install("esde", self.base, {**SURPRISE, "Foo": "rpg"})
            self.assertEqual(read(self.copy(themeart.ESDE_OWNED)).splitlines(), ["foo", "surprise"])
            self.store("def", {**self.THEME, **self.THEIRS})
            themeart.install("esde", self.base, dict(SURPRISE))  # Foo is gone in the sync that updates the theme
            self.assertTrue(self.foo_is_the_theme_s())
            self.assertEqual(read(self.copy(themeart.ESDE_OWNED)).splitlines(), ["surprise"])
            themeart.install("esde", self.base, {})
        self.assertTrue(self.foo_is_the_theme_s())

    def test_a_listed_name_a_theme_update_ships_is_skipped_while_still_wanted_and_kept_after(self):
        self.store("abc", self.THEME)
        self.settings(themeart.ESDE_THEME)
        with contextlib.redirect_stdout(io.StringIO()):
            themeart.install("esde", self.base, {**SURPRISE, "Foo": "rpg"})
            self.store("def", {**self.THEME, **self.THEIRS})
            themeart.install("esde", self.base, {**SURPRISE, "Foo": "rpg"})
            self.assertIn("Foo: Art Book Next already has art of its own", self.warned[-1])
            self.assertTrue(self.foo_is_the_theme_s())
            self.assertEqual(read(self.copy(themeart.ESDE_OWNED)).splitlines(), ["surprise"])
            themeart.install("esde", self.base, dict(SURPRISE))  # Foo is gone
        self.assertTrue(self.foo_is_the_theme_s())

    def test_the_dry_run_names_the_art_that_would_be_removed(self):
        self.store("abc", self.THEME)
        self.settings(themeart.ESDE_THEME)
        self.install()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("esde", self.base, dict(SURPRISE))
        self.assertIn(f"would remove the art for my shmups from ES-DE/themes/{themeart.ESDE_COPY}", out.getvalue())
        self.assertIn("would add art for Surprise", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as out, mock.patch.object(themeart, "_stored_commit") as commit:
            themeart.describe("esde", self.base, {})
        commit.assert_not_called()
        self.assertIn("would remove the art for my shmups, surprise from", out.getvalue())
        self.assertEqual(out.getvalue().count("\n"), 1)
        for path in self.art("my shmups") + self.art("surprise"):
            self.assertTrue(os.path.exists(path), path)
        self.assertEqual(read(self.copy(themeart.ESDE_OWNED)).splitlines(), ["my shmups", "surprise"])

    def test_the_dry_run_says_nothing_when_no_art_would_be_removed(self):
        self.store("abc", self.THEME)
        self.settings(themeart.ESDE_THEME)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("esde", self.base, {})  # no theme copy, no list
            self.install()
            themeart.describe("esde", self.base, {**SURPRISE, "My Shmups": "shmups"})
        self.assertNotIn("would remove", out.getvalue())

    def test_no_art_on_a_card_that_never_had_any_does_nothing(self):
        self.store("abc", self.THEME)
        self.assertFalse(themeart.install("esde", self.base, {}))
        self.assertEqual(os.listdir(self.base), [])
        write(self.copy("_inc", "systems", "artwork-outline", "old.png"), "x")  # a copy with no list of sync-roms's art
        self.assertFalse(themeart.install("esde", self.base, {}))
        self.assertEqual(os.listdir(self.copy()), ["_inc"])
        self.assertTrue(os.path.exists(self.copy("_inc", "systems", "artwork-outline", "old.png")))

    def test_a_listed_name_that_is_no_collection_name_removes_nothing(self):
        self.store("abc", self.THEME)
        self.settings(themeart.ESDE_THEME)
        self.install()
        outside = self.copy("..", "theme.xml")
        write(outside, "x")
        write(self.copy(themeart.ESDE_OWNED), "..\nsurprise\n")
        with contextlib.redirect_stdout(io.StringIO()):
            themeart.install("esde", self.base, dict(SURPRISE))
        self.assertTrue(os.path.exists(outside))
        self.assertEqual(read(self.copy(themeart.ESDE_OWNED)).splitlines(), ["surprise"])

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


class EsdeOwnArt(Esde):
    def test_a_name_the_theme_already_themes_is_skipped_but_one_sync_roms_wrote_is_kept(self):
        self.store("abc", {"theme.xml": b"<theme/>", "_inc/systems/_metadata-global/steam.xml": b"<theme/>"})
        self.settings(themeart.ESDE_THEME)
        with contextlib.redirect_stdout(io.StringIO()):
            themeart.install("esde", self.base, {"Steam": "horror", "My Shmups": "shmups"})
            self.assertFalse(themeart.install("esde", self.base, {"My Shmups": "shmups"}))
        self.assertIn("Steam", self.warned[0])
        self.assertFalse(os.path.exists(self.copy("_inc", "systems", "artwork-outline", "steam.png")))
        self.assertIn("<systemName>My Shmups</systemName>", read(self.copy("_inc", "systems", "_metadata-global", "my shmups.xml")))


class PixelArt(Card):
    """An ES-DE card whose selected theme is Pixel: collection art goes into Pixel's systems/ folders."""
    def setUp(self):
        super().setUp()
        self.storage = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(runtime, "ROOT", self.storage))
        self.settings_text = f'<?xml version="1.0"?>\n<string name="Theme" value="{esde_pixel.THEME}" />\n'
        write(frontend.settings_path("esde", self.base), self.settings_text)

    def pixel(self, *rel):
        return os.path.join(esde_pixel.dest("esde", self.base), *rel)

    def install(self, arts):
        with contextlib.redirect_stdout(io.StringIO()):
            return themeart.install("esde", self.base, arts)

    def box(self, art_id):
        with open(os.path.join(themeart.THEME_DATA, "art-box", "Imgs", f"{art_id}.png"), "rb") as f:
            return f.read()

    def test_pixel_selected_gets_box_art_in_both_variants(self):
        self.assertTrue(self.install({**SURPRISE, "My Shmups": "shmups"}))
        for variant in esde_pixel.ART_FOLDERS:
            with open(self.pixel("systems", variant, "my shmups.png"), "rb") as f:
                self.assertEqual(f.read(), self.box("shmups"))
            with open(self.pixel("systems", variant, "surprise.png"), "rb") as f:
                self.assertEqual(f.read(), self.box("surprise"))
        self.assertEqual(read(self.pixel(esde_pixel.OWNED)), "my shmups\nsurprise\n")
        self.assertFalse(os.path.exists(os.path.join(self.base, "ES-DE", "themes", themeart.ESDE_COPY)))
        self.assertFalse(self.install({**SURPRISE, "My Shmups": "shmups"}))  # nothing new the second time

    def test_pixel_selected_theme_setting_unchanged(self):
        self.install({**SURPRISE, "My Shmups": "shmups"})
        self.install({})
        self.assertEqual(read(frontend.settings_path("esde", self.base)), self.settings_text)

    def test_pixel_removes_gone_collection_art(self):
        self.install({**SURPRISE, "My Shmups": "shmups"})
        self.assertTrue(self.install(SURPRISE))
        for variant in esde_pixel.ART_FOLDERS:
            self.assertFalse(os.path.exists(self.pixel("systems", variant, "my shmups.png")))
            self.assertTrue(os.path.exists(self.pixel("systems", variant, "surprise.png")))
        self.assertEqual(read(self.pixel(esde_pixel.OWNED)), "surprise\n")
        self.install({})
        self.assertFalse(os.path.exists(self.pixel("systems", "consoles", "surprise.png")))
        self.assertEqual(read(self.pixel(esde_pixel.OWNED)), "")

    def test_each_collection_gets_a_theme_folder_that_a_pixel_install_keeps(self):
        # ES-DE groups a custom collection under "collections" unless the theme has <name>/theme.xml
        include = "<theme><include>./../theme.xml</include></theme>\n"
        self.install({**SURPRISE, "My Shmups": "shmups"})
        for name in ("my shmups", "surprise"):
            self.assertEqual(read(self.pixel(name, "theme.xml")), include)
        with contextlib.redirect_stdout(io.StringIO()):
            esde_pixel.install("esde", self.base)  # the art step runs first on a new card
            write(self.pixel(esde_pixel.MARKER), "an older build\n")
            self.assertTrue(esde_pixel.install("esde", self.base))
        for name in ("my shmups", "surprise"):
            self.assertEqual(read(self.pixel(name, "theme.xml")), include)
        self.assertTrue(os.path.exists(self.pixel("systems", "consoles", "my shmups.png")))
        self.install(SURPRISE)
        self.assertFalse(os.path.exists(self.pixel("my shmups")))
        self.assertTrue(os.path.exists(self.pixel("surprise", "theme.xml")))

    def test_no_delete_keeps_gone_collection_art(self):
        self.install({**SURPRISE, "My Shmups": "shmups"})
        with contextlib.redirect_stdout(io.StringIO()):
            themeart.install("esde", self.base, SURPRISE, keep=True)
        self.assertTrue(os.path.exists(self.pixel("systems", "consoles", "my shmups.png")))
        self.assertIn("my shmups", read(self.pixel(esde_pixel.OWNED)))

    def test_reserved_name_never_overwrites_a_system_sprite(self):
        sprite = self.pixel("systems", "consoles", "snes.png")
        os.makedirs(os.path.dirname(sprite))
        with open(sprite, "wb") as f:
            f.write(b"the system's own sprite")
        self.install({"SNES": "shmups"})
        with open(sprite, "rb") as f:
            self.assertEqual(f.read(), b"the system's own sprite")
        self.assertIn("SNES", self.warned[0])
        self.assertFalse(os.path.exists(self.pixel(esde_pixel.OWNED)))

    def test_a_name_pixel_has_a_sprite_for_is_skipped_on_emudeck(self):
        appdata = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.dict(os.environ, {"ESDE_APPDATA_DIR": appdata}))
        write(os.path.join(appdata, "settings", "es_settings.xml"), self.settings_text)
        with contextlib.redirect_stdout(io.StringIO()):  # ps4 has no emudeck folder, so usable lets it through
            themeart.install("emudeck", self.base, {"PS4": "shmups", "My Shmups": "shmups"})
        pixel = esde_pixel.dest("emudeck", self.base)
        self.assertFalse(os.path.exists(os.path.join(pixel, "systems", "consoles", "ps4.png")))
        self.assertTrue(os.path.exists(os.path.join(pixel, "systems", "consoles", "my shmups.png")))
        self.assertIn("PS4", self.warned[0])

    def test_the_dry_run_names_pixel_and_selects_nothing(self):
        self.install({"My Shmups": "shmups"})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("esde", self.base, SURPRISE)
        self.assertIn("would add art for Surprise to", out.getvalue())
        self.assertIn(esde_pixel.THEME, out.getvalue())
        self.assertIn("would remove the art for my shmups", out.getvalue())
        self.assertNotIn("select", out.getvalue())

    def test_new_card_still_gets_art_book_next(self):
        os.remove(frontend.settings_path("esde", self.base))
        Esde.store(self, "abc", {"theme.xml": b"<theme/>"})
        self.assertTrue(self.install(SURPRISE))
        self.assertIn(f'value="{themeart.ESDE_COPY}"', read(frontend.settings_path("esde", self.base)))
        self.assertFalse(os.path.exists(self.pixel()))


class Emudeck(Esde):
    """An EmuDeck card: the theme goes into ES-DE's folder on this computer, not on the card."""
    def setUp(self):
        super().setUp()
        self.appdata = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.dict(os.environ, {"ESDE_APPDATA_DIR": self.appdata}))

    def test_the_theme_and_art_go_into_es_de_on_this_computer_and_are_selected(self):
        self.store("abc", {"theme.xml": b"<theme/>"})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertTrue(themeart.install("emudeck", self.base, {**SURPRISE, "My Shmups": "shmups"}))
        copy = os.path.join(self.appdata, "themes", themeart.ESDE_COPY)
        self.assertIn(os.path.join(os.path.basename(self.appdata), "themes", themeart.ESDE_COPY), out.getvalue())
        self.assertTrue(os.path.exists(os.path.join(copy, "_inc", "systems", "artwork-outline", "surprise.png")))
        self.assertTrue(os.path.exists(os.path.join(copy, "my shmups", "theme.xml")))
        self.assertIn(f'<string name="Theme" value="{themeart.ESDE_COPY}" />',
                      read(os.path.join(self.appdata, "settings", "es_settings.xml")))
        self.assertEqual(os.listdir(self.base), [])

    def test_art_of_a_collection_that_is_gone_is_removed_from_es_de_on_this_computer(self):
        self.store("abc", {"theme.xml": b"<theme/>"})
        copy = os.path.join(self.appdata, "themes", themeart.ESDE_COPY)
        with contextlib.redirect_stdout(io.StringIO()):
            themeart.install("emudeck", self.base, {**SURPRISE, "My Shmups": "shmups"})
            self.assertTrue(themeart.install("emudeck", self.base, {}))
        self.assertFalse(os.path.exists(os.path.join(copy, "my shmups")))
        self.assertFalse(os.path.exists(os.path.join(copy, "_inc", "systems", "artwork-outline", "surprise.png")))
        self.assertEqual(os.listdir(self.base), [])

    def test_the_dry_run_names_es_de_on_this_computer(self):
        self.store("abc", {"theme.xml": b"<theme/>"})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("emudeck", self.base, SURPRISE)
        self.assertIn(f"{os.path.basename(self.appdata)}/themes/{themeart.ESDE_COPY}", out.getvalue())

    def test_another_theme_is_left_alone(self):
        self.store("abc", {"theme.xml": b"<theme/>"})
        write(os.path.join(self.appdata, "settings", "es_settings.xml"),
              '<?xml version="1.0"?>\n<string name="Theme" value="linear-es-de" />\n')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(themeart.install("emudeck", self.base, SURPRISE))
        self.assertFalse(os.path.exists(os.path.join(self.appdata, "themes")))


class Update(Esde):
    def run_update(self, latest, tarball=b"", dry_run=False):
        def fake(url, accept=None):
            return io.BytesIO(latest.encode() if "api.github.com" in url else tarball)
        with mock.patch.object(github, "get", fake), contextlib.redirect_stdout(io.StringIO()):
            return themeart.update_storage(dry_run)

    def test_storage_gets_the_latest_archive_and_commit(self):
        tarball = archive({"top/theme.xml": b"<theme/>"}).getvalue()
        self.assertEqual(self.run_update("abc", tarball), 0)
        self.assertEqual(read(os.path.join(self.storage, themeart.ESDE_COMMIT)).strip(), "abc")
        with open(os.path.join(self.storage, themeart.ESDE_ARCHIVE), "rb") as f:
            self.assertEqual(f.read(), tarball)

    def test_a_download_with_a_length_gets_a_bar_and_uploads(self):
        tarball = archive({"top/theme.xml": b"<theme/>"}).getvalue()

        class Response(io.BytesIO):
            headers = {"Content-Length": str(len(tarball))}

        def fake(url, accept=None):
            return Response(b"abc" if "api.github.com" in url else tarball)
        with mock.patch.object(github, "get", fake), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(themeart.update_storage(), 0)
        self.assertIn("Downloading Art Book Next", out.getvalue())
        with open(os.path.join(self.storage, themeart.ESDE_ARCHIVE), "rb") as f:
            self.assertEqual(f.read(), tarball)

    def test_a_failed_download_with_a_length_clears_the_bar(self):
        class Response(io.BytesIO):
            headers = {"Content-Length": "10"}

            def read(self, n=-1):
                raise OSError("reset")

        def fake(url, accept=None):
            return io.BytesIO(b"abc") if "api.github.com" in url else Response()
        with mock.patch.object(github, "get", fake), mock.patch.object(themeart.ui.ProgressBar, "clear") as clear, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(themeart.update_storage(), 1)
        clear.assert_called()

    def test_the_latest_already_in_storage_is_left_alone(self):
        self.store("abc", {"theme.xml": b"<theme/>"})
        self.assertEqual(self.run_update("abc", b"not used"), 0)

    def test_a_missing_storage_folder_or_failed_upload_fails(self):
        with mock.patch.object(runtime, "ROOT", os.path.join(self.storage, "gone")):
            self.assertEqual(self.run_update("abc"), 1)
        with mock.patch.object(themeart.s3, "copy_file", mock.Mock(side_effect=PermissionError("denied"))):
            self.assertEqual(self.run_update("abc", archive({"top/a": b"a"}).getvalue()), 1)
        self.assertIn("Couldn't upload Art Book Next", self.warned[-1])
        self.assertFalse(os.path.exists(os.path.join(self.storage, themeart.ESDE_COMMIT)))

    def test_a_dry_run_or_a_bad_download_changes_nothing(self):
        self.store("abc", {"theme.xml": b"<theme/>"})
        self.assertEqual(self.run_update("def", archive({"top/a": b"a"}).getvalue(), dry_run=True), 0)
        self.assertEqual(self.run_update("def", b"not a tar.gz"), 1)
        self.assertEqual(read(os.path.join(self.storage, themeart.ESDE_COMMIT)).strip(), "abc")


class Knulli(Card):
    def path(self, *rel):
        return os.path.join(self.base, "theme-customizations", "art-book-next", *rel)

    def test_art_and_settings_for_the_collection(self):
        self.assertTrue(themeart.install("knulli", self.base, SURPRISE))
        self.assertTrue(os.path.exists(self.path("artwork", "Surprise.png")))
        self.assertIn("<path ", read(self.path("logos", "Surprise.svg")))
        settings = read(frontend.settings_path("knulli", self.base))
        for name, value in themeart.knulli_settings("Surprise").items():
            self.assertIn(f'<string name="{name}" value="{value}" />', settings)
        self.assertFalse(themeart.install("knulli", self.base, SURPRISE))  # nothing new the second time

    def test_a_name_without_a_logo_keeps_the_text_name(self):
        themeart.install("knulli", self.base, {"東方": "shmups"})
        self.assertTrue(os.path.exists(self.path("artwork", "東方.png")))
        self.assertFalse(os.path.exists(self.path("logos", "東方.svg")))
        settings = read(frontend.settings_path("knulli", self.base))
        self.assertIn("subset.東方.system-view-artwork", settings)
        self.assertNotIn("subset.東方.system-logos", settings)

    def test_a_name_with_an_ampersand_keeps_the_settings_well_formed(self):
        for _ in range(2):  # the second sync replaces the entries
            themeart.install("knulli", self.base, {"Mario & Sonic": "surprise"})
        entries = minidom.parse(frontend.settings_path("knulli", self.base)).getElementsByTagName("string")
        self.assertEqual({e.getAttribute("name"): e.getAttribute("value") for e in entries},
                         themeart.knulli_settings("Mario & Sonic"))
        self.assertEqual(len(entries), 3)

    def test_a_grouping_choice_already_made_is_kept(self):
        path = frontend.settings_path("knulli", self.base)
        write(path, '<config>\n\t<string name="UseCustomCollectionsSystemEx" value="true" />\n</config>\n')
        themeart.install("knulli", self.base, SURPRISE)
        settings = read(path)
        self.assertIn('name="UseCustomCollectionsSystemEx" value="true"', settings)
        self.assertIn('name="subset.Surprise.system-view-artwork" value="custom"', settings)

    def test_another_theme_is_left_alone(self):
        path = frontend.settings_path("knulli", self.base)
        write(path, '<config>\n\t<string name="ThemeSet" value="es-theme-carbon" />\n</config>\n')
        self.assertFalse(themeart.install("knulli", self.base, SURPRISE))
        self.assertFalse(os.path.exists(self.path()))
        self.assertNotIn("subset.", read(path))

    def test_art_and_settings_of_a_collection_that_is_gone_are_removed_and_the_rest_kept(self):
        themeart.install("knulli", self.base, {**SURPRISE, "Favs": "rpg"})
        write(self.path("artwork", "Mine.png"), "mine")  # the user's own
        path = frontend.settings_path("knulli", self.base)
        write(path, read(path).replace("</config>", '\t<string name="subset.Mine.system-view-artwork" value="custom" />\n</config>'))
        self.assertEqual(read(self.path(themeart.CUSTOM_OWNED)).splitlines(), ["Favs", "Surprise"])
        self.assertTrue(themeart.install("knulli", self.base, dict(SURPRISE)))
        for rel in (("artwork", "Favs.png"), ("logos", "Favs.svg")):
            self.assertFalse(os.path.exists(self.path(*rel)), rel)
        for rel in (("artwork", "Surprise.png"), ("logos", "Surprise.svg"), ("artwork", "Mine.png")):
            self.assertTrue(os.path.exists(self.path(*rel)), rel)
        self.assertEqual(read(self.path(themeart.CUSTOM_OWNED)).splitlines(), ["Surprise"])
        settings = read(path)
        self.assertNotIn("subset.Favs.", settings)
        for name in ("subset.Surprise.system-view-artwork", "subset.Surprise.system-logos", "subset.Mine.system-view-artwork"):
            self.assertIn(f'<string name="{name}" value="custom" />', settings)
        self.assertIn('<string name="UseCustomCollectionsSystemEx" value="false" />', settings)
        self.assertTrue(settings.endswith("</config>\n"))
        self.assertFalse(themeart.install("knulli", self.base, dict(SURPRISE)))  # nothing left to remove

    def test_keep_leaves_the_art_and_settings_of_a_collection_that_is_gone_and_listed(self):
        themeart.install("knulli", self.base, {**SURPRISE, "Favs": "rpg"})
        self.assertFalse(themeart.install("knulli", self.base, dict(SURPRISE), keep=True))
        for rel in (("artwork", "Favs.png"), ("logos", "Favs.svg"), ("artwork", "Surprise.png")):
            self.assertTrue(os.path.exists(self.path(*rel)), rel)
        self.assertEqual(read(self.path(themeart.CUSTOM_OWNED)).splitlines(), ["Favs", "Surprise"])
        self.assertIn("subset.Favs.", read(frontend.settings_path("knulli", self.base)))
        self.assertTrue(themeart.install("knulli", self.base, dict(SURPRISE)))  # a later sync without it removes them
        self.assertFalse(os.path.exists(self.path("artwork", "Favs.png")))

    def test_the_last_collection_s_art_and_settings_are_removed(self):
        themeart.install("knulli", self.base, dict(SURPRISE))
        self.assertTrue(themeart.install("knulli", self.base, {}))
        for rel in (("artwork", "Surprise.png"), ("logos", "Surprise.svg"), (themeart.CUSTOM_OWNED,)):
            self.assertFalse(os.path.exists(self.path(*rel)), rel)
        settings = read(frontend.settings_path("knulli", self.base))
        self.assertNotIn("subset.", settings)
        self.assertIn('<string name="UseCustomCollectionsSystemEx" value="false" />', settings)
        self.assertFalse(themeart.install("knulli", self.base, {}))

    def test_the_dry_run_names_the_art_and_settings_that_would_be_removed(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("knulli", self.base, {})  # no list: nothing to say
        self.assertEqual(out.getvalue(), "")
        themeart.install("knulli", self.base, {**SURPRISE, "Favs": "rpg"})
        settings = read(frontend.settings_path("knulli", self.base))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("knulli", self.base, dict(SURPRISE))
        self.assertIn("would remove the art and settings for Favs from theme-customizations/art-book-next/", out.getvalue())
        self.assertIn("would add art for Surprise", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("knulli", self.base, {})
        self.assertIn("would remove the art and settings for Favs, Surprise from", out.getvalue())
        self.assertEqual(out.getvalue().count("\n"), 1)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("knulli", self.base, {**SURPRISE, "Favs": "rpg"})
        self.assertNotIn("would remove", out.getvalue())
        self.assertTrue(os.path.exists(self.path("artwork", "Favs.png")))
        self.assertEqual(read(frontend.settings_path("knulli", self.base)), settings)

    def test_art_and_settings_sync_roms_has_no_list_of_are_kept(self):
        self.assertFalse(themeart.install("knulli", self.base, {}))
        self.assertEqual(os.listdir(self.base), [])  # a card that never had art: nothing is written
        write(self.path("artwork", "Old.png"), "old")
        path = frontend.settings_path("knulli", self.base)
        write(path, '<config>\n\t<string name="subset.Old.system-view-artwork" value="custom" />\n</config>\n')
        self.assertFalse(themeart.install("knulli", self.base, {}))
        themeart.install("knulli", self.base, dict(SURPRISE))
        themeart.install("knulli", self.base, {})
        self.assertEqual(read(self.path("artwork", "Old.png")), "old")
        self.assertIn('<string name="subset.Old.system-view-artwork" value="custom" />', read(path))

    def test_settings_of_a_gone_collection_with_an_ampersand_are_removed_escaped_or_not(self):
        path = frontend.settings_path("knulli", self.base)
        for raw in (False, True):  # as sync-roms writes the names now, and as it did before
            with self.subTest(raw=raw):
                themeart.install("knulli", self.base, {"Mario & Sonic": "surprise", "Mario": "rpg"})
                if raw:
                    write(path, read(path).replace("&amp;", "&"))
                self.assertEqual(read(path).count('name="subset.Mario &amp; Sonic.'), 0 if raw else 2)
                self.assertEqual(read(path).count('name="subset.Mario & Sonic.'), 2 if raw else 0)
                themeart.install("knulli", self.base, {"Mario": "rpg"})
                entries = minidom.parse(path).getElementsByTagName("string")
                self.assertEqual({e.getAttribute("name"): e.getAttribute("value") for e in entries},
                                 themeart.knulli_settings("Mario"))
                self.assertFalse(os.path.exists(self.path("artwork", "Mario & Sonic.png")))

    def test_a_collection_renamed_in_other_capitals_keeps_its_art(self):
        themeart.install("knulli", self.base, {"Favs": "rpg"})
        themeart.install("knulli", self.base, {"favs": "rpg"})
        self.assertIn("favs.png", os.listdir(self.path("artwork")))
        self.assertEqual(read(self.path(themeart.CUSTOM_OWNED)).splitlines(), ["favs"])
        settings = read(frontend.settings_path("knulli", self.base))
        self.assertNotIn("subset.Favs.", settings)
        self.assertIn('<string name="subset.favs.system-view-artwork" value="custom" />', settings)


class Rocknix(Card):
    """ROCKNIX's Art Book Next takes its customizations from ~/roms/_userdata/ (the card's roms/_userdata/)."""
    def path(self, *rel):
        return os.path.join(self.base, "roms", "_userdata", "theme-customizations", "art-book-next", *rel)

    def test_art_goes_in_the_card_s_customizations_and_no_knulli_code_runs(self):
        with mock.patch.object(themeart, "install_knulli") as k:
            self.assertTrue(themeart.install("rocknix", self.base, SURPRISE))
            k.assert_not_called()
        with open(self.path("artwork", "Surprise.png"), "rb") as f, open(themeart.art_png("surprise"), "rb") as g:
            self.assertEqual(f.read(), g.read())
        self.assertIn("<path ", read(self.path("logos", "Surprise.svg")))
        self.assertFalse(os.path.exists(os.path.join(self.base, "theme-customizations")))
        self.assertFalse(os.path.exists(os.path.join(self.base, "system")))  # the settings are the install script's
        self.assertFalse(themeart.install("rocknix", self.base, SURPRISE))  # nothing new the second time

    def test_a_name_without_a_logo_gets_only_its_artwork(self):
        themeart.install("rocknix", self.base, {"東方": "shmups"})
        self.assertTrue(os.path.exists(self.path("artwork", "東方.png")))
        self.assertFalse(os.path.exists(self.path("logos", "東方.svg")))

    def test_art_of_a_collection_that_is_gone_is_removed_and_the_rest_kept(self):
        themeart.install("rocknix", self.base, {**SURPRISE, "Favs": "rpg"})
        write(self.path("artwork", "Mine.png"), "mine")  # the user's own
        self.assertEqual(read(self.path(themeart.CUSTOM_OWNED)).splitlines(), ["Favs", "Surprise"])
        self.assertTrue(themeart.install("rocknix", self.base, dict(SURPRISE)))
        for rel in (("artwork", "Favs.png"), ("logos", "Favs.svg")):
            self.assertFalse(os.path.exists(self.path(*rel)), rel)
        for rel in (("artwork", "Surprise.png"), ("logos", "Surprise.svg"), ("artwork", "Mine.png")):
            self.assertTrue(os.path.exists(self.path(*rel)), rel)
        self.assertEqual(read(self.path(themeart.CUSTOM_OWNED)).splitlines(), ["Surprise"])
        self.assertFalse(themeart.install("rocknix", self.base, dict(SURPRISE)))  # nothing left to remove

    def test_the_last_collection_s_art_is_removed(self):
        themeart.install("rocknix", self.base, dict(SURPRISE))
        self.assertTrue(themeart.install("rocknix", self.base, {}))
        for rel in (("artwork", "Surprise.png"), ("logos", "Surprise.svg"), (themeart.CUSTOM_OWNED,)):
            self.assertFalse(os.path.exists(self.path(*rel)), rel)
        self.assertFalse(themeart.install("rocknix", self.base, {}))

    def test_the_dry_run_names_the_art_that_would_be_removed(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("rocknix", self.base, {})  # no list: nothing to say
        self.assertEqual(out.getvalue(), "")
        themeart.install("rocknix", self.base, {**SURPRISE, "Favs": "rpg"})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("rocknix", self.base, dict(SURPRISE))
        self.assertIn("would remove the art for Favs from roms/_userdata/theme-customizations/art-book-next/", out.getvalue())
        self.assertIn("would add art for Surprise", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("rocknix", self.base, {})
        self.assertIn("would remove the art for Favs, Surprise from", out.getvalue())
        self.assertEqual(out.getvalue().count("\n"), 1)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("rocknix", self.base, {**SURPRISE, "Favs": "rpg"})
        self.assertNotIn("would remove", out.getvalue())
        self.assertTrue(os.path.exists(self.path("artwork", "Favs.png")))

    def test_art_sync_roms_has_no_list_of_is_kept(self):
        self.assertFalse(themeart.install("rocknix", self.base, {}))
        self.assertEqual(os.listdir(self.base), [])  # a card that never had art: nothing is written
        write(self.path("artwork", "Old.png"), "old")
        self.assertFalse(themeart.install("rocknix", self.base, {}))
        themeart.install("rocknix", self.base, dict(SURPRISE))
        themeart.install("rocknix", self.base, {})
        self.assertEqual(read(self.path("artwork", "Old.png")), "old")

    def test_describe(self):
        out = io.StringIO()
        with mock.patch.object(themeart, "describe_knulli") as k, contextlib.redirect_stdout(out):
            themeart.describe("rocknix", self.base, SURPRISE)
            k.assert_not_called()
        self.assertIn("would add art for Surprise to roms/_userdata/theme-customizations/art-book-next/",
                      out.getvalue())
        self.assertFalse(os.path.exists(self.path()))


class Muos(Card):
    def path(self, kind, name):
        return os.path.join(self.base, "MUOS", "info", "catalogue", "Collection", kind, f"{name}.png")

    def test_install_art_copies_box_and_grid(self):
        self.assertTrue(themeart.install("muos", self.base, SURPRISE))
        for kind in ("box", "grid"):
            with open(self.path(kind, "Surprise"), "rb") as f, open(themeart.art_png("surprise"), "rb") as g:
                self.assertEqual(f.read(), g.read())

    def test_install_art_second_run_changes_nothing(self):
        themeart.install("muos", self.base, SURPRISE)
        self.assertFalse(themeart.install("muos", self.base, SURPRISE))

    def test_install_art_removes_art_of_dropped_collections_it_wrote(self):
        themeart.install("muos", self.base, {"Surprise": "surprise", "Favs": "rpg"})
        other = self.path("box", "Mine")
        os.makedirs(os.path.dirname(other), exist_ok=True)
        with open(other, "wb") as f:
            f.write(b"x")
        marker = os.path.join(self.base, "MUOS", "info", "catalogue", "Collection", ".sync-roms-art")
        self.assertEqual(sorted(read(marker).splitlines()), ["Favs", "Surprise"])
        self.assertTrue(themeart.install("muos", self.base, SURPRISE))
        for kind in ("box", "grid"):
            self.assertFalse(os.path.exists(self.path(kind, "Favs")))
            self.assertTrue(os.path.exists(self.path(kind, "Surprise")))
        self.assertTrue(os.path.exists(other))
        self.assertEqual(read(marker).splitlines(), ["Surprise"])

    def test_a_collection_renamed_in_other_capitals_keeps_its_art(self):
        themeart.install("muos", self.base, {"Favs": "rpg"})
        themeart.install("muos", self.base, {"favs": "rpg"})  # a card that ignores case has one file for both
        for kind in ("box", "grid"):
            self.assertIn("favs.png", os.listdir(os.path.dirname(self.path(kind, "favs"))))
        marker = os.path.join(self.base, "MUOS", "info", "catalogue", "Collection", ".sync-roms-art")
        self.assertEqual(read(marker).splitlines(), ["favs"])

    def test_the_dry_run_names_the_art_that_would_be_removed(self):
        themeart.install("muos", self.base, {**SURPRISE, "Favs": "rpg"})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            themeart.describe("muos", self.base, dict(SURPRISE))
        self.assertIn("would remove the art for Favs from MUOS/info/catalogue/Collection/", out.getvalue())
        self.assertIn("would add art for Surprise to MUOS/info/catalogue/Collection/", out.getvalue())
        self.assertTrue(os.path.exists(self.path("box", "Favs")))

    def test_describe_lists_the_names(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            themeart.describe("muos", self.base, SURPRISE)
        self.assertIn("Surprise", out.getvalue())
        self.assertFalse(os.path.exists(self.path("box", "Surprise")))


class Spruce(Card):
    def path(self, name, size="Imgs"):
        return os.path.join(self.base, "Collections", size, f"{name}.png")

    def test_all_three_sizes_are_written_to_a_fresh_card(self):
        self.assertTrue(themeart.install("spruce", self.base, SURPRISE))
        for size in themeart.SPRUCE_SIZES:
            with open(self.path("Surprise", size), "rb") as f, \
                    open(themeart.art_png("surprise", f"art-box/{size}"), "rb") as g:
                self.assertEqual(f.read(), g.read())
        self.assertFalse(themeart.install("spruce", self.base, SURPRISE))

    def zelda(self, art_id, size="Imgs"):
        return os.path.join(themeart.ZELDA_ART, size, f"{art_id}.png")

    def test_totk_cards_get_the_zelda_art(self):
        for theme in themeart.ZELDA_THEMES:
            self.assertEqual(themeart.install("spruce", self.base, SURPRISE, spruce_theme=theme),
                             theme == themeart.ZELDA_THEMES[0])  # the second theme's files are already there
            for size in themeart.SPRUCE_SIZES:
                with open(self.path("Surprise", size), "rb") as f, open(self.zelda("surprise", size), "rb") as g:
                    self.assertEqual(f.read(), g.read())

    def test_other_themes_get_the_box_art(self):
        for theme in (None, "ToTK - James ", "Art Book Next"):
            themeart.install("spruce", self.base, SURPRISE, spruce_theme=theme)
            with open(self.path("Surprise"), "rb") as f, open(themeart.art_png("surprise", "art-box/Imgs"), "rb") as g:
                self.assertEqual(f.read(), g.read(), theme)

    def test_switching_theme_swaps_the_art(self):
        themeart.install("spruce", self.base, SURPRISE, spruce_theme="ToTK")
        self.assertTrue(themeart.install("spruce", self.base, SURPRISE))
        self.assertFalse(themeart.install("spruce", self.base, SURPRISE))

    def test_old_square_art_is_replaced(self):
        from PIL import Image
        write(self.path("Surprise"), "old 300x300")
        self.assertTrue(themeart.install("spruce", self.base, SURPRISE))
        with Image.open(self.path("Surprise")) as im:
            self.assertEqual(im.size, (336, 480))

    def test_changed_art_is_rewritten(self):
        themeart.install("spruce", self.base, SURPRISE)
        for size in themeart.SPRUCE_SIZES:
            with open(self.path("Surprise", size), "wb") as f:
                f.write(b"old")
            self.assertTrue(themeart.install("spruce", self.base, SURPRISE))
            self.assertNotEqual(os.path.getsize(self.path("Surprise", size)), 3)

    def test_a_name_of_a_system_or_built_in_collection_is_fine(self):
        self.assertTrue(themeart.install("spruce", self.base, {"Favorites": "rpg"}))
        for size in themeart.SPRUCE_SIZES:
            self.assertTrue(os.path.exists(self.path("Favorites", size)))
        self.assertEqual(self.warned, [])

    def test_owned_collections_without_art_lose_all_sizes_and_other_files_stay(self):
        themeart.install("spruce", self.base, {"Surprise": "surprise", "Favs": "rpg"})
        for size in themeart.SPRUCE_SIZES:
            write(self.path("Mine", size), "x")
        self.assertTrue(themeart.install("spruce", self.base, SURPRISE, {"Surprise", "Favs"}))
        for size in themeart.SPRUCE_SIZES:
            self.assertFalse(os.path.exists(self.path("Favs", size)))
            self.assertTrue(os.path.exists(self.path("Surprise", size)))
            self.assertTrue(os.path.exists(self.path("Mine", size)))
        self.assertTrue(themeart.install("spruce", self.base, {}, {"Surprise"}))
        for size in themeart.SPRUCE_SIZES:
            self.assertFalse(os.path.exists(self.path("Surprise", size)))
            self.assertTrue(os.path.exists(self.path("Mine", size)))

    def test_a_picture_of_a_collection_sync_roms_does_not_own_is_kept(self):
        write(self.path("Mine"), "x")
        self.assertFalse(themeart.install("spruce", self.base, {}, {"Surprise"}))
        self.assertTrue(os.path.exists(self.path("Mine")))

    def test_describe_prints_and_writes_nothing(self):
        themeart.install("spruce", self.base, {"Favs": "rpg"})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            themeart.describe("spruce", self.base, SURPRISE, {"Favs"})
        text = out.getvalue()
        self.assertEqual(text.count("would remove"), 1)
        self.assertIn("would remove the art for Favs from Collections/Imgs/ (and Imgs_med/, Imgs_small/)", text)
        self.assertIn("would add the art for Surprise", text)
        for size in themeart.SPRUCE_SIZES:
            self.assertFalse(os.path.exists(self.path("Surprise", size)))
            self.assertTrue(os.path.exists(self.path("Favs", size)))


if __name__ == "__main__":
    unittest.main()
