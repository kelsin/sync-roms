import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import edit, picker, runtime, s3, store, ui  # noqa: E402

SETS = {"s": {"id": "s", "name": "Mix", "games": [{"system": "gba", "bucket": "gba/A.zip", "files": ["gba/A2.zip"]}]}}


class DataDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.object(store, "data_dir", lambda: self.tmp.name)
        patch.start()
        self.addCleanup(patch.stop)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def read(self, name):
        with open(self.path(name)) as f:
            return json.load(f)


class Helpers(unittest.TestCase):
    def test_valid_card_name(self):
        for bad in ("", "  ", "a/b"):
            self.assertIsNotNone(edit.valid_card_name(bad, set()))
        self.assertIsNotNone(edit.valid_card_name("RG SP", {"RG SP"}))
        self.assertIsNone(edit.valid_card_name("RG SP", {"other"}))

    def test_dump_list_shapes(self):
        systems = [{"bucket": "gba", "full_system": True, "games": [{"bucket": "gba/A.zip"}]},
                   {"bucket": "ps2", "full_system": False, "games": [{"bucket": "ps2/B.iso"}]},
                   {"bucket": "nes", "full_system": False, "games": []}]
        self.assertEqual(store.dump_list(systems, ["s"]),
                         {"gba": {"full_system": True}, "ps2": [{"bucket": "ps2/B.iso"}], "sets": ["s"]})
        self.assertEqual(store.dump_list(systems[2:], []), {})

    def test_cover_notes(self):
        core = {"nes": {"full_system": True}, "gba": [{"bucket": "gba/C.zip"}], "sets": ["s"]}
        full, keys = edit.cover_notes(SETS, ["s", "missing"], core)
        self.assertEqual(full, {"nes": "From core: full system"})
        self.assertEqual(keys["gba/C.zip"], "From core")
        self.assertEqual(keys["gba/A2.zip"], "From core: Mix")
        full, keys = edit.cover_notes(SETS, ["s"])
        self.assertEqual((full, keys["gba/A.zip"]), ({}, "Full set: Mix"))


class Saving(DataDir):
    def test_save_lists_writes_core_and_card(self):
        store.update_card("c", device="x", layout="esde")
        store.save_lists({"gba": [{"bucket": "gba/A.zip"}]}, {"c": {"sets": ["s"]}})
        with open(self.path("games.json")) as f:
            text = f.read()
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(json.loads(text), {"gba": [{"bucket": "gba/A.zip"}]})
        self.assertEqual(self.read("cards.json")["c"], {"device": "x", "layout": "esde", "games": {"sets": ["s"]}})

    def test_save_lists_without_core_leaves_games_json(self):
        store.save_lists(None, {"c": {}})
        self.assertFalse(os.path.exists(self.path("games.json")))


class EscPrompt(unittest.TestCase):
    def test_curses_error_at_the_keep_or_revert_prompt_keeps_editing(self):
        import curses

        class Screen:
            def __init__(self, keys):
                self.keys = iter(keys)

            def getmaxyx(self):
                return 24, 80

            def get_wch(self):
                k = next(self.keys)
                if isinstance(k, Exception):
                    raise k
                return k

            def __getattr__(self, name):
                return lambda *a, **k: None
        screen = Screen(["\t", "\x1b", curses.error("no input"), "\n"])
        with mock.patch.object(picker.ui, "require_terminal", create=True), \
                mock.patch.object(curses, "curs_set"), mock.patch.object(curses, "use_default_colors"), \
                mock.patch.object(curses, "has_colors", return_value=False), \
                mock.patch.object(curses, "wrapper", side_effect=lambda f: f(screen)):
            self.assertEqual(picker.filter_list("t", ["a", "b"], multi=True), [True, False])


class EditFlow(DataDir):
    def run_edit(self, picks, confirmed, name="newcard"):
        picks = iter(picks)
        with mock.patch.object(runtime, "BUCKET", "b", create=True), \
                mock.patch.object(s3, "list_sizes", return_value={}), \
                mock.patch.object(picker, "filter_list", side_effect=lambda *a, **k: next(picks)), \
                mock.patch("builtins.input", return_value=name), \
                mock.patch.object(picker, "choose_setup", return_value=(None, "esde")), \
                mock.patch.object(ui, "confirm", return_value=confirmed), \
                mock.patch.object(ui, "choose", side_effect=lambda *a, **k: "s" if confirmed else "d"), \
                mock.patch.object(edit, "note"), \
                contextlib.redirect_stdout(io.StringIO()):
            return edit.edit_manifest()

    def test_cancel_writes_nothing(self):
        # main menu: "New card" is the last option; inside the card menu Esc; then Esc to finish
        self.assertEqual(self.run_edit([1, None, None], confirmed=False), 0)
        self.assertFalse(os.path.exists(self.path("cards.json")))

    def test_new_card_saved_with_setup(self):
        self.assertEqual(self.run_edit([1, None, None], confirmed=True), 0)
        self.assertEqual(self.read("cards.json")["newcard"], {"device": "full", "layout": "esde", "games": {}})
        self.assertEqual(self.read("games.json"), {})

    def test_no_changes_nothing_saved(self):
        self.assertEqual(self.run_edit([0, None, None], confirmed=True), 0)
        self.assertFalse(os.path.exists(self.path("cards.json")))


class MenuActions(EditFlow):
    def write_json(self, name, data):
        with open(self.path(name), "w") as f:
            json.dump(data, f)

    def run_menu(self, picks, confirm=True, inputs=("renamed",), multi=None):
        picks, inputs = iter(picks), iter(inputs)

        def fake(*a, **k):
            if k.get("multi") and multi:
                return multi(k["initial"], a[1])
            return next(picks)
        with mock.patch.object(runtime, "BUCKET", "b", create=True), \
                mock.patch.object(s3, "list_sizes", return_value={}), \
                mock.patch.object(picker, "filter_list", side_effect=fake), \
                mock.patch("builtins.input", side_effect=lambda *a: next(inputs)), \
                mock.patch.object(ui, "confirm", return_value=confirm), \
                mock.patch.object(ui, "choose", side_effect=lambda *a, **k: "s"), \
                mock.patch.object(edit, "note"), \
                contextlib.redirect_stdout(io.StringIO()):
            return edit.edit_manifest()

    def test_rename_a_saved_card(self):
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        self.run_menu([(edit.RENAME_KEY, 1), 4])
        self.assertEqual(list(self.read("cards.json")), ["renamed"])

    def test_delete_a_saved_card(self):
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        self.run_menu([(edit.DELETE_KEY, 1), 4])
        self.assertEqual(self.read("cards.json"), {})

    def test_declined_delete_keeps_the_card(self):
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        self.run_menu([(edit.DELETE_KEY, 1), 4], confirm=False)
        self.assertIn("c", self.read("cards.json"))

    def test_done_with_no_changes_saves_nothing(self):
        self.assertEqual(self.run_menu([3]), 0)
        self.assertFalse(os.path.exists(self.path("cards.json")))

    def device_case(self):
        dev = store.load_manifest()["devices"][0]
        base = store.repo_json("device-systems")[dev["id"]]["systems"]
        names = {s["bucket"]: s["name"] for s in store.load_manifest()["systems"]}
        ids = sorted(names, key=lambda x: names[x].lower())
        return dev, base, ids

    def test_returning_to_the_defaults_drops_the_overlay_entry(self):
        dev, base, ids = self.device_case()
        extra = next(x for x in ids if x not in base)
        self.write_json("device-systems.json", {dev["id"]: {"add": [extra]}})
        self.run_menu([2, 0, None, 3], multi=lambda initial, labels: [x in base for x in ids])
        self.assertEqual(self.read("device-systems.json"), {})

    def test_opening_a_device_and_changing_nothing_is_not_an_edit(self):
        dev, base, ids = self.device_case()
        extra = next(x for x in ids if x not in base)
        self.write_json("device-systems.json", {dev["id"]: {"add": [extra]}})
        self.run_menu([2, 0, None, 3], multi=lambda initial, labels: list(initial))
        self.assertEqual(self.read("device-systems.json"), {dev["id"]: {"add": [extra]}})
        self.assertFalse(os.path.exists(self.path("device-systems.json.bak")))

    def test_unwritable_cards_json_refuses_to_edit(self):
        with open(self.path("cards.json"), "w") as f:
            f.write("{oops")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            self.run_menu([3])
        self.assertNotEqual(cm.exception.code, 0)


class FullToggles(EditFlow):
    def run_with(self, picks, bucket_files=None, confirmed=True):
        picks, calls = iter(picks), []

        def fake(*a, **k):
            calls.append(k)
            return next(picks)
        files = bucket_files or {}
        with mock.patch.object(runtime, "BUCKET", "b", create=True), \
                mock.patch.object(s3, "list_sizes", side_effect=lambda prefix: files.get(prefix, {})), \
                mock.patch.object(picker, "filter_list", side_effect=fake), \
                mock.patch.object(ui, "confirm", return_value=confirmed), \
                mock.patch.object(ui, "choose", side_effect=lambda *a, **k: "s" if confirmed else "d"), \
                mock.patch.object(edit, "note"), \
                contextlib.redirect_stdout(io.StringIO()):
            edit.edit_manifest()
        return calls

    def test_toggle_set_ref(self):
        self.assertEqual(edit.toggle_set_ref(["a"], "b"), ["a", "b"])
        self.assertEqual(edit.toggle_set_ref(["a", "b"], "a"), ["b"])

    def test_toggle_full_system_keeps_games(self):
        s = {"full_system": False, "games": [{"bucket": "gba/A.zip"}]}
        edit.toggle_full_system(s)
        self.assertTrue(s["full_system"])
        self.assertEqual(len(s["games"]), 1)

    def test_set_menu_hotkey_toggles_and_redraws(self):
        first = store.load_sets()[1]["id"]
        calls = self.run_with([0, 1, (edit.FULL_KEY, 1), None, None, None])
        self.assertEqual(self.read("games.json"), {"sets": [first]})
        self.assertEqual(calls[3]["cursor"], 1)
        self.assertEqual(calls[3]["extras"][1], [("  📦 full set", "green")])
        self.assertIn(edit.FULL_KEY, calls[2]["hotkeys"])

    def test_system_hotkey_toggles_full_system(self):
        self.run_with([0, 0, (edit.FULL_KEY, 0), None, None, None], {"gba/": {"gba/A.zip": 1}})
        self.assertEqual(self.read("games.json"), {"gba": {"full_system": True}})

    def test_core_full_system_blocks_card_toggle(self):
        self.write_json("games.json", {"gba": {"full_system": True}})
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        self.run_with([1, 0, (edit.FULL_KEY, 0), None, None, None], {"gba/": {"gba/A.zip": 1}})
        self.assertNotIn("games", self.read("cards.json")["c"])

    def test_set_ref_rows_locked(self):
        self.write_json("games.json", {"sets": ["mario"]})
        tracked = []
        with mock.patch.object(edit, "toggle_games",
                               side_effect=lambda *a, **k: tracked.append((a, k))):
            ids = [x["id"] for x in store.load_sets()]
            self.run_with([0, 1, ids.index("mario"), None, None, None])
        rows = tracked[0][0][1]
        note = tracked[0][1]["covered"](rows[0][0], rows[0][1])
        self.assertEqual(note, "Full set: Mario")

    def test_card_named_core_leaves_core_list_alone(self):
        self.write_json("games.json", {"gba": [{"title": "A", "bucket": "gba/A.zip"}]})
        self.write_json("cards.json", {"core": {"layout": "esde", "device": "full"}})
        self.run_with([1, 1, (edit.FULL_KEY, 0), None, None, None], confirmed=True)
        self.assertEqual(self.read("games.json"), {"gba": [{"title": "A", "bucket": "gba/A.zip"}]})

    def test_by_set_locks_systems_full_in_core(self):
        self.write_json("games.json", {"nes": {"full_system": True}})
        self.write_json("cards.json", {"c": {"layout": "esde", "device": "full"}})
        tracked = []
        nes_set = next(x["id"] for x in store.load_sets() if any(g["system"] == "nes" for g in x["games"]))
        ids = [x["id"] for x in store.load_sets()]
        with mock.patch.object(edit, "toggle_games", side_effect=lambda *a, **k: tracked.append((a, k))):
            self.run_with([1, 1, ids.index(nes_set), None, None, None])
        rows, covered = tracked[0][0][1], tracked[0][1]["covered"]
        nes_row = next(r for r in rows if r[0]["bucket"] == "nes")
        self.assertTrue(covered(nes_row[0], nes_row[1]))

    def device_and_unsupported(self):
        """A device and a system bucket id (with a esde folder) it doesn't run."""
        systems = store.repo_json("systems")
        for d in store.load_manifest()["devices"]:
            if "esde" in d["firmwares"]:
                other = next((x["bucket"] for x in systems if x["bucket"] not in d["systems"] and x["folders"].get("esde")), None)
                if other:
                    return d, other
        self.fail("no device with an unsupported system")

    def test_opening_a_card_drops_games_of_unsupported_systems(self):
        device, other = self.device_and_unsupported()
        self.write_json("cards.json", {"c": {"layout": "esde", "device": device["id"],
                                             "games": {other: [{"title": "X", "bucket": f"{other}/X.zip"}]}}})
        self.run_with([1, None, None])
        self.assertEqual(self.read("cards.json")["c"]["games"], {})

    def test_set_counts_only_count_supported_systems(self):
        device, other = self.device_and_unsupported()
        self.write_json("cards.json", {"c": {"layout": "esde", "device": device["id"]}})
        game_set = {"id": "t", "name": "T", "description": "", "games": [
            {"system": other, "bucket": f"{other}/X.zip"}, {"system": device["systems"][0], "bucket": "a/Y.zip"}]}
        labels = []
        picks = iter([1, 1, None, None, None])

        def fake(title, items, **k):
            labels.append(items)
            return next(picks)
        with mock.patch.object(store, "load_sets", return_value=[game_set]), \
                mock.patch.object(picker, "filter_list", side_effect=fake), \
                mock.patch.object(s3, "list_sizes", return_value={}), \
                mock.patch.object(runtime, "BUCKET", "b", create=True), \
                contextlib.redirect_stdout(io.StringIO()):
            edit.edit_manifest()
        self.assertIn("(0/1 on)", labels[2][0])

    def write_json(self, name, data):
        with open(self.path(name), "w") as f:
            json.dump(data, f)


if __name__ == "__main__":
    unittest.main()
