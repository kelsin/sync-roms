import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import DataDir  # noqa: E402
from sync_roms import budget, cardedit, collections, edit, inventory, picker, s3, store, surprise, ui  # noqa: E402

U = budget.Usage


def system(bucket, name, bios=(), company="Nintendo"):
    return {"bucket": bucket, "name": name, "company": company, "folders": {"esde": bucket}, "bios": {"files": list(bios)}}


GBA, GB, PSX = system("gba", "Game Boy Advance", ["gba_bios.bin"]), system("gb", "Game Boy", ["gb_bios.bin"]), system("psx", "PlayStation", company="Sony")
DEVICE = {"id": "d", "name": "D", "firmwares": ["esde"], "systems": ["gba", "gb"]}
CATALOG = {"systems": [GBA, GB, PSX], "devices": [DEVICE],
           "layouts": {"esde": {"label": "ES-DE", "roms_dir": "ROMs", "bios_dir": "BIOS"}}}
SET = {"id": "pk", "name": "Pokemon", "description": "", "games": [
    {"system": "gba", "bucket": "gba/Ruby.zip", "files": ["gba/Ruby.sav"]}, {"system": "gb", "bucket": "gb/Red.gb"}]}


def g(key):
    return {"title": store.key_title(key), "bucket": key}


class Pure(unittest.TestCase):
    def test_size_text_is_decimal(self):
        self.assertEqual(cardedit.size_text(512 * 10 ** 9), "512 GB")
        self.assertEqual(cardedit.size_text(1_500_000_000), "1.5 GB")
        self.assertEqual(cardedit.size_text(999), "999 B")
        self.assertEqual(cardedit.size_text(2 * 10 ** 12), "2 TB")

    def test_header(self):
        self.assertEqual(cardedit.header(U(1_500_000_000, 3, False), 512 * 10 ** 9),
                         ("💾 1.5 GB / 512 GB · 510.5 GB free · 3 file(s)", False))
        text, over = cardedit.header(U(600 * 10 ** 9, 9, False), 512 * 10 ** 9)
        self.assertTrue(over)
        self.assertIn("88 GB over", text)
        self.assertEqual(cardedit.header(U(10 ** 9, 1, False), None), ("💾 1 GB used · 1 file(s)", False))
        text, over = cardedit.header(U(10 ** 9, 1, True), None)
        self.assertTrue(text.endswith("not sized (sync-roms cache update)"))
        self.assertFalse(over)
        self.assertEqual(cardedit.header(U(10 ** 9, 1, False), None, 0)[0], "💾 1 GB used · 1 file(s) · ⬇️  0 B to download")

    def test_silent_thread_hides_warn_and_fail_output(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), ui.silent_thread():
            ui.warn("quiet")
            with self.assertRaises(SystemExit):
                ui.fail("quiet")
        self.assertEqual(err.getvalue(), "")
        with contextlib.redirect_stderr(err):
            ui.warn("loud")
        self.assertIn("loud", err.getvalue())

    def test_status_color_follows_how_full_the_card_is(self):
        self.assertEqual(cardedit.status_of(U(2, 0, False), 1)[1], "red")
        self.assertEqual(cardedit.status_of(U(69, 0, False), 100)[1], "green")
        self.assertEqual(cardedit.status_of(U(70, 0, False), 100)[1], "yellow")
        self.assertEqual(cardedit.status_of(U(89, 0, False), 100)[1], "yellow")
        self.assertEqual(cardedit.status_of(U(90, 0, False), 100)[1], "red")
        self.assertIsInstance(cardedit.status_of(U(1, 0, False), None), str)

    def test_system_labels(self):
        card = {"games": {"psx": {"full_system": True}}}
        usages = {"gba": U(2 * 10 ** 9, 4, False), "gb": U(0, 0, False), "psx": U(0, 0, True)}
        labels, extras = cardedit.system_labels(card, [GBA, GB, PSX], {"gb"}, usages)
        self.assertEqual([l.strip() for l in labels], ["Game Boy Advance", "⭐ Game Boy", "PlayStation"])  # the given order
        self.assertTrue(labels[1].startswith("⭐ "))
        self.assertEqual(extras[0], [("  4 picked", "green"), ("  2 GB", "dim")])
        self.assertEqual(extras[1], [])
        self.assertEqual(extras[2], [("  🗂️  full system", "cyan"), ("  … picked", "green"), ("  …", "dim")])

    def test_set_filter_is_one_system(self):
        self.assertEqual(cardedit.set_filter(SET, GBA), {"gba/Ruby.zip", "gba/Ruby.sav"})
        self.assertEqual(cardedit.set_filter(SET, GB), {"gb/Red.gb"})
        self.assertEqual(cardedit.set_filter(SET, PSX), set())


class Script:
    """A fake picker.filter_list: each call runs the next step(labels, kwargs) for its return value."""

    def __init__(self, *steps):
        self.steps, self.calls = iter(steps), []

    def __call__(self, title, labels, **kw):
        self.calls.append((title, list(labels), kw))
        while True:
            result = next(self.steps)(labels, kw)
            handled = isinstance(result, tuple) and kw.get("on_hotkey") and kw["on_hotkey"](*result)
            if not handled:  # a hotkey handled in place leaves the list open for the next step
                return result


def returns(value):
    return lambda labels, kw: value


def toggle(*names):
    """A multi-mode step that switches the rows labelled names and presses Enter."""
    def step(labels, kw):
        state = list(kw["session"]["sel"])
        for n in names:
            state[labels.index(n)] = not state[labels.index(n)]
        return state
    return step


def flip(i):
    """A multi-mode step that switches row i of the initial states and presses Enter."""
    def step(labels, kw):
        state = list(kw["initial"])
        state[i] = not state[i]
        return state
    return step


class Flow(DataDir):
    def setUp(self):
        super().setUp()
        self.files = {"gba/": {"gba/Emerald.zip": 3, "gba/Ruby.zip": 5, "gba/Ruby.sav": 1, "gba/Zelda.zip": 7},
                      "gb/": {"gb/Red.gb": 2}}
        self.cache = {}
        self.folders = {"gba", "gb", "psx"}
        for target, attrs in ((store, {"load_catalog": lambda: CATALOG, "load_sets": lambda: [SET],
                                       "repo_json": lambda name: CATALOG[name],
                                       "recommended_systems": lambda device, systems: set()}),
                              (s3, {"list_sizes": lambda prefix, sizes=True: self.files.get(prefix, {}),
                                    "list_folders": lambda: self.folders}),
                              (inventory, {"cached": lambda p: self.cache.get(p)}),
                              (edit, {"note": lambda text: None}),
                              (cardedit, {"_spawn": lambda fn: None, "_metadata": {}})):  # no metadata read
            for name, new in attrs.items():
                p = mock.patch.object(target, name, new)
                p.start()
                self.addCleanup(p.stop)

    def card(self, **entry):
        self.write_json("cards.json", {"c": {"device": "d", "layout": "esde", **entry}})

    def test_u_toggles_surprise_and_the_title_shows_it(self):
        self.card(size="1 GB")
        calls = self.run_card(returns((cardedit.SURPRISE_KEY, 0)), returns(0), returns((cardedit.SURPRISE_KEY, 0)),
                              returns(0), returns(None))
        self.assertIn("🎁 Surprise on", calls[0][0])
        self.assertEqual(calls[1][1][0], "Turn Surprise off for c")
        self.assertIn("🎁 Surprise off", calls[2][0])
        self.assertEqual(calls[3][1][0], "Turn Surprise on for c")
        self.assertIn("🎁 Surprise on", calls[4][0])
        self.assertNotIn("surprise", self.read("cards.json")["c"])

    def test_u_off_saves_false(self):
        self.card(size="1 GB")
        self.run_card(returns((cardedit.SURPRISE_KEY, 0)), returns(0), returns(None))
        self.assertIs(self.read("cards.json")["c"]["surprise"], False)

    def test_u_esc_changes_nothing(self):
        self.card(size="1 GB")
        self.run_card(returns((cardedit.SURPRISE_KEY, 0)), returns(None), returns(None))
        self.assertNotIn("surprise", self.read("cards.json")["c"])
        self.assertIsNone(self.read_settings().get("surprise_excluded_systems"))

    def test_u_systems_saves_the_unchecked_ones_for_every_card(self):
        self.card(size="1 GB")
        self.write_json("settings.json", {"surprise_excluded_systems": ["gone"], "bucket": "b"})
        names = [s["name"] for s in CATALOG["systems"]]
        calls = self.run_card(returns((cardedit.SURPRISE_KEY, 0)), returns(1), flip(0), returns(None))
        self.assertTrue(calls[2][1] and all(calls[2][1][i] == names[i] for i in range(len(names))))
        self.assertEqual(self.read_settings()["surprise_excluded_systems"], sorted(["gone", CATALOG["systems"][0]["bucket"]]))
        self.assertEqual(self.read_settings()["bucket"], "b")
        self.assertNotIn("surprise", self.read("cards.json")["c"])

    def test_u_systems_all_checked_removes_the_setting(self):
        self.card(size="1 GB")
        first = CATALOG["systems"][0]
        self.write_json("settings.json", {"surprise_excluded_systems": [first["bucket"]]})
        self.run_card(returns((cardedit.SURPRISE_KEY, 0)), returns(1), flip(0), returns(None))
        self.assertNotIn("surprise_excluded_systems", self.read_settings())

    def read_settings(self):
        try:
            return self.read("settings.json")
        except FileNotFoundError:
            return {}

    def test_u_off_clears_the_current_surprises(self):
        self.card(surprises=[{"system": "gba", "bucket": "gba/Zelda.zip", "title": "Zelda"}])
        self.assertFalse(cardedit.toggle_surprise("c"))
        self.assertNotIn("surprises", self.read("cards.json")["c"])

    def test_a_text_collections_field_is_not_split_into_letters(self):
        self.favs()
        self.card(collections="favs")
        self.run_card(returns((cardedit.COLLECTIONS_KEY, 0)), returns((" ", 0)), returns(None), returns(None))
        self.assertEqual(self.read("cards.json")["c"]["collections"], ["favs"])

    def test_p_narrows_the_game_list_to_past_surprises(self):
        self.card()
        with mock.patch.object(surprise, "past_keys", return_value={"gba/Ruby.zip"}):
            _, calls = self.run_system(returns((cardedit.PAST_SURPRISE_KEY, 0)), returns((cardedit.CLEAR_KEY, 0)),
                                       lambda labels, kw: [False] * len(labels))
        self.assertEqual(calls[1][1], ["Ruby.zip"])
        self.assertIn("🎁 past surprises only (c shows all)", calls[1][0])
        self.assertEqual(len(calls[2][1]), len(calls[0][1]))

    def test_p_with_no_past_surprises_says_so_and_keeps_the_list(self):
        self.card()
        with mock.patch.object(surprise, "past_keys", return_value=set()), \
                mock.patch.object(edit, "note") as note:
            _, calls = self.run_system(returns((cardedit.PAST_SURPRISE_KEY, 0)), lambda labels, kw: [False] * len(labels))
        self.assertIn("No past surprises on Game Boy Advance", note.call_args[0][0])
        self.assertEqual(len(calls[1][1]), len(calls[0][1]))

    def test_surprise_rows_are_locked_in_the_game_list(self):
        self.card(surprises=[{"system": "gba", "bucket": "gba/Zelda.zip", "title": "Zelda"}])
        _, calls = self.run_system(lambda labels, kw: list(kw["initial"]))
        labels, kw = calls[0][1], calls[0][2]
        i = labels.index("Zelda.zip")
        self.assertTrue(kw["locked"][i])
        self.assertIn("🎁 Surprise", str(kw["extras"][i]) + str(kw.get("locked_note")))

    def test_system_list_offers_no_make_set_key(self):
        self.card(games={"gba": [g("gba/Ruby.zip")]})
        kw = self.run_card(returns(None))[0][2]
        self.assertNotIn("m", kw["hotkeys"])
        self.assertNotIn("make set", kw["hint"])
        self.assertFalse(hasattr(cardedit, "MAKE_SET_KEY"))

    def favs(self, *more):
        collections.save_collection({"id": "favs", "name": "Favs", "games": [
            {"title": "Ruby", "system": "gba", "bucket": "gba/Ruby.zip"}, {"title": "Red", "system": "gb", "bucket": "gb/Red.gb"},
            {"title": "FF7", "system": "psx", "bucket": "psx/FF7.chd"}, *more]})

    def test_collections_hotkey_shows_playable_counts_and_space_toggles(self):
        self.favs({"title": "Pokemon", "system": "nds", "bucket": "nds/Pokemon.nds"})
        self.card()
        nds = {**system("nds", "Nintendo DS"), "folders": {}}  # the device runs it, but esde has no folder for it
        with mock.patch.dict(CATALOG, systems=CATALOG["systems"] + [nds]), \
                mock.patch.dict(DEVICE, systems=["gba", "gb", "nds"]):
            calls = self.run_card(returns((cardedit.COLLECTIONS_KEY, 0)), returns((" ", 0)), returns(None), returns(None))
        self.assertEqual(calls[1][1], ["Favs  (2 playable, 2 not playable)"])
        self.assertEqual(calls[1][2]["extras"], [[("  ✅ on the card", "green")]])
        self.assertEqual(self.read("cards.json")["c"]["collections"], ["favs"])

    def test_collections_hotkey_skips_malformed_games(self):
        self.favs("gba/Loose.zip", None, {"system": "gba"})
        self.card()
        with contextlib.redirect_stderr(io.StringIO()):
            calls = self.run_card(returns((cardedit.COLLECTIONS_KEY, 0)), returns(None), returns(None))
        self.assertEqual(calls[1][1], ["Favs  (2 playable, 1 not playable)"])

    def test_enter_toggles_a_collection_off_again(self):
        self.favs()
        self.card(collections=["favs"])
        self.run_card(returns((cardedit.COLLECTIONS_KEY, 0)), returns(0), returns(None), returns(None))
        self.assertEqual(self.read("cards.json")["c"]["collections"], [])

    def test_no_collections_is_a_note(self):
        self.card()
        with mock.patch.object(edit, "note") as note:
            calls = self.run_card(returns((cardedit.COLLECTIONS_KEY, 0)), returns(None))
        self.assertEqual(len(calls), 2)  # the system list twice, no collection list
        self.assertIn("sync-roms collections edit", note.call_args[0][0])

    def test_collection_games_are_on_locked_and_marked_even_when_excluded(self):
        self.favs()
        self.card(collections=["favs"], excluded={"gba": ["gba/Ruby.zip"]})
        changed, calls = self.run_system(toggle())
        _, labels, kw = calls[0]
        i = labels.index("Ruby.zip")
        self.assertTrue(kw["initial"][i])
        self.assertEqual([n for n, on in enumerate(kw["locked"]) if on], [i])
        self.assertEqual(kw["locked_note"][i], "From 💖 Favs; take it off the card to remove this game")
        self.assertIn(("  💖 Favs", "cyan"), kw["extras"][i])
        self.assertFalse(changed)

    def test_collection_games_count_in_the_game_view_and_system_list(self):
        self.favs()
        self.card(size="1 GB", collections=["favs"])
        self.cache = {"gba/": self.files["gba/"], "gb/": self.files["gb/"], "scrapes/gba/": {}, "scrapes/gb/": {}, "BIOS/": {}}
        _, calls = self.run_system(toggle())
        kw = calls[0][2]
        self.assertIn("· 2 file(s)", kw["status"](kw["initial"])[0])  # Ruby here, Red on Game Boy
        extras = self.run_card(returns(None))[0][2]["extras"]
        self.assertIn(("  1 picked", "green"), extras[0])

    def run_card(self, *steps):
        script = Script(*steps)
        with mock.patch.object(picker, "filter_list", script), contextlib.redirect_stdout(io.StringIO()):
            cardedit.edit_card("c")
        return script.calls

    def run_system(self, *steps, bucket="gba"):
        script = Script(*steps)
        with mock.patch.object(picker, "filter_list", script), contextlib.redirect_stdout(io.StringIO()):
            changed = edit.edit_card_system("c", bucket, (DEVICE, "esde"))
        return changed, script.calls

    def test_system_list_hides_systems_cached_as_empty_unless_picked(self):
        self.card(size="1 GB")
        self.cache = {"gb/": {}, "gba/": self.files["gba/"], "scrapes/gba/": {}, "BIOS/": {}}
        self.assertEqual([l.strip() for l in self.run_card(returns(None))[0][1]], ["Game Boy Advance"])
        self.card(size="1 GB", games={"gb": [g("gb/Red.gb")]})
        self.assertEqual([l.strip() for l in self.run_card(returns(None))[0][1]], ["Game Boy", "Game Boy Advance"])

    def test_system_list_hides_systems_with_no_storage_folder_unless_picked(self):
        self.card(size="1 GB")
        self.folders = {"gba"}  # gb was never opened, so nothing is cached for it
        self.assertEqual([l.strip() for l in self.run_card(returns(None))[0][1]], ["Game Boy Advance"])
        self.card(size="1 GB", games={"gb": [g("gb/Red.gb")]})
        self.assertEqual([l.strip() for l in self.run_card(returns(None))[0][1]], ["Game Boy", "Game Boy Advance"])

    def test_system_list_shows_every_system_when_storage_cannot_be_listed(self):
        self.card(size="1 GB")
        for error in (OSError("unreachable"), SystemExit(3)):
            with mock.patch.object(s3, "list_folders", side_effect=error):
                labels = self.run_card(returns(None))[0][1]
            self.assertEqual([l.strip() for l in labels], ["Game Boy", "Game Boy Advance"])

    def test_system_list_is_what_the_device_plays_sorted_by_company_and_name(self):
        self.card(size="1 GB", games={"gba": [g("gba/Ruby.zip")]})
        self.cache = {"gba/": self.files["gba/"], "scrapes/gba/": {}, "BIOS/": {"BIOS/gba_bios.bin": 16}}
        with mock.patch.object(store, "recommended_systems", return_value={"gb"}):
            calls = self.run_card(returns(None))
        title, labels, kw = calls[0]
        self.assertEqual([l.strip() for l in labels], ["⭐ Game Boy", "Game Boy Advance"])
        self.assertEqual(kw["extras"][1], [("  1 picked", "green"), ("  5 B", "dim")])  # the ROM
        self.assertEqual(kw["status"](None), ("💾 21 B / 1 GB · 1 GB free · 1 file(s)", "green"))  # ROM and the GBA BIOS

    def test_full_system_hotkey_saves_and_restores_the_list(self):
        self.card(games={"gba": [g("gba/Ruby.zip")]})
        seen = []

        def look(labels, kw):
            seen.append(store.card_games("c"))
            return (cardedit.FULL_KEY, 1)
        self.run_card(returns((cardedit.FULL_KEY, 1)), look, returns(None))
        self.assertEqual(seen[0], {"gba": {"full_system": True, "games": [g("gba/Ruby.zip")]}})
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Ruby.zip")]})

    def test_clear_all_hotkey_empties_the_card_after_confirming(self):
        entry = {"games": {"gba": [g("gba/Ruby.zip")], "gb": {"full_system": True}, "sets": ["pk"]},
                 "excluded": {"gba": ["gba/Ruby.zip"]}}
        for answer, want in ((False, entry["games"]), (True, {})):
            self.card(**entry)
            with mock.patch.object(ui, "confirm", return_value=answer):
                self.run_card(returns((cardedit.CLEAR_ALL_KEY, 0)), returns(None))
            self.assertEqual(store.card_games("c"), want)
            self.assertEqual(store.card_excluded("c"), entry["excluded"] if not answer else {})

    def test_full_system_keeps_the_list_for_a_later_session(self):
        self.card(games={"gba": [g("gba/Ruby.zip")]})
        self.run_card(returns((cardedit.FULL_KEY, 1)), returns(None))  # full system on, editor closed
        self.run_card(returns((cardedit.FULL_KEY, 1)), returns(None))  # a new session switches it off
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Ruby.zip")]})
        self.card(games={"gba": {"full_system": True}})  # no list was replaced: off removes the system
        self.run_card(returns((cardedit.FULL_KEY, 1)), returns(None))
        self.assertEqual(store.card_games("c"), {})

    def test_header_says_not_sized_without_a_cache(self):
        self.card(games={"gba": [g("gba/Ruby.zip")]})

        def step(labels, kw):
            self.assertIn("not sized (sync-roms cache update)", kw["status"](None))
            return None
        self.run_card(step)

    def test_toggle_a_game_saves_it(self):
        self.card(games={"gba": [g("gba/Ruby.zip")]})
        changed, calls = self.run_system(toggle("Zelda.zip", "Ruby.zip"))
        self.assertTrue(changed)
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Zelda.zip")]})
        _, labels, kw = calls[0]
        self.assertEqual(labels, ["Emerald.zip", "Ruby.sav", "Ruby.zip", "Zelda.zip"])
        self.assertEqual(kw["initial"], [False, False, True, False])

    def test_nothing_toggled_saves_nothing(self):
        self.card(games={"gba": [g("gba/Ruby.zip")]})
        before = self.read("cards.json")
        changed, _ = self.run_system(returns([False, False, True, False]))
        self.assertFalse(changed)
        self.assertEqual(self.read("cards.json"), before)
        self.assertFalse(os.path.exists(self.path("cards.json.bak")))

    def test_set_games_are_marked_and_switching_one_off_excludes_it(self):
        self.card(games={"sets": ["pk"]})
        changed, calls = self.run_system(toggle("Ruby.zip"))
        _, labels, kw = calls[0]
        self.assertEqual(kw["initial"], [False, True, True, False])
        self.assertEqual(kw["extras"][labels.index("Ruby.zip")][0], ("  📦 Pokemon", "cyan"))
        self.assertTrue(changed)
        entry = self.read("cards.json")["c"]
        self.assertEqual(entry["excluded"], {"gba": ["gba/Ruby.zip"]})
        self.assertEqual(entry["games"], {"sets": ["pk"]})

    def test_set_filter_narrows_to_that_set_on_this_system_and_clears(self):
        self.card()

        def pick_first_set(labels, kw):
            self.assertEqual(labels, ["Pokemon  (2 on Game Boy Advance)"])
            return 0

        def filtered(labels, kw):
            self.assertEqual(labels, ["Ruby.sav", "Ruby.zip"])
            state = list(kw["session"]["sel"])
            state[1] = True  # pick Ruby.zip, then clear the filter
            kw["session"]["sel"] = state
            return (cardedit.CLEAR_KEY, 1)

        def everything(labels, kw):
            self.assertEqual(labels, ["Emerald.zip", "Ruby.sav", "Ruby.zip", "Zelda.zip"])
            self.assertEqual(kw["session"]["sel"], [False, False, True, False])  # kept across the filter
            return kw["session"]["sel"]
        _, calls = self.run_system(returns((cardedit.SET_KEY, 0)), pick_first_set, filtered, everything)
        self.assertIn("Pokemon only", calls[2][0])
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Ruby.zip")]})

    def test_set_list_counts_what_is_in_storage(self):
        self.card()
        self.files["gba/"].pop("gba/Ruby.sav")
        other = {"id": "gone", "name": "Gone", "description": "", "games": [{"system": "gba", "bucket": "gba/X.zip"}]}

        def offered(labels, kw):
            self.assertEqual(labels, ["Pokemon  (1 on Game Boy Advance, 1 not in storage)"])  # Gone: nothing to show
            return None
        with mock.patch.object(store, "load_sets", return_value=[SET, other]):
            self.run_system(returns((cardedit.SET_KEY, 0)), offered, lambda labels, kw: kw["session"]["sel"])
        self.assertNotIn("excluded", self.read("cards.json")["c"])

    def test_set_list_toggle_adds_only_this_systems_games(self):
        self.card()

        def added(labels, kw):
            self.assertEqual(kw["extras"], [[("  ✅", "cyan")]])
            return None
        self.run_system(returns((cardedit.SET_KEY, 0)), returns((" ", 0)), added,
                        lambda labels, kw: kw["session"]["sel"])
        games = store.card_games("c")
        self.assertNotIn("sets", games)
        self.assertEqual({x["bucket"] for x in games["gba"]}, {"gba/Ruby.sav", "gba/Ruby.zip"})

    def test_set_list_toggle_again_removes_them(self):
        self.card()

        def removed(labels, kw):
            self.assertEqual(kw["extras"], [[("  0/2", "cyan")]])
            return None
        self.run_system(returns((cardedit.SET_KEY, 0)), returns((" ", 0)), returns((" ", 0)), removed,
                        lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(store.card_games("c"), {})

    def test_game_view_status_counts_pending_picks(self):
        self.card(size="1 GB")
        self.cache = {"gba/": self.files["gba/"], "scrapes/gba/": {}, "BIOS/": {"BIOS/gba_bios.bin": 16}, "gb/": {}}

        def step(labels, kw):
            self.assertEqual(kw["status"]([False] * 4), ("💾 0 B / 1 GB · 1 GB free · 0 file(s)", "green"))
            self.assertEqual(kw["status"]([True, False, False, True]), ("💾 26 B / 1 GB · 1 GB free · 2 file(s)", "green"))
            return [False] * 4
        self.run_system(step)

    def test_game_view_counts_other_systems_bios_once(self):
        self.card(games={"gb": [g("gb/Red.gb")]})
        self.cache = {"gba/": self.files["gba/"], "gb/": self.files["gb/"], "scrapes/gba/": {}, "scrapes/gb/": {},
                      "BIOS/": {"BIOS/gb_bios.bin": 1000, "BIOS/gba_bios.bin": 16}}
        card = cardedit.card_entry("c", (DEVICE, "esde"))
        self.assertEqual(budget.card_usage(card, [GBA, GB]).bytes, 1002)  # what the system list shows

        seen = []

        def step(labels, kw):
            kw["status"]([False] * 4)
            kw["status"]([True, False, False, False])  # Emerald (3) and the GBA BIOS (16)
            return [False] * 4
        with mock.patch.object(cardedit, "status_of", side_effect=lambda u, c, fetch=None: seen.append(u.bytes)):
            self.run_system(step)
        self.assertEqual(seen, [1002, 1021])

    def test_download_preview_counts_only_roms_not_on_the_card(self):
        self.card(games={"gba": [g("gba/Ruby.zip")], "gb": [g("gb/Red.gb")]})
        self.cache = {"gba/": self.files["gba/"], "gb/": self.files["gb/"], "scrapes/gba/": {}, "scrapes/gb/": {},
                      "BIOS/": {}}
        on_card = {"gba/Ruby.zip"}

        def to_fetch(s, keys):
            return {k for k in keys if k not in on_card}
        statuses = []

        def system_list(labels, kw):
            statuses.append(kw["status"](None))
            return None
        script = Script(system_list)
        with mock.patch.object(picker, "filter_list", script), contextlib.redirect_stdout(io.StringIO()):
            cardedit.edit_card("c", (DEVICE, "esde"), to_fetch)
        self.assertTrue(statuses[0].endswith("⬇️  2 B to download"), statuses)  # Red (2); Ruby is on the card

        def games(labels, kw):
            statuses.append(kw["status"]([True, False, True, False]))  # Emerald (3) too
            return [False] * 4
        script = Script(games)
        with mock.patch.object(picker, "filter_list", script), contextlib.redirect_stdout(io.StringIO()):
            cardedit.edit_system("c", GBA, (DEVICE, "esde"), to_fetch)
        self.assertTrue(statuses[1].endswith("⬇️  5 B to download"), statuses)

    def test_collections_screen_shows_the_card_status_after_each_toggle(self):
        favs = {"id": "favs", "name": "Favs", "games": [{"system": "gba", "bucket": "gba/Zelda.zip", "title": "Zelda"}]}
        self.card()
        self.cache = {"gba/": self.files["gba/"], "gb/": self.files["gb/"], "scrapes/gba/": {}, "scrapes/gb/": {},
                      "BIOS/": {}}
        statuses = []

        def step(labels, kw):
            statuses.append(kw["status"](None))
            return (" ", 0) if len(statuses) == 1 else None
        with mock.patch.object(collections, "load_collections", lambda: [favs]), \
                mock.patch.object(picker, "filter_list", Script(step, step)), contextlib.redirect_stdout(io.StringIO()):
            cardedit.pick_collections("c", {"gba"}, lambda: cardedit.card_status("c", (DEVICE, "esde"), [GBA, GB],
                                                                                 lambda s, keys: set(keys)))
        self.assertIn("0 file(s) · ⬇️  0 B to download", statuses[0])
        self.assertIn("1 file(s) · ⬇️  7 B to download", statuses[1])

    def test_picked_game_not_in_storage_is_not_still_sizing(self):
        self.card(games={"gba": [g("gba/Ruby.zip"), g("gba/Gone.zip")]})
        self.cache = {"gba/": self.files["gba/"], "scrapes/gba/": {}, "BIOS/": {}}

        def step(labels, kw):
            self.assertIn("Gone.zip  ⚠️ not in storage", labels)
            self.assertEqual(kw["status"](kw["session"]["sel"]), "💾 5 B used · 2 file(s)")
            return kw["session"]["sel"]
        self.run_system(step)
        with mock.patch.object(store, "recommended_systems", return_value=set()):
            calls = self.run_card(returns(None))
        self.assertEqual(calls[0][2]["status"](None), "💾 5 B used · 2 file(s)")

    def test_entering_a_system_lists_names_only(self):
        self.card()
        calls = []
        real = s3.list_sizes

        def listing(prefix, sizes=True):
            calls.append((prefix, sizes))
            return real(prefix, sizes)
        with mock.patch.object(s3, "list_sizes", listing):
            self.run_system(returns([False] * 4))
        self.assertEqual(calls, [("gba/", False)])

    def test_ctrl_c_saves_what_was_toggled(self):
        self.card(games={"gba": [g("gba/Ruby.zip")]})

        def filtered_pass(labels, kw):  # Zelda on, then the set list
            kw["session"]["sel"][labels.index("Zelda.zip")] = True
            return (cardedit.SET_KEY, 0)

        def interrupted(labels, kw):  # Ruby off, then Ctrl-C mid-list
            kw["session"]["sel"][labels.index("Ruby.zip")] = False
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.run_system(filtered_pass, returns((" ", 0)), returns(None), interrupted)
        entry = self.read("cards.json")["c"]  # the first pass, the set's games and the interrupted pass
        self.assertEqual({x["bucket"] for x in entry["games"]["gba"]}, {"gba/Zelda.zip", "gba/Ruby.sav"})
        self.assertNotIn("sets", entry["games"])

    def initial_of(self, kw, labels, name):
        return kw["initial"][labels.index(name)]

    def test_switching_on_an_excluded_set_game_drops_the_exclusion_only(self):
        self.card(games={"sets": ["pk"]}, excluded={"gba": ["gba/Ruby.zip"]})
        _, calls = self.run_system(toggle("Ruby.zip"))
        self.assertFalse(self.initial_of(calls[0][2], calls[0][1], "Ruby.zip"))
        entry = self.read("cards.json")["c"]
        self.assertEqual(entry["games"], {"sets": ["pk"]})  # the set syncs it: no direct pick
        self.assertNotIn("gba", entry.get("excluded", {}))

    def test_an_excluded_direct_pick_shows_off_as_sync_skips_it_and_on_clears_it(self):
        self.write_json("cards.json", {"c": {"device": "d", "layout": "esde", "games": {"gba": [g("gba/Ruby.zip")]},
                                             "excluded": {"gba": ["gba/Ruby.zip"]}}})
        _, calls = self.run_system(toggle("Ruby.zip"))
        self.assertFalse(self.initial_of(calls[0][2], calls[0][1], "Ruby.zip"))
        entry = self.read("cards.json")["c"]
        self.assertEqual(entry["games"], {"gba": [g("gba/Ruby.zip")]})  # still one pick
        self.assertNotIn("gba", entry.get("excluded", {}))

    def test_switching_off_a_game_no_set_covers_adds_no_exclusion(self):
        self.card(games={"gba": [g("gba/Zelda.zip")]})
        self.run_system(toggle("Zelda.zip"))
        entry = self.read("cards.json")["c"]
        self.assertEqual(entry["games"], {})
        self.assertNotIn("excluded", entry)

    def test_a_storage_listing_error_is_a_note(self):
        self.card()
        notes = []

        def fail(prefix, sizes=True):
            raise OSError("share is gone")
        with mock.patch.object(s3, "list_sizes", fail), mock.patch.object(edit, "note", notes.append):
            changed, calls = self.run_system()
        self.assertFalse(changed)
        self.assertEqual(calls, [])
        self.assertIn("Couldn't list Game Boy Advance in storage: share is gone", notes[0])

    def test_a_terminal_too_small_still_saves_the_toggles(self):
        import curses
        self.card()

        def first(labels, kw):
            kw["session"]["sel"][labels.index("Zelda.zip")] = True
            return (cardedit.CLEAR_KEY, None)

        def too_small(labels, kw):
            kw["session"]["sel"][labels.index("Emerald.zip")] = True
            raise curses.error("addnstr() returned ERR")
        with self.assertRaises(curses.error):
            self.run_system(first, too_small)
        self.assertEqual(sorted(x["bucket"] for x in store.card_games("c")["gba"]), ["gba/Emerald.zip", "gba/Zelda.zip"])

    def test_full_system_has_no_game_list(self):
        self.card(games={"gba": {"full_system": True}})
        changed, calls = self.run_system()
        self.assertFalse(changed)
        self.assertEqual(calls, [])


DISCS = ["psx/A (USA).m3u", "psx/A (USA) (Disc 1).chd", "psx/A (USA) (Disc 2).chd", "psx/A (USA) (Disc 3).chd"]


class DiscFlow(Flow):
    """A multi-disc game's playlist and discs are switched on and off together, each saved as its own entry."""

    def setUp(self):
        super().setUp()
        self.files["psx/"] = {k: 10 for k in DISCS + ["psx/B (USA).chd"]}

    def psx(self, *steps):
        return self.run_system(*steps, bucket="psx")

    def test_rows_are_linked_and_marked(self):
        self.card()
        _, calls = self.psx(returns([False] * 5))
        _, labels, kw = calls[0]
        self.assertEqual(labels, ["A (USA) (Disc 1).chd", "A (USA) (Disc 2).chd", "A (USA) (Disc 3).chd",
                                  "A (USA).m3u", "B (USA).chd"])
        self.assertEqual(kw["links"], [[3, 0, 1, 2]] * 4 + [[]])
        self.assertEqual(kw["extras"][0][0], ("  🔗 4 files", "dim"))

    def test_toggling_the_playlist_adds_every_disc(self):
        self.card()
        self.psx(toggle("A (USA).m3u"))
        self.assertEqual(sorted(store.card_games("c")["psx"], key=lambda x: x["bucket"]),
                         sorted((g(k) for k in DISCS), key=lambda x: x["bucket"]))

    def test_toggling_a_later_disc_adds_the_whole_game_and_untoggling_removes_it(self):
        self.card()
        self.psx(toggle("A (USA) (Disc 2).chd"))
        self.assertEqual(sorted(x["bucket"] for x in store.card_games("c")["psx"]), sorted(DISCS))
        self.psx(toggle("A (USA) (Disc 3).chd"))
        self.assertEqual(store.card_games("c"), {})

    def test_status_counts_the_whole_game(self):
        self.card()

        def step(labels, kw):
            state = [True, False, False, False, False]  # only Disc 1 switched (as a script would)
            self.assertIn("4 file(s)", kw["status"](state))
            return state
        self.psx(step)

    def test_a_partial_pick_is_kept_until_a_member_is_toggled(self):
        self.card(games={"psx": [g(DISCS[1])]})
        self.psx(returns([True, False, False, False, False]))
        self.assertEqual(store.card_games("c"), {"psx": [g(DISCS[1])]})
        self.psx(toggle("A (USA) (Disc 1).chd"))  # Disc 1 off: the whole game is off
        self.assertEqual(store.card_games("c"), {})

    def test_a_set_filter_showing_one_disc_still_switches_the_whole_game(self):
        self.card()
        one = {"id": "one", "name": "One", "description": "", "games": [{"system": "psx", "bucket": DISCS[1]}]}

        def filtered(labels, kw):
            self.assertEqual(labels, ["A (USA) (Disc 1).chd"])
            return [True]
        with mock.patch.object(store, "load_sets", lambda: [one]):
            self.psx(returns((cardedit.SET_KEY, 0)), returns(0), filtered)
        self.assertEqual(sorted(x["bucket"] for x in store.card_games("c")["psx"]), sorted(DISCS))
        self.assertEqual(sorted(x["bucket"] for x in self.read("cards.json")["c"]["games"]["psx"]), sorted(DISCS))


class Links(unittest.TestCase):
    def run_keys(self, keys, labels, links, initial=None, locked=None):
        import curses

        class Screen:
            def __init__(self):
                self.keys = iter(keys)

            def getmaxyx(self):
                return 24, 80

            def get_wch(self):
                return next(self.keys)

            def __getattr__(self, name):
                return lambda *a, **k: None
        with mock.patch.object(curses, "curs_set"), mock.patch.object(curses, "use_default_colors"), \
                mock.patch.object(curses, "has_colors", return_value=False), \
                mock.patch.object(curses, "wrapper", side_effect=lambda f: f(Screen())):
            return picker.filter_list("t", labels, multi=True, initial=initial, links=links, locked=locked)

    def test_space_switches_linked_rows_to_the_new_state(self):
        links = [[0, 2], [], [0, 2]]
        self.assertEqual(self.run_keys([" ", "\n"], ["a", "b", "c"], links), [True, False, True])
        self.assertEqual(self.run_keys(["j", "j", " ", "\n"], ["a", "b", "c"], links, initial=[True, False, False]),
                         [True, False, True])  # partial: the toggled row's new state wins

    def test_toggle_all_reaches_rows_hidden_by_the_filter(self):
        links = [[0, 2], [], [0, 2]]
        self.assertEqual(self.run_keys(["/", "a", "\n", "a", "\n"], ["a", "b", "c"], links), [True, False, True])

    def test_no_links_toggles_one_row(self):
        self.assertEqual(self.run_keys([" ", "\n"], ["a", "b"], None), [True, False])


class MetaFlow(Flow):
    META = {"Emerald.zip": {"genre": "Platform", "releasedate": "2004-01-01"},
            "Ruby.zip": {"genre": "RPG / Pokemon", "releasedate": "2002"},
            "Zelda.zip": {"genre": "platform", "releasedate": "20010304"}}  # spelled differently: same genre

    def setUp(self):
        super().setUp()
        self.texts = {"scrapes/gba/metadata.json": json.dumps(self.META)}
        self.loaders, self.fetched, self.notes = [], [], []

        def get_text(key):
            self.fetched.append(key)
            if key not in self.texts:
                raise FileNotFoundError(key)
            return self.texts[key]
        for target, name, new in ((cardedit, "_spawn", self.loaders.append), (cardedit, "_metadata", {}),
                                  (s3, "get_text", get_text), (edit, "note", self.notes.append)):
            p = mock.patch.object(target, name, new)
            p.start()
            self.addCleanup(p.stop)

    def load(self):
        """Run the background loads that were started (what the worker thread does)."""
        while self.loaders:
            self.loaders.pop(0)()

    def opens_meta(self, labels, kw):
        self.load()
        return (cardedit.META_KEY, 0)

    def test_filters_narrow_combine_with_the_set_filter_and_clear(self):
        self.card()

        def fields(labels, kw):
            self.assertEqual(labels, ["Developer", "Publisher", "Genre", "Year"])
            self.assertEqual(kw["status"](None), "Pick a field")
            return 2

        def genres(labels, kw):
            self.assertEqual(labels, ["Platform", "RPG"])
            self.assertEqual(kw["extras"], [[("  2 game(s)", "dim")], [("  1 game(s)", "dim")]])
            return 0

        def platform(labels, kw):
            self.assertEqual(labels, ["Emerald.zip", "Zelda.zip"])
            kw["session"]["sel"][1] = True  # Zelda on
            return (cardedit.META_KEY, 0)

        def fields_again(labels, kw):
            self.assertEqual(kw["extras"][2], [("  Platform", "cyan")])
            return 3

        def years(labels, kw):
            self.assertEqual(labels, ["2001", "2004"])  # counted over the Platform games only
            return 0

        def both(labels, kw):
            self.assertEqual(labels, ["Zelda.zip"])
            self.assertEqual(kw["session"]["sel"], [True])
            return (cardedit.SET_KEY, 0)

        def with_set(labels, kw):
            self.assertEqual(labels, [])  # Pokemon's GBA games aren't Platform games
            return (cardedit.CLEAR_KEY, None)

        def everything(labels, kw):
            self.assertEqual(labels, ["Emerald.zip", "Ruby.sav", "Ruby.zip", "Zelda.zip"])
            return kw["session"]["sel"]
        _, calls = self.run_system(self.opens_meta, fields, genres, platform, fields_again, years, both, returns(0),
                                   with_set, everything)
        titles = [c[0] for c in calls]
        self.assertIn("genre: Platform (c shows all)", titles[3])
        self.assertIn("genre: Platform · year: 2001 (c shows all)", titles[6])
        self.assertIn("📦 Pokemon only · genre: Platform · year: 2001", titles[8])
        self.assertNotIn("c shows all", titles[9])
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Zelda.zip")]})
        self.assertEqual(self.fetched, ["scrapes/gba/metadata.json"])

    def test_menu_shows_loading_until_the_metadata_is_read(self):
        self.card()

        def loading(labels, kw):
            self.assertIn("loading", kw["status"](None))
            return 2  # chosen too early: the menu comes back

        def loaded(labels, kw):
            self.load()
            self.assertEqual(kw["status"](None), "Pick a field")
            return None
        self.run_system(returns((cardedit.META_KEY, 0)), loading, loaded, lambda labels, kw: kw["session"]["sel"])

    def test_missing_or_invalid_metadata_says_so(self):
        for texts in ({}, {"scrapes/gba/metadata.json": "not json"}, {"scrapes/gba/metadata.json": "[]"}):
            self.texts, self.notes[:] = texts, []
            self.card()
            _, calls = self.run_system(self.opens_meta, lambda labels, kw: kw["session"]["sel"])
            self.assertEqual(len(calls), 2)  # no field menu
            self.assertEqual(len(self.notes), 1)
            self.assertIn("No scraped metadata for Game Boy Advance yet", self.notes[0])

    def test_metadata_is_read_once_per_session(self):
        self.card()
        self.run_system(self.opens_meta, returns(None), lambda labels, kw: kw["session"]["sel"])
        self.run_system(returns((cardedit.META_KEY, 0)), returns(None), lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(self.fetched, ["scrapes/gba/metadata.json"])
        self.assertEqual(self.loaders, [])

    def test_ctrl_c_in_a_filtered_view_saves_what_was_toggled(self):
        self.card()

        def interrupted(labels, kw):
            self.assertEqual(labels, ["Emerald.zip", "Zelda.zip"])
            kw["session"]["sel"][1] = True
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.run_system(self.opens_meta, returns(2), returns(0), interrupted)
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Zelda.zip")]})


class SetupChange(DataDir):
    def test_changing_the_device_drops_games_it_cannot_play_at_save(self):
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde",
                                             "games": {"gba": [g("gba/A.zip")], "gb": [g("gb/B.gb")]}}})
        picks = iter([0, (edit.SETUP_KEY, 0), None, 4])  # Cards, v on the card, back, Done
        device = {**DEVICE, "systems": ["gba"]}
        with mock.patch.object(store, "repo_json", side_effect=lambda name: [dict(s) for s in CATALOG[name]]), \
                mock.patch.object(store, "load_manifest", return_value=CATALOG), \
                mock.patch.object(store, "load_sets", return_value=[]), \
                mock.patch.object(picker, "filter_list", side_effect=lambda *a, **k: next(picks)), \
                mock.patch.object(picker, "choose_setup", return_value=(device, "esde")), \
                mock.patch.object(ui, "choose", return_value="s"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(edit.edit_manifest(), 0)
        entry = self.read("cards.json")["c"]
        self.assertEqual((entry["device"], entry["games"]), ("d", {"gba": [g("gba/A.zip")]}))


class Poll(unittest.TestCase):
    def test_filter_list_polls_while_idle_and_colors_the_status(self):
        import curses
        polled, drawn = [], []

        class Screen:
            keys = iter([curses.error("timeout"), "\n"])

            def getmaxyx(self):
                return 24, 80

            def get_wch(self):
                k = next(self.keys)
                if isinstance(k, Exception):
                    raise k
                return k

            def addnstr(self, y, x, text, n, attr=0):
                drawn.append(text)

            def __getattr__(self, name):
                return lambda *a, **k: None
        with mock.patch.object(curses, "curs_set"), mock.patch.object(curses, "use_default_colors"), \
                mock.patch.object(curses, "has_colors", return_value=False), \
                mock.patch.object(curses, "wrapper", side_effect=lambda f: f(Screen())):
            self.assertEqual(picker.filter_list("t", ["a"], poll=lambda: polled.append(1),
                                                status=lambda s: ("over", "red")), 0)
        self.assertEqual(polled, [1])
        self.assertIn("over", drawn)


if __name__ == "__main__":
    unittest.main()
