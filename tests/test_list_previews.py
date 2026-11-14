import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import collectionedit, diff, edit, listedit, picker, previews, setedit, store, surprise, upload  # noqa: E402

SYSTEMS = [{"name": "Game Boy Advance", "bucket": "gba"}, {"name": "PlayStation", "bucket": "psx"}]


def capture(returns):
    """A fake picker.filter_list that records each call's kwargs and answers from returns."""
    calls, answers = [], iter(returns)

    def fake(title, labels, **kw):
        calls.append(kw)
        return next(answers)
    return fake, calls


def art(calls, n, index=0):
    with mock.patch.object(previews, "collection", side_effect=lambda a: "art-" + str(a)), \
            mock.patch.object(previews, "system", side_effect=lambda s: "sys-" + s["bucket"]):
        return [calls[index]["preview"](i) for i in range(n)]


class ListPreviews(unittest.TestCase):
    def test_collection_and_set_lists_preview_each_row_and_nothing_for_the_menu_rows(self):
        def stop(title, labels, **kw):
            calls.append(kw)
            raise KeyboardInterrupt
        for module, args, expect in (
                (collectionedit, (), ["art-surprise", "art-None", None, None, None]),
                (setedit, ({"review": False},), ["art-a", "art-b", None, None, None])):
            calls = []
            working = {"a": {"name": "A", "art": "surprise", "games": []}, "b": {"name": "B", "games": []}}
            with mock.patch.object(picker, "filter_list", stop):
                with self.assertRaises(KeyboardInterrupt):
                    module.edit_working(SYSTEMS, {}, working, *args)
            self.assertEqual(art(calls, 5), expect, module.__name__)

    def test_system_pickers_preview_the_system_in_the_row(self):
        for module in (upload, diff):
            fake, calls = capture([None])
            with mock.patch.object(store, "load_manifest", return_value={"systems": SYSTEMS}), \
                    mock.patch.object(store, "guess_system", return_value=None), \
                    mock.patch.object(picker, "filter_list", fake), mock.patch("builtins.print"), \
                    mock.patch.object(os.path, "isdir", return_value=True):
                if module is upload:
                    upload.upload_command(mock.Mock(upload="/x"))
                else:
                    diff.diff_command(mock.Mock(diff="/x", system=None, json=False))
            self.assertEqual(art(calls, 2), ["sys-gba", "sys-psx"], module.__name__)

    def test_add_games_from_set_previews_the_set_by_id(self):
        fake, calls = capture([None])
        sets = [{"id": "pk", "name": "Pokemon", "games": []}]
        with mock.patch.object(picker, "filter_list", fake):
            listedit.add_from_set(None, sets, None, None, "x")
        self.assertEqual(art(calls, 1), ["art-pk"])

    def test_add_games_from_which_system_previews_the_system(self):
        for module, edit_one in ((setedit, setedit.edit_one), (collectionedit, collectionedit.edit_one)):
            fake, calls = capture([1, None, None])  # "add games from a system", then Esc, then back
            thing = {"name": "X", "games": []}
            with mock.patch.object(picker, "filter_list", fake), mock.patch.object(module, "stocked", return_value=SYSTEMS):
                try:
                    edit_one(thing, SYSTEMS, lambda bucket: set())
                except StopIteration:
                    pass
            self.assertEqual(art(calls, 3, 1), ["sys-gba", "sys-psx", None], module.__name__)


class GamePreviews(unittest.TestCase):
    def games(self, calls, n, index=0):
        with mock.patch.object(previews, "game", side_effect=lambda k: "img-" + k):
            return [calls[index]["preview"](i) for i in range(n)]

    def test_toggle_games_previews_the_row_key_and_nothing_past_the_rows(self):
        fake, calls = capture([[False, False]])
        s = {"name": "GBA", "bucket": "gba", "games": []}
        rows = [(s, "gba/A.zip", "A", "A"), (s, "gba/B.zip", "B", "B")]
        with mock.patch.object(picker, "filter_list", fake):
            edit.toggle_games("t", rows)
        self.assertEqual(self.games(calls, 3), ["img-gba/A.zip", "img-gba/B.zip", None])

    def test_change_category_lists_preview_the_game_bucket_skipping_rows_without_one(self):
        for module, edit_one in ((setedit, setedit.edit_one), (collectionedit, collectionedit.edit_one)):
            fake, calls = capture([3, None, None])  # "change which game's category?", then Esc, then back
            thing = {"name": "X", "games": [{"system": "gba", "bucket": "gba/A.zip"}, {"title": "no bucket"},
                                            {"system": "psx", "bucket": "psx/B.bin"}]}
            with mock.patch.object(picker, "filter_list", fake), mock.patch.object(module, "stocked", return_value=SYSTEMS):
                try:
                    edit_one(thing, SYSTEMS, lambda bucket: set())
                except StopIteration:
                    pass
            self.assertEqual(self.games(calls, 3, 1), ["img-gba/A.zip", "img-psx/B.bin", None], module.__name__)

    def stop_after(self, calls):
        def stop(title, labels, **kw):
            calls.append(kw)
            raise KeyboardInterrupt
        return stop

    def test_upload_delete_list_previews_the_storage_only_files(self):
        calls = []
        with mock.patch.object(upload.diff, "local_sizes", return_value={}), \
                mock.patch.object(upload.inventory, "etags", return_value={"Old.zip": (1, "e")}), \
                mock.patch.object(upload.diff, "plan_replace", return_value=([], [], [], ["Old.zip"])), \
                mock.patch.object(upload.ignore, "is_ignored", return_value=False), \
                mock.patch.object(picker, "filter_list", self.stop_after(calls)), mock.patch("builtins.print"):
            with self.assertRaises(KeyboardInterrupt):
                upload.replace_command(mock.Mock(dry_run=False), "/x", SYSTEMS[0])
        self.assertEqual(self.games(calls, 2), ["img-gba/Old.zip", None])

    def test_surprise_replace_list_previews_each_surprise_key(self):
        calls = []
        entry = {"surprises": [{"system": "gba", "bucket": "gba/A.zip"}, {"system": "psx", "bucket": "psx/B.bin"}]}
        with mock.patch.object(surprise.store, "load_cards", return_value={"c": entry}), \
                mock.patch.object(surprise, "enabled", return_value=True), \
                mock.patch.object(surprise, "excluded_systems", return_value=set()), \
                mock.patch.object(picker, "filter_list", self.stop_after(calls)):
            with self.assertRaises(KeyboardInterrupt):
                surprise.run_surprise("c", (None, "esde"), SYSTEMS, True, False)
        self.assertEqual(self.games(calls, 3), ["img-gba/A.zip", "img-psx/B.bin", None])


if __name__ == "__main__":
    unittest.main()
