import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import DataDir, feed_list, pilot_list, screen_lines  # noqa: E402
from helpers import VITA_DLC as DLC, VITA_GAME as G, VITA_OTHER as H, VITA_UPDATE as NEW  # noqa: E402
from sync_roms import budget, cardedit, collections, edit, inventory, picker, previews, s3, store, surprise, themeart, ui  # noqa: E402

U = budget.Usage


def system(bucket, name, bios=(), company="Nintendo"):
    return {"bucket": bucket, "name": name, "company": company, "folders": {"esde": bucket}, "bios": {"files": list(bios)}}


GBA, GB, PSX = system("gba", "Game Boy Advance", ["gba_bios.bin"]), system("gb", "Game Boy", ["gb_bios.bin"]), system("psx", "PlayStation", company="Sony")
DEVICE = {"id": "d", "name": "D", "firmwares": ["esde"], "systems": ["gba", "gb"]}
PSX_DEVICE = {**DEVICE, "systems": ["gba", "gb", "psx"]}
CATALOG = {"systems": [GBA, GB, PSX], "devices": [DEVICE],
           "layouts": {"esde": {"label": "ES-DE", "roms_dir": "ROMs", "bios_dir": "BIOS"}}}
SET = {"id": "pk", "name": "Pokemon", "description": "", "games": [
    {"system": "gba", "bucket": "gba/Ruby.zip", "files": ["gba/Ruby.sav"]}, {"system": "gb", "bucket": "gb/Red.gb"}]}


def g(key):
    return {"title": store.key_title(key), "bucket": key}


class Pure(unittest.TestCase):
    def test_pick_series_is_a_filterable_list(self):
        game_set = {"name": "S", "games": [{"series": "Alpha"}, {"series": "Alpha"}, {"series": "Beta"}]}
        with mock.patch.object(picker, "filter_list", return_value=0) as fl:
            self.assertEqual(cardedit.pick_series(game_set), "Alpha")
        self.assertEqual(fl.call_args[0][1], ["Alpha  (2 games)"])

    def test_size_text_is_decimal(self):
        self.assertEqual(cardedit.size_text(512 * 10 ** 9), "512 GB")
        self.assertEqual(cardedit.size_text(1_500_000_000), "1.5 GB")
        self.assertEqual(cardedit.size_text(999), "999 B")
        self.assertEqual(cardedit.size_text(2 * 10 ** 12), "2 TB")

    def test_header(self):
        self.assertEqual(cardedit.header(U(1_500_000_000, 3, False), 512 * 10 ** 9),
                         ("💾 1.5 GB / 512 GB · 510.5 GB free · 3 files", False))
        self.assertEqual(cardedit.header(U(600 * 10 ** 9, 9, False), 512 * 10 ** 9),
                         ("💾 600 GB / 512 GB · ⚠️  88 GB over · 9 files", True))
        self.assertEqual(cardedit.header(U(1_500_000_000, 3, False), 512 * 10 ** 9, count=False),
                         ("💾 1.5 GB / 512 GB · 510.5 GB free", False))  # the games list leaves the card's count out
        self.assertEqual(cardedit.header(U(10 ** 9, 1, False), None), ("💾 1 GB used · 1 file", False))
        text, over = cardedit.header(U(10 ** 9, 1, True), None)
        self.assertTrue(text.endswith("not sized (sync-roms cache update)"))
        self.assertFalse(over)
        self.assertEqual(cardedit.header(U(10 ** 9, 1, False), None, 0)[0], "💾 1 GB used · 1 file · ⬇️  0 B to download")

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
        full = {"gba": U(9 * 10 ** 9, 30, False), "gb": U(45 * 10 ** 9, 1234, False), "psx": U(7 * 10 ** 9, 1, False)}
        labels, extras = cardedit.system_labels(card, [GBA, GB, PSX], {"gb"}, usages, full)
        self.assertEqual([l.strip() for l in labels], ["Game Boy Advance", "⭐ Game Boy", "PlayStation"])  # the given order
        self.assertTrue(labels[1].startswith("⭐ "))
        self.assertEqual(extras[0], [("  4 picked", "green"), ("  2 GB", "dim"), ("  🗂️  9 GB full", "dim")])
        self.assertEqual(extras[1], [("", "green"), ("", "dim"), ("  🗂️  45 GB full", "dim")])  # nothing picked
        self.assertEqual(extras[2], [("  1 file", "green"), ("  7 GB", "dim"), ("  🗂️  full system", "cyan")])

    def test_system_labels_while_full_sizes_are_unknown(self):
        card = {"games": {"psx": {"full_system": True}}}
        usages = {"gba": U(2 * 10 ** 9, 4, False), "gb": U(0, 0, False), "psx": U(0, 0, True)}
        for full in ({}, {"gba": U(0, 0, True), "gb": U(5, 0, True), "psx": U(0, 0, True)}):  # not worked out, no cache
            extras = cardedit.system_labels(card, [GBA, GB, PSX], set(), usages, full)[1]
            self.assertEqual(extras[0], [("  4 picked", "green"), ("  2 GB", "dim"), ("  🗂️  … full", "dim")])
            self.assertEqual(extras[1], [("", "green"), ("", "dim"), ("  🗂️  … full", "dim")])
            self.assertEqual(extras[2], [("  … files", "green"), ("  …", "dim"), ("  🗂️  full system", "cyan")])

    def test_an_empty_folder_shows_no_full_size(self):
        extras = cardedit.system_labels({}, [GB], set(), {"gb": U(0, 0, False)}, {"gb": U(16, 0, False)})[1]
        self.assertEqual(extras, [[]])

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


def counted(kw, state):
    """The card's file count a games list's status works out for state (the list doesn't show it)."""
    with mock.patch.object(cardedit, "status_of", lambda u, c, fetch=None, count=True: u.count):
        return kw["status"](state)


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
        calls = self.run_card(returns((cardedit.SETTINGS_KEY, 0)), returns(0), returns((cardedit.SETTINGS_KEY, 0)),
                              returns(0), returns(None))
        self.assertIn("🎁 Surprise on", calls[0][0])
        self.assertEqual(calls[1][1][0], "🎁 Surprise: on")
        self.assertIn("🎁 Surprise off", calls[2][0])
        self.assertEqual(calls[3][1][0], "🎁 Surprise: off")
        self.assertIn("🎁 Surprise on", calls[4][0])
        self.assertNotIn("surprise", self.read("cards.json")["c"])

    def test_u_off_saves_false(self):
        self.card(size="1 GB")
        self.run_card(returns((cardedit.SETTINGS_KEY, 0)), returns(0), returns(None))
        self.assertIs(self.read("cards.json")["c"]["surprise"], False)

    def test_u_on_an_allium_card_saves_true_and_off_drops_it(self):
        self.write_json("cards.json", {"c": {"device": "d", "layout": "allium"}})
        self.assertTrue(cardedit.toggle_surprise("c"))
        self.assertIs(self.read("cards.json")["c"]["surprise"], True)
        self.assertFalse(cardedit.toggle_surprise("c"))
        self.assertNotIn("surprise", self.read("cards.json")["c"])

    def test_u_esc_changes_nothing(self):
        self.card(size="1 GB")
        self.run_card(returns((cardedit.SETTINGS_KEY, 0)), returns(None), returns(None))
        self.assertNotIn("surprise", self.read("cards.json")["c"])
        self.assertIsNone(self.read_settings().get("surprise_excluded_systems"))

    def test_u_systems_saves_the_unchecked_ones_for_every_card(self):
        self.card(size="1 GB")
        self.write_json("settings.json", {"surprise_excluded_systems": ["gone"], "bucket": "b"})
        names = [s["name"] for s in CATALOG["systems"]]
        calls = self.run_card(returns((cardedit.SETTINGS_KEY, 0)), returns(4), flip(0), returns(None))
        self.assertTrue(calls[2][1] and all(calls[2][1][i] == names[i] for i in range(len(names))))
        self.assertEqual(self.read_settings()["surprise_excluded_systems"], sorted(["gone", CATALOG["systems"][0]["bucket"]]))
        self.assertEqual(self.read_settings()["bucket"], "b")
        self.assertNotIn("surprise", self.read("cards.json")["c"])

    def test_u_systems_all_checked_removes_the_setting(self):
        self.card(size="1 GB")
        first = CATALOG["systems"][0]
        self.write_json("settings.json", {"surprise_excluded_systems": [first["bucket"]]})
        self.run_card(returns((cardedit.SETTINGS_KEY, 0)), returns(4), flip(0), returns(None))
        self.assertNotIn("surprise_excluded_systems", self.read_settings())

    def playable(self):
        return cardedit.can_play(CATALOG["systems"], (DEVICE, "esde"))

    def test_u_card_systems_saves_the_unchecked_ones_on_the_card_only(self):
        self.card(size="1 GB", surprise_excluded_systems=["gone"])
        first = self.playable()[0]
        calls = self.run_card(returns((cardedit.SETTINGS_KEY, 0)), returns(5), flip(0), returns(None))
        self.assertEqual(calls[2][1], [s["name"] for s in self.playable()])
        self.assertEqual(self.read("cards.json")["c"]["surprise_excluded_systems"], sorted(["gone", first["bucket"]]))
        self.assertIsNone(self.read_settings().get("surprise_excluded_systems"))

    def test_u_card_systems_all_checked_removes_the_field(self):
        first = self.playable()[0]
        self.card(size="1 GB", surprise_excluded_systems=[first["bucket"]])
        self.run_card(returns((cardedit.SETTINGS_KEY, 0)), returns(5), flip(0), returns(None))
        self.assertNotIn("surprise_excluded_systems", self.read("cards.json")["c"])

    def test_u_card_systems_shows_globally_excluded_ones_unchecked_and_keeps_them_global(self):
        first = self.playable()[0]
        self.card(size="1 GB")
        self.write_json("settings.json", {"surprise_excluded_systems": [first["bucket"]]})
        calls = self.run_card(returns((cardedit.SETTINGS_KEY, 0)), returns(5),
                              returns([True] * len(self.playable())), returns(None))
        self.assertIn("off on every card", calls[2][1][0])
        self.assertFalse(calls[2][2]["initial"][0])
        self.assertNotIn("surprise_excluded_systems", self.read("cards.json")["c"])

    def read_settings(self):
        try:
            return self.read("settings.json")
        except FileNotFoundError:
            return {}

    def test_u_off_clears_the_current_surprises(self):
        self.card(surprises=[{"system": "gba", "bucket": "gba/Zelda.zip", "title": "Zelda"}])
        self.assertFalse(cardedit.toggle_surprise("c"))
        self.assertNotIn("surprises", self.read("cards.json")["c"])

    def test_s_menu_turns_theme_and_collections_off_and_on(self):
        self.card(size="1 GB")
        calls = self.run_card(returns((cardedit.SETTINGS_KEY, 0)), returns(1), returns((cardedit.SETTINGS_KEY, 0)),
                              returns(2), returns((cardedit.SETTINGS_KEY, 0)), returns(1), returns(None))
        self.assertIn("Theme", calls[1][1][1])
        self.assertTrue(calls[1][1][1].endswith("on"))
        self.assertTrue(calls[3][1][1].endswith("off"))  # the theme, turned off by the first menu
        self.assertIs(self.read("cards.json")["c"]["custom_collections"], False)
        self.assertNotIn("theme", self.read("cards.json")["c"])  # the last menu turned it back on: on is not stored

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
        self.assertEqual(calls[1][2]["filters"], "🎁 past surprises only (c clear filters)")  # on the filter line
        self.assertNotIn("past surprises", calls[1][0])
        self.assertEqual(len(calls[2][1]), len(calls[0][1]))

    def test_p_with_no_past_surprises_says_so_and_keeps_the_list(self):
        self.card()
        with mock.patch.object(surprise, "past_keys", return_value=set()), \
                mock.patch.object(edit, "note") as note:
            _, calls = self.run_system(returns((cardedit.PAST_SURPRISE_KEY, 0)), lambda labels, kw: [False] * len(labels))
        self.assertIn("No past surprises on Game Boy Advance", note.call_args[0][0])
        self.assertEqual(len(calls[1][1]), len(calls[0][1]))

    def test_the_game_list_keeps_its_place_after_a_key_that_lists_the_same_games(self):
        self.card()
        place = {"row": 2, "query": "r", "view_mode": 1, "top": 1}

        def move(key):
            def step(labels, kw):
                kw["session"].update(place)
                return (key, 2)
            return step
        seen = []

        def look(labels, kw):
            seen.append({k: kw["session"].get(k) for k in place})
            return kw["session"]["sel"]
        with mock.patch.object(surprise, "past_keys", return_value=set()):
            self.run_system(move(cardedit.META_KEY), returns(None), look)  # m, then Esc in the field list
            self.run_system(move(cardedit.PAST_SURPRISE_KEY), look)  # p with no past surprises
            self.run_system(move(cardedit.SET_KEY), returns(None), look)  # s, then Esc in the set list
        self.assertEqual(seen, [place] * 3)

    def test_the_game_list_starts_over_when_a_key_changes_what_it_lists(self):
        self.card()
        seen = []

        def look(labels, kw):
            seen.append(kw["session"].get("query"))
            return kw["session"]["sel"]

        def filtered(labels, kw):
            kw["session"].update(query="r", row=0)
            return (cardedit.PAST_SURPRISE_KEY, 0)
        with mock.patch.object(surprise, "past_keys", return_value={"gba/Ruby.zip"}):
            self.run_system(filtered, look)
        self.assertEqual(seen, [None])

    def test_surprise_is_not_on_u_so_u_always_reverts(self):
        self.card()
        kw = self.run_card(returns(None))[0][2]
        self.assertEqual(cardedit.SETTINGS_KEY, "S")
        self.assertIn(cardedit.SETTINGS_KEY, kw["hotkeys"])
        self.assertNotIn("u", kw["hotkeys"])
        self.assertIn("S settings", cardedit.LIST_HINT)
        self.assertIn(("S", "settings menu: Surprise, theme, collections and RAOfflineProxy on or off, and the systems Surprise may use"), kw["key_help"])

    def test_settings_menu_toggles_raofflineproxy_and_shifts_the_systems_entries(self):
        self.card()
        seen = []
        with mock.patch.object(picker, "filter_list", lambda t, labels, **kw: seen.append(labels) or 3), \
                mock.patch.object(cardedit, "pick_surprise_systems") as every, \
                mock.patch.object(cardedit, "pick_card_surprise_systems") as one:
            cardedit.settings_menu("c", CATALOG["systems"], [])
            self.assertEqual(seen[0][3], "🏆 RAOfflineProxy (RetroAchievements offline proxy app): on")
            self.assertIs(self.read("cards.json")["c"]["raofflineproxy"], False)
            cardedit.settings_menu("c", CATALOG["systems"], [])
            self.assertNotIn("raofflineproxy", self.read("cards.json")["c"])
            with mock.patch.object(picker, "filter_list", return_value=4):
                cardedit.settings_menu("c", CATALOG["systems"], [])
            with mock.patch.object(picker, "filter_list", return_value=5):
                cardedit.settings_menu("c", CATALOG["systems"], [])
        every.assert_called_once()
        one.assert_called_once()

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
        self.assertEqual(calls[1][1], ["💖 Favs"])
        self.assertEqual(calls[1][2]["extras"], [[("  ✅ on the card", "green"), ("  2 playable, 2 not playable", "dim")]])
        self.assertEqual(self.read("cards.json")["c"]["collections"], ["favs"])

    def test_collections_hotkey_skips_malformed_games(self):
        self.favs("gba/Loose.zip", None, {"system": "gba"})
        self.card()
        with contextlib.redirect_stderr(io.StringIO()):
            calls = self.run_card(returns((cardedit.COLLECTIONS_KEY, 0)), returns(None), returns(None))
        self.assertEqual(calls[1][2]["extras"][0][1], ("  2 playable, 1 not playable", "dim"))

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
        self.assertEqual(counted(kw, kw["initial"]), 2)  # Ruby here, Red on Game Boy
        extras = self.run_card(returns(None))[0][2]["extras"]
        self.assertIn(("  1 picked", "green"), extras[0])

    def test_system_list_previews_each_system_and_nothing_past_them(self):
        self.card()
        kw = self.run_card(returns(None))[0][2]
        with mock.patch.object(previews, "system", side_effect=lambda s: "art-" + s["bucket"]):
            self.assertEqual([kw["preview"](i) for i in range(3)], ["art-gb", "art-gba", None])

    def test_collections_list_previews_each_collection_art(self):
        favs = {"id": "favs", "name": "Favs", "art": "surprise", "games": []}
        self.card()
        calls = []

        def look(labels, kw):
            calls.append(kw["preview"])
            return None
        with mock.patch.object(collections, "load_collections", lambda: [favs]), \
                mock.patch.object(picker, "filter_list", Script(look)), contextlib.redirect_stdout(io.StringIO()):
            cardedit.pick_collections("c", {"gba"})
        with mock.patch.object(previews, "collection", side_effect=lambda a: "art-" + str(a)):
            self.assertEqual([calls[0](0), calls[0](1)], ["art-surprise", None])

    def test_sets_list_previews_each_set_by_its_id(self):
        kw = {}

        def look(title, labels, **k):
            kw.update(k)
            return None
        with mock.patch.object(picker, "filter_list", look):
            cardedit.pick_set(GBA, [SET], [], {}, {"gba/Ruby.zip"})
        with mock.patch.object(previews, "collection", side_effect=lambda a: "art-" + a):
            self.assertEqual([kw["preview"](0), kw["preview"](1)], ["art-pk", None])

    def test_sets_list_counts_games_not_their_extra_files(self):
        seen = []

        def look(title, labels, extras=None, **k):
            seen.append((labels, [list(e) for e in extras]))
            return None
        with mock.patch.object(picker, "filter_list", look):
            cardedit.pick_set(GBA, [SET], [], {}, {"gba/Ruby.zip", "gba/Ruby.sav"}, synced=lambda: {"gba/Ruby.zip", "gba/Ruby.sav"})
            cardedit.pick_set(GBA, [SET], [], {}, {"gba/Ruby.sav"})
        self.assertEqual(seen[0], ([themeart.set_emoji(SET) + " Pokemon  (1 on Game Boy Advance)"], [[("  ✅", "cyan")]]))
        self.assertEqual(seen[1][0], [themeart.set_emoji(SET) + " Pokemon  (0 on Game Boy Advance, 1 not in storage)"])

    def test_games_list_previews_each_game_by_key_with_and_without_a_set_filter(self):
        self.card()
        seen = []

        def look(labels, kw):
            with mock.patch.object(previews, "game_thumb", side_effect=lambda k: "img-" + k):
                seen.append([kw["preview"](i) for i in range(len(labels) + 1)])
            self.assertEqual(kw["preview_width"], previews.GAME_WIDTH)  # a game's picture: 300 px wide at the top right
            return kw["session"]["sel"]

        def filtered(labels, kw):
            look(labels, kw)
            return (cardedit.CLEAR_KEY, 1)
        self.run_system(returns((cardedit.SET_KEY, 0)), returns(0), filtered, look)
        self.assertEqual(seen[0], ["img-gba/Ruby.sav", "img-gba/Ruby.zip", None])  # the set's rows, not all of them
        self.assertEqual(seen[1], ["img-gba/Emerald.zip", "img-gba/Ruby.sav", "img-gba/Ruby.zip", "img-gba/Zelda.zip", None])

    def test_opening_a_system_without_a_storage_cache_says_it_is_listing(self):
        self.card()
        for tree, said in ((None, True), (mock.Mock(), False)):
            out = io.StringIO()
            with mock.patch.object(inventory, "current", return_value=tree), \
                    mock.patch.object(inventory, "files", lambda p, sizes=True: self.files.get(p, {})), \
                    mock.patch.object(picker, "filter_list", Script(lambda labels, kw: kw["session"]["sel"])), \
                    contextlib.redirect_stdout(out):
                edit.edit_card_system("c", "gba", (DEVICE, "esde"))
            self.assertEqual("📡 Listing" in out.getvalue(), said, out.getvalue())

    def test_a_takes_every_game_the_set_filter_shows(self):
        self.card()
        filter_list = picker.filter_list  # the real list, driven by keys without a screen

        def take_all(labels, kw):
            self.assertEqual(kw["filters"], "📦 Pokemon only (c clear filters)")
            self.assertNotIn("Pokemon", calls[-1][0])
            with mock.patch.object(picker, "_run", lambda model: [model.key(k) for k in ("a", "enter")][-1]), \
                    mock.patch.object(picker, "_draws_images", return_value=False):
                return filter_list("t", labels, **kw)
        script = Script(returns((cardedit.SET_KEY, 0)), returns(0), take_all)
        calls = script.calls
        with mock.patch.object(picker, "filter_list", script), contextlib.redirect_stdout(io.StringIO()):
            edit.edit_card_system("c", "gba", (DEVICE, "esde"))
        self.assertEqual(calls[2][1], ["Ruby.sav", "Ruby.zip"])  # the set's games here, not Emerald or Zelda
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Ruby.sav"), g("gba/Ruby.zip")]})

    def run_card(self, *steps):
        script = Script(*steps)
        with mock.patch.object(picker, "filter_list", script), contextlib.redirect_stdout(io.StringIO()):
            cardedit.edit_card("c")
        return script.calls

    def test_s_opens_a_set_then_its_games(self):
        self.card()
        calls = self.run_card(returns((cardedit.SET_KEY, 0)), returns(0), toggle("Game Boy — Red"), returns(None))
        self.assertTrue(calls[1][1][0].startswith(f"{themeart.set_emoji(SET)} Pokemon"))
        self.assertEqual({x["bucket"] for x in store.card_games("c")["gb"]}, {"gb/Red.gb"})

    def test_s_says_when_no_set_has_games_here(self):
        self.card()
        notes = []
        only_psx = {"id": "x", "name": "X", "description": "", "games": [{"system": "psx", "bucket": "psx/X.chd"}]}
        with mock.patch.object(store, "load_sets", return_value=[only_psx]), \
                mock.patch.object(edit, "note", notes.append):
            calls = self.run_card(returns((cardedit.SET_KEY, 0)), returns(None))
        self.assertEqual(len(calls), 2)  # the system list twice, no set list
        self.assertEqual(notes, ["ℹ️  No set has games in storage for this card's systems."])

    def test_set_list_counts_synced_games(self):
        self.card(games={"gb": [g("gb/Red.gb")]})
        calls = self.run_card(returns((cardedit.SET_KEY, 0)), returns(None), returns(None))
        self.assertEqual(calls[1][2]["extras"], [[("  1/2", "cyan")]])
        self.assertEqual(calls[1][1], [f"{themeart.set_emoji(SET)} Pokemon  (2 games)"])

    def test_s_is_in_the_hint_and_help(self):
        self.assertIn("s set", cardedit.LIST_HINT)
        self.assertIn(cardedit.SET_KEY, [k for k, _ in cardedit.LIST_KEYS])

    def test_esc_on_the_set_list_returns_to_systems(self):
        self.card()
        calls = self.run_card(returns((cardedit.SET_KEY, 0)), returns(None), returns(None))
        self.assertEqual(len(calls), 3)
        self.assertIn("its systems", calls[2][0])

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
        self.assertEqual(kw["extras"][1], [("  1 picked", "green"), ("  5 B", "dim"), ("  🗂️  … full", "dim")])  # the ROM
        self.assertEqual(kw["status"](None), ("💾 21 B / 1 GB · 1 GB free · 1 file", "green"))  # ROM and the GBA BIOS

    def test_full_sizes_fill_in_when_the_worker_hands_them_over(self):
        self.card(games={"gba": [g("gba/Ruby.zip")]})
        self.cache = {"gba/": self.files["gba/"], "gb/": self.files["gb/"], "scrapes/gba/": {}, "scrapes/gb/": {},
                      "BIOS/": {"BIOS/gba_bios.bin": 16, "BIOS/gb_bios.bin": 1000}}
        workers = []

        def check(labels, kw):
            self.assertEqual(kw["extras"], [[("", "green"), ("", "dim"), ("  🗂️  … full", "dim")],
                                            [("  1 picked", "green"), ("  5 B", "dim"), ("  🗂️  … full", "dim")]])
            kw["poll"]()  # nothing handed over yet
            self.assertIn(("  🗂️  … full", "dim"), kw["extras"][0])
            workers.pop()()
            kw["poll"]()
            self.assertEqual(kw["extras"], [[("", "green"), ("", "dim"), ("  🗂️  1 KB full", "dim")],  # Red.gb and the Game Boy BIOS
                                            [("  1 picked", "green"), ("  5 B", "dim"), ("  🗂️  32 B full", "dim")]])
            return (cardedit.FULL_KEY, 1)  # in place: the full system shows its files from the kept sizes

        def full_on(labels, kw):
            self.assertEqual(kw["extras"][1], [("  4 files", "green"), ("  32 B", "dim"), ("  🗂️  full system", "cyan")])
            return None
        with mock.patch.object(cardedit, "_spawn", workers.append):
            self.run_card(check, full_on)
        self.assertEqual(workers, [])  # worked out once for the session

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
        self.assertEqual(kw["extras"][labels.index("Ruby.zip")][1], ("  📦 Pokemon", "cyan"))
        self.assertTrue(changed)
        entry = self.read("cards.json")["c"]
        self.assertEqual(entry["excluded"], {"gba": ["gba/Ruby.zip"]})
        self.assertEqual(entry["games"], {"sets": ["pk"]})

    def with_variants(self, *variants):
        """Sets with a "vs" set whose gba/Ruby.zip has the given variants."""
        vset = {"id": "vs", "name": "Variants", "description": "", "games": [
            {"system": "gba", "bucket": "gba/Ruby.zip", "variants": list(variants)}]}
        p = mock.patch.object(store, "load_sets", return_value=[SET, vset])
        p.start()
        self.addCleanup(p.stop)

    RED = {"bucket": "gb/Red.gb", "note": "GB: the original"}

    def test_variant_line_shows_on_the_highlighted_game(self):
        self.with_variants(self.RED)
        self.card()

        def step(labels, kw):
            self.assertEqual(kw["row_note"](labels.index("Ruby.zip")), "↳ Variant: GB: the original (v adds it)")
            self.assertEqual(kw["row_note"](labels.index("Zelda.zip")), "")
            self.assertEqual(kw["hint"], cardedit.GAMES_HINT)
            self.assertIn(cardedit.VARIANT_KEY, kw["hotkeys"])
            return kw["session"]["sel"]
        self.run_system(step)
        self.assertEqual(cardedit.GAMES_HINT,
                         "Space toggle · Enter done · s set · m meta · p past · v variant")

    def test_a_game_with_its_variant_on_the_card_is_marked_in_the_list(self):
        self.with_variants(self.RED)
        self.card(games={"gba": [g("gba/Zelda.zip")], "psx": [g("psx/x.chd")], "sets": ["vs"]},
                  excluded={"gba": ["gba/Ruby.zip"]})

        def press_v(labels, kw):
            self.assertEqual(kw["extras"][labels.index("Ruby.zip")][-1][0], "")
            return (cardedit.VARIANT_KEY, labels.index("Ruby.zip"))

        def marked(labels, kw):
            self.assertIn("🔀", kw["extras"][labels.index("Ruby.zip")][-1][0])
            self.assertEqual(kw["extras"][labels.index("Zelda.zip")][-1][0], "")
            return kw["session"]["sel"]
        self.run_system(press_v, marked)

    def test_v_adds_the_variant_on_its_own_system_and_saves(self):
        self.with_variants(self.RED)
        self.card(games={"gba": [g("gba/Zelda.zip")], "psx": [g("psx/x.chd")], "sets": ["vs"]},
                  excluded={"gba": ["gba/Ruby.zip"]})

        def press_v(labels, kw):
            return (cardedit.VARIANT_KEY, labels.index("Ruby.zip"))

        def now_on(labels, kw):
            self.assertTrue(kw["row_note"](labels.index("Ruby.zip")).endswith("✅ on the card (v removes it)"))
            return kw["session"]["sel"]
        changed, _ = self.run_system(press_v, now_on)
        self.assertTrue(changed)
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Zelda.zip")], "gb": [g("gb/Red.gb")],
                                                 "psx": [g("psx/x.chd")], "sets": ["vs"]})
        self.assertEqual(store.card_excluded("c"), {"gba": ["gba/Ruby.zip"]})

    def test_v_counts_the_variant_in_the_status(self):
        self.with_variants(self.RED)
        self.card(size="1 GB")
        self.cache = {"gba/": self.files["gba/"], "gb/": self.files["gb/"], "scrapes/gba/": {}, "BIOS/": {}}
        seen = []

        def look(labels, kw):
            seen.append(kw["status"](kw["session"]["sel"])[0])
            counts.append(counted(kw, kw["session"]["sel"]))
            return (cardedit.VARIANT_KEY, labels.index("Ruby.zip")) if len(seen) == 1 else kw["session"]["sel"]
        counts = []
        self.run_system(look, look)
        self.assertEqual(counts[0], 0)
        self.assertIn("2 B /", seen[1])
        self.assertEqual(counts[1], 1)
        self.assertNotIn("file", seen[1])  # the card's count is left out of a games list

    def test_v_on_another_system_clears_its_exclusion(self):
        self.with_variants(self.RED)
        self.card(games={"sets": ["pk"]}, excluded={"gb": ["gb/Red.gb"], "gba": ["gba/Zelda.zip"]})

        def off_then_v(labels, kw):
            self.assertTrue(kw["row_note"](labels.index("Ruby.zip")).endswith("(v adds it)"))
            return (cardedit.VARIANT_KEY, labels.index("Ruby.zip"))

        def now_on(labels, kw):
            self.assertTrue(kw["row_note"](labels.index("Ruby.zip")).endswith("✅ on the card (v removes it)"))
            return kw["session"]["sel"]
        self.run_system(off_then_v, now_on)
        self.assertEqual(store.card_games("c"), {"gb": [g("gb/Red.gb")], "sets": ["pk"]})
        self.assertEqual(store.card_excluded("c"), {"gba": ["gba/Zelda.zip"]})

    def test_v_adds_a_variants_files_with_it(self):
        self.with_variants({**self.RED, "files": ["gb/Red.sav"]})
        self.card()
        self.run_system(lambda labels, kw: (cardedit.VARIANT_KEY, labels.index("Ruby.zip")),
                        lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(store.card_games("c"), {"gb": [g("gb/Red.gb"), g("gb/Red.sav")]})

    def test_v_again_removes_it(self):
        self.with_variants({**self.RED, "files": ["gb/Red.sav"]})
        self.card(games={"gba": [g("gba/Zelda.zip")]})
        press_v = lambda labels, kw: (cardedit.VARIANT_KEY, labels.index("Ruby.zip"))  # noqa: E731
        self.run_system(press_v, press_v, lambda labels, kw: kw["session"]["sel"])
        self.assertNotIn("gb", store.card_games("c"))
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Zelda.zip")]})

    def test_v_on_a_same_system_variant_toggles_the_row(self):
        self.with_variants({"bucket": "gba/Emerald.zip", "note": "The third version"})
        self.card()
        sel = []

        def press_v(labels, kw):
            return (cardedit.VARIANT_KEY, labels.index("Ruby.zip"))

        def look(labels, kw):
            sel.append(kw["session"]["sel"][labels.index("Emerald.zip")])
            return press_v(labels, kw) if len(sel) == 1 else kw["session"]["sel"]
        self.run_system(press_v, look, look)
        self.assertEqual(sel, [True, False])
        self.assertEqual(store.card_games("c"), {})
        self.run_system(press_v, lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Emerald.zip")]})

    def test_v_leaves_a_full_system_or_set_covered_variant_alone(self):
        self.with_variants(self.RED)
        press_v = lambda labels, kw: (cardedit.VARIANT_KEY, labels.index("Ruby.zip"))  # noqa: E731

        def on_then_enter(labels, kw):
            self.assertTrue(kw["row_note"](labels.index("Ruby.zip")).endswith("✅ on the card (v removes it)"))
            return kw["session"]["sel"]
        for games in ({"gb": {"full_system": True}}, {"sets": ["pk"]}):
            self.card(games=games)
            before = self.read("cards.json")
            self.run_system(press_v, on_then_enter)
            self.assertEqual(self.read("cards.json"), before)
            self.assertEqual(store.card_excluded("c"), {})

    def test_v_leaves_a_collection_variant_alone(self):
        self.with_variants(self.RED)
        self.favs()
        self.card(collections=["favs"])
        before = self.read("cards.json")

        def on_then_v(labels, kw):
            self.assertTrue(kw["row_note"](labels.index("Ruby.zip")).endswith("✅ on the card (v removes it)"))
            return (cardedit.VARIANT_KEY, labels.index("Ruby.zip"))
        self.run_system(on_then_v, lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(self.read("cards.json"), before)

    def test_v_with_two_variants_opens_a_picker(self):
        self.with_variants(self.RED, {"bucket": "psx/x.chd", "note": "PS1: x"})
        self.card()
        changed, calls = self.run_system(lambda labels, kw: (cardedit.VARIANT_KEY, labels.index("Ruby.zip")),
                                         returns(0), lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(calls[0][2]["row_note"](calls[0][1].index("Ruby.zip")),
                         "↳ 2 variants (v picks): GB: the original; PS1: x")
        title, labels, kw = calls[1]
        self.assertEqual(title, "Variants of Ruby")
        self.assertEqual(labels, ["⬜ GB: the original", "⬜ PS1: x"])
        self.assertFalse(kw.get("multi"))
        self.assertEqual(store.card_games("c"), {"gb": [g("gb/Red.gb")]})

    def test_v_with_two_variants_cancelled_changes_nothing(self):
        self.with_variants(self.RED, {"bucket": "psx/x.chd", "note": "PS1: x"})
        self.card()
        changed, _ = self.run_system(lambda labels, kw: (cardedit.VARIANT_KEY, labels.index("Ruby.zip")),
                                     returns(None), lambda labels, kw: kw["session"]["sel"])
        self.assertFalse(changed)

    def test_set_filter_narrows_to_that_set_on_this_system_and_clears(self):
        self.card()

        def pick_first_set(labels, kw):
            self.assertEqual(labels, [themeart.set_emoji(SET) + " Pokemon  (1 on Game Boy Advance)"])
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
        self.assertIn("Pokemon only", calls[2][2]["filters"])
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Ruby.zip")]})

    def series_set(self):
        """SET with Ruby and Emerald in series A on gba, and Red in A on gb (not counted on gba)."""
        return {**SET, "games": [{**SET["games"][0], "series": "A"}, {"system": "gba", "bucket": "gba/Emerald.zip", "series": "A"},
                                 {"system": "gba", "bucket": "gba/Zelda.zip", "series": "B"}, {**SET["games"][1], "series": "B"}]}

    def run_system_series(self, game_set, *steps):
        """Drives edit_system with store's sets as [game_set]; the series list (no multi mode, no hotkeys) answers 0."""
        script, lists = Script(*steps), []

        def fake(title, labels, **kw):
            if "multi" in kw or "hotkeys" in kw:
                return script(title, labels, **kw)
            lists.append(list(labels))
            return 0
        with mock.patch.object(store, "load_sets", return_value=[game_set]), \
                mock.patch.object(picker, "filter_list", fake), contextlib.redirect_stdout(io.StringIO()):
            edit.edit_card_system("c", "gba", (DEVICE, "esde"))
        return script.calls, lists

    def test_r_after_a_set_narrows_to_one_of_its_series_on_this_system(self):
        self.card()
        calls, lists = self.run_system_series(
            self.series_set(), returns((cardedit.SET_KEY, 0)), returns(0), returns((cardedit.SERIES_KEY, 0)),
            returns((cardedit.CLEAR_KEY, 0)), lambda labels, kw: kw["session"]["sel"])
        self.assertIn(cardedit.SERIES_KEY, calls[0][2]["hotkeys"])
        self.assertEqual(lists, [["A  (2 games)"]])  # Ruby and Emerald; B has one game on gba
        self.assertEqual(calls[3][1], ["Emerald.zip", "Ruby.sav", "Ruby.zip"])
        self.assertIn("🎮 A", calls[3][2]["filters"])
        self.assertEqual(len(calls[4][1]), 4)  # c clears the series with the set

    def test_r_without_a_set_notes_and_lists_again(self):
        self.card()
        with mock.patch.object(edit, "note") as note:
            calls, lists = self.run_system_series(
                self.series_set(), returns((cardedit.SERIES_KEY, 0)), lambda labels, kw: kw["session"]["sel"])
        self.assertIn("to a set with s first", note.call_args[0][0])
        self.assertEqual(lists, [])
        self.assertEqual(calls[1][1], calls[0][1])

    def test_picking_another_set_drops_the_series(self):
        self.card()
        other = {"id": "o", "name": "Other", "description": "", "games": [{"system": "gba", "bucket": "gba/Zelda.zip"}]}
        script, calls = Script(returns((cardedit.SET_KEY, 0)), returns(0), returns((cardedit.SERIES_KEY, 0)),
                               returns((cardedit.SET_KEY, 0)), returns(1), lambda labels, kw: kw["session"]["sel"]), []

        def fake(title, labels, **kw):
            if "multi" in kw or "hotkeys" in kw:
                return script(title, labels, **kw)
            return 0
        with mock.patch.object(store, "load_sets", return_value=[self.series_set(), other]), \
                mock.patch.object(picker, "filter_list", fake), contextlib.redirect_stdout(io.StringIO()):
            edit.edit_card_system("c", "gba", (DEVICE, "esde"))
        self.assertEqual(script.calls[-1][1], ["Zelda.zip"])
        self.assertNotIn("🎮", script.calls[-1][2]["filters"])

    def test_set_list_counts_what_is_in_storage(self):
        self.card()
        self.files["gba/"].pop("gba/Ruby.sav")
        other = {"id": "gone", "name": "Gone", "description": "", "games": [{"system": "gba", "bucket": "gba/X.zip"}]}

        def offered(labels, kw):
            self.assertEqual(labels, [themeart.set_emoji(SET) + " Pokemon  (1 on Game Boy Advance)"])  # its extra file missing is not a missing game; Gone: nothing to show
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
            self.assertEqual(kw["extras"], [[("  0/1", "cyan")]])
            return None
        self.run_system(returns((cardedit.SET_KEY, 0)), returns((" ", 0)), returns((" ", 0)), removed,
                        lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(store.card_games("c"), {})

    def set_list_shows(self, count):
        """A set list step that checks the first set's count and leaves the list."""
        def step(labels, kw):
            self.assertEqual(kw["extras"], [[(f"  {count}", "cyan")]])
            return None
        return step

    def test_set_list_toggle_switches_on_a_game_excluded_from_a_referenced_set(self):
        self.card(games={"sets": ["pk"]}, excluded={"gba": ["gba/Ruby.zip"]})
        self.run_system(returns((cardedit.SET_KEY, 0)), returns((" ", 0)), self.set_list_shows("✅"),
                        lambda labels, kw: kw["session"]["sel"])
        entry = self.read("cards.json")["c"]
        self.assertEqual(entry["games"], {"sets": ["pk"]})  # the set syncs it: no direct pick
        self.assertNotIn("gba", entry.get("excluded", {}))

    def test_set_list_toggle_switches_on_an_excluded_direct_pick(self):
        self.card(games={"gba": [g("gba/Ruby.sav"), g("gba/Ruby.zip")]}, excluded={"gba": ["gba/Ruby.zip"]})
        self.run_system(returns((cardedit.SET_KEY, 0)), returns((" ", 0)), self.set_list_shows("✅"),
                        lambda labels, kw: kw["session"]["sel"])
        entry = self.read("cards.json")["c"]
        self.assertEqual(entry["games"], {"gba": [g("gba/Ruby.sav"), g("gba/Ruby.zip")]})  # still one pick each
        self.assertNotIn("gba", entry.get("excluded", {}))

    def test_set_list_toggle_on_a_referenced_set_excludes_its_games(self):
        self.card(games={"sets": ["pk"]})
        self.run_system(returns((cardedit.SET_KEY, 0)), returns((" ", 0)), self.set_list_shows("0/1"),
                        lambda labels, kw: kw["session"]["sel"])
        entry = self.read("cards.json")["c"]
        self.assertEqual(entry["games"], {"sets": ["pk"]})  # the set syncs them: no direct picks to add or remove
        self.assertEqual(entry["excluded"], {"gba": ["gba/Ruby.sav", "gba/Ruby.zip"]})

    def test_set_list_toggle_again_on_a_referenced_set_brings_its_games_back(self):
        self.card(games={"sets": ["pk"]})
        before = self.read("cards.json")
        changed, _ = self.run_system(returns((cardedit.SET_KEY, 0)), returns((" ", 0)), returns((" ", 0)),
                                     self.set_list_shows("✅"), lambda labels, kw: kw["session"]["sel"])
        self.assertFalse(changed)
        self.assertEqual(self.read("cards.json"), before)

    def test_game_view_status_counts_pending_picks(self):
        self.card(size="1 GB")
        self.cache = {"gba/": self.files["gba/"], "scrapes/gba/": {}, "BIOS/": {"BIOS/gba_bios.bin": 16}, "gb/": {}}

        def step(labels, kw):
            self.assertEqual(kw["status"]([False] * 4), ("💾 0 B / 1 GB · 1 GB free", "green"))
            self.assertEqual(kw["status"]([True, False, False, True]), ("💾 26 B / 1 GB · 1 GB free", "green"))
            self.assertEqual(counted(kw, [True, False, False, True]), 2)
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
        with mock.patch.object(cardedit, "status_of", side_effect=lambda u, c, fetch=None, count=True: seen.append(u.bytes)):
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

    def run_keep(self, match, *steps):
        script = Script(*steps)
        with mock.patch.object(picker, "filter_list", script), contextlib.redirect_stdout(io.StringIO()):
            cardedit.edit_card("c", (DEVICE, "esde"), card_match=match)
        return script.calls

    def test_K_keeps_card_files(self):
        self.card()
        notes = []

        def match(system, keys):
            return {"gba/Ruby.zip"} if system["bucket"] == "gba" else set()
        with mock.patch.object(edit, "note", notes.append):
            calls = self.run_keep(match, returns((cardedit.KEEP_KEY, 0)), returns(None))
        self.assertIn(cardedit.KEEP_KEY, calls[0][2]["hotkeys"])
        self.assertIn("K keep", calls[0][2]["hint"])
        self.assertIn(g("gba/Ruby.zip"), store.card_games("c")["gba"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes, ["Picked 1 card file(s) in 1 system(s)."])

    def test_k_skips_full_system(self):
        self.card(games={"gba": {"full_system": True}})
        asked = []

        def match(system, keys):
            asked.append(system["bucket"])
            return set()
        self.run_keep(match, returns((cardedit.KEEP_KEY, 0)), returns(None))
        self.assertNotIn("gba", asked)

    def test_k_hidden_without_callback(self):
        self.card()
        calls = self.run_card(returns(None))
        self.assertNotIn(cardedit.KEEP_KEY, calls[0][2]["hotkeys"])
        self.assertNotIn("K keep", calls[0][2]["hint"])

    def test_collections_screen_toggles_with_enter_in_place(self):
        favs = {"id": "favs", "name": "Favs", "games": []}
        self.card()
        seen = {}

        def look(labels, kw):
            seen.update(kw)
            self.assertTrue(kw["on_hotkey"]("enter", 0))  # handled in the list: it isn't torn down and reopened
            return None
        with mock.patch.object(collections, "load_collections", lambda: [favs]), \
                mock.patch.object(picker, "filter_list", Script(look)), contextlib.redirect_stdout(io.StringIO()):
            cardedit.pick_collections("c", {"gba"})
        self.assertIn("enter", seen["hotkeys"])
        self.assertEqual(store.load_cards()["c"]["collections"], ["favs"])

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
        self.assertIn("0 files · ⬇️  0 B to download", statuses[0])
        self.assertIn("1 file · ⬇️  7 B to download", statuses[1])

    def test_picked_game_not_in_storage_is_not_still_sizing(self):
        self.card(games={"gba": [g("gba/Ruby.zip"), g("gba/Gone.zip")]})
        self.cache = {"gba/": self.files["gba/"], "scrapes/gba/": {}, "BIOS/": {}}

        def step(labels, kw):
            self.assertIn("Gone.zip  ⚠️ not in storage", labels)
            self.assertEqual(kw["status"](kw["session"]["sel"]), "💾 5 B used")
            return kw["session"]["sel"]
        self.run_system(step)
        with mock.patch.object(store, "recommended_systems", return_value=set()):
            calls = self.run_card(returns(None))
        self.assertEqual(calls[0][2]["status"](None), "💾 5 B used · 2 files")

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

    def test_ctrl_c_in_the_set_list_only_saves(self):
        self.card()

        def ruby_on_then_sets(labels, kw):
            kw["session"]["sel"][labels.index("Ruby.zip")] = True
            return (cardedit.SET_KEY, 0)

        def interrupted(labels, kw):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):  # Space twice in the set list: its games on, then off again
            self.run_system(ruby_on_then_sets, returns((" ", 0)), returns((" ", 0)), interrupted)
        self.assertEqual(store.card_games("c"), {})  # the pass before the set list isn't applied a second time

    def test_ctrl_c_in_the_variant_list_saves_what_was_toggled(self):
        self.with_variants(self.RED, {"bucket": "psx/x.chd", "note": "PS1: x"})
        self.card()

        def zelda_on_then_v(labels, kw):
            kw["session"]["sel"][labels.index("Zelda.zip")] = True
            return (cardedit.VARIANT_KEY, labels.index("Ruby.zip"))

        def interrupted(labels, kw):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.run_system(zelda_on_then_v, interrupted)
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Zelda.zip")]})

    def test_a_systems_games_keep_select_all(self):
        self.card()
        _, calls = self.run_system(returns([False] * 4))
        self.assertIs(calls[0][2].get("select_all", True), True)

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

    def test_full_system_has_no_game_list(self):
        self.card(games={"gba": {"full_system": True}})
        changed, calls = self.run_system()
        self.assertFalse(changed)
        self.assertEqual(calls, [])

    def sized(self):
        self.cache = {"gba/": self.files["gba/"], "gb/": self.files["gb/"], "scrapes/gb/": {},
                      "scrapes/gba/": {"scrapes/gba/screenshots/Ruby.png": 100, "scrapes/gba/screenshots/Zelda.png": 30},
                      "BIOS/": {"BIOS/gba_bios.bin": 16, "BIOS/gb_bios.bin": 1000}}

    def fresh(self, count=True):
        """(status, extras) of the system list from a full recount of the card as saved now (count: with the file
        count, as the system list shows it)."""
        card = cardedit.card_entry("c", (DEVICE, "esde"))
        usages = budget.system_usages(card, [GB, GBA])
        full = {s["bucket"]: budget.full_usage(card, s) for s in (GB, GBA)}
        return (cardedit.status_of(budget.card_usage(card, [GB, GBA], usages), budget.card_capacity(card), count=count),
                cardedit.system_labels(card, [GB, GBA], set(), usages, full)[1])

    @contextlib.contextmanager
    def workers_run_at_once(self):
        """Background work runs as it is started (no metadata to read), so the full sizes are in from the first draw."""
        with mock.patch.object(cardedit, "_spawn", lambda fn: fn()), \
                mock.patch.object(s3, "get_text", side_effect=FileNotFoundError("metadata.json")):
            yield

    def same_as_fresh(self, labels, kw):
        status, extras = self.fresh()
        self.assertEqual(kw["status"](None), status)
        self.assertEqual(kw["extras"], extras)
        return None

    def test_kept_totals_match_a_full_recount_after_every_kind_of_change(self):
        self.favs()
        zelda = [{"system": "gba", "bucket": "gba/Zelda.zip", "title": "Zelda"}]

        def game_view_is_fresh(step):
            def check(labels, kw):
                self.assertEqual(kw["status"](kw["initial"]), self.fresh(count=False)[0])
                with mock.patch.object(cardedit, "status_of", lambda u, c, fetch=None, count=True: u):
                    kept, full = kw["status"](kw["initial"]), self.fresh()[0]
                self.assertEqual(kept.count, full.count)
                return step(labels, kw)
            return check
        keep = lambda labels, kw: kw["session"]["sel"]  # noqa: E731
        cases = {
            "toggle a game": ({"games": {"gba": [g("gba/Ruby.zip")], "gb": [g("gb/Red.gb")]}},
                              [returns(1), game_view_is_fresh(toggle("Zelda.zip", "Ruby.sav"))]),
            "f on": ({"games": {"gba": [g("gba/Ruby.zip")]}}, [returns((cardedit.FULL_KEY, 1))]),
            "f off": ({"games": {"gba": {"full_system": True}}}, [returns((cardedit.FULL_KEY, 1))]),
            "add a set's games": ({"games": {"gb": [g("gb/Red.gb")]}},
                                  [returns(1), returns((cardedit.SET_KEY, 0)), returns((" ", 0)), returns(None), keep]),
            "remove a set's games": ({"games": {"gba": [g("gba/Ruby.zip"), g("gba/Ruby.sav")]}},
                                     [returns(1), returns((cardedit.SET_KEY, 0)), returns((" ", 0)), returns(None), keep]),
            "toggle a collection on": ({}, [returns((cardedit.COLLECTIONS_KEY, 0)), returns((" ", 0)), returns(None)]),
            "toggle a collection off": ({"collections": ["favs"], "games": {"gba": [g("gba/Zelda.zip")]}},
                                        [returns((cardedit.COLLECTIONS_KEY, 0)), returns((" ", 0)), returns(None)]),
            "clear all": ({"games": {"gba": [g("gba/Ruby.zip")], "gb": {"full_system": True}, "sets": ["pk"]},
                           "excluded": {"gba": ["gba/Ruby.sav"]}}, [returns((cardedit.CLEAR_ALL_KEY, 0))]),
            "surprise off": ({"surprises": zelda}, [returns((cardedit.SETTINGS_KEY, 0)), returns(0)]),
            "exclude a set game": ({"games": {"sets": ["pk"]}}, [returns(1), game_view_is_fresh(toggle("Ruby.zip"))]),
        }
        for case, (entry, steps) in cases.items():
            with self.subTest(case), mock.patch.object(ui, "confirm", return_value=True), self.workers_run_at_once():
                self.card(size="1 GB", **entry)
                self.sized()
                before = self.fresh()
                self.run_card(*steps, self.same_as_fresh)
                self.assertNotEqual(self.fresh(), before)  # the change shows

    @contextlib.contextmanager
    def counted(self):
        """{budget function: calls} for the recount functions, counted inside the with block."""
        calls = {}
        with contextlib.ExitStack() as stack:
            for fn in ("system_usages", "system_usage", "_system_usage"):
                def count(*a, _fn=fn, _real=getattr(budget, fn)):
                    calls[_fn] = calls.get(_fn, 0) + 1
                    return _real(*a)
                stack.enter_context(mock.patch.object(budget, fn, count))
            yield calls

    def test_editor_recounts_only_the_system_that_changed(self):
        cases = {
            "open": ([], {"system_usages": 1, "_system_usage": 2}),
            "enter and leave": ([returns(1), lambda labels, kw: kw["initial"]], {"system_usages": 1, "_system_usage": 2}),
            "change a system": ([returns(1), toggle("Zelda.zip")],
                                {"system_usages": 1, "system_usage": 1, "_system_usage": 3}),
            "f": ([returns((cardedit.FULL_KEY, 1))], {"system_usages": 1, "system_usage": 1, "_system_usage": 3}),
        }
        for case, (steps, want) in cases.items():
            with self.subTest(case):
                self.card(size="1 GB", games={"gba": [g("gba/Ruby.zip")]})
                self.sized()
                with self.counted() as calls:
                    self.run_card(*steps, returns(None))
                self.assertEqual(calls, want)

    def test_a_storage_cache_change_recounts_every_system(self):
        self.card(size="1 GB", games={"gba": [g("gba/Ruby.zip")], "gb": [g("gb/Red.gb")]})
        self.sized()
        version = [0]

        def leave(labels, kw):  # the cache changes while the system is open
            self.cache["gb/"] = {"gb/Red.gb": 50}
            version[0] += 1
            return kw["initial"]
        with mock.patch.object(inventory, "version", lambda: version[0]), mock.patch.dict(budget._scrapes), \
                self.workers_run_at_once():
            self.run_card(returns(1), leave, self.same_as_fresh)

    def test_v_on_another_systems_variant_recounts_that_system(self):
        self.with_variants(self.RED)
        self.card(size="1 GB", games={"gba": [g("gba/Zelda.zip")]})
        self.sized()
        seen = []

        def look(labels, kw):
            seen.append(kw["status"](kw["session"]["sel"]))
            return kw["session"]["sel"]
        with self.workers_run_at_once():
            self.run_card(returns(1), lambda labels, kw: (cardedit.VARIANT_KEY, labels.index("Ruby.zip")), look,
                          self.same_as_fresh)
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Zelda.zip")], "gb": [g("gb/Red.gb")]})
        self.assertEqual(seen, [self.fresh(count=False)[0]])  # the games list counted Red and the Game Boy BIOS too


DISCS = ["psx/A (USA).m3u", "psx/A (USA) (Disc 1).chd", "psx/A (USA) (Disc 2).chd", "psx/A (USA) (Disc 3).chd"]


class VitaFlow(Flow):
    """A Vita game's DLC and update are not rows: the game is marked and syncs them with it."""

    def setUp(self):
        super().setUp()
        self.files["psvita/"] = {G: 10, DLC: 1, NEW: 2, H: 5}
        vita = {"name": "Sony PlayStation Vita", "bucket": "psvita", "folders": {"esde": "psvita"}, "bios": {"files": []}}
        catalog = {**CATALOG, "systems": CATALOG["systems"] + [vita]}
        p = mock.patch.object(store, "repo_json", lambda name: catalog[name])
        p.start()
        self.addCleanup(p.stop)

    def test_only_games_are_rows_and_a_game_with_extras_is_marked(self):
        self.card()
        _, calls = self.run_system(returns([False, False]), bucket="psvita")
        _, labels, kw = calls[0]
        self.assertEqual(labels, [G.split("/", 1)[1], H.split("/", 1)[1]])
        self.assertEqual(kw["extras"][0][0], ("  🔗 3 files", "dim"))
        self.assertFalse(any("🔗" in text for text, _ in kw["extras"][1]))

    def test_picking_a_game_saves_only_the_game(self):
        self.card()
        self.run_system(toggle(G.split("/", 1)[1]), bucket="psvita")
        self.assertEqual(store.card_games("c")["psvita"], [g(G)])


class DiscFlow(Flow):
    """A multi-disc game's playlist and discs are switched on and off together, each saved as its own entry."""

    def setUp(self):
        super().setUp()
        self.files["psx/"] = {k: 10 for k in DISCS + ["psx/B (USA).chd"]}

    def psx(self, *steps):
        return self.run_system(*steps, bucket="psx")

    def test_the_playlist_is_the_games_only_row(self):
        self.card()
        _, calls = self.psx(returns([False, False]))
        _, labels, kw = calls[0]
        self.assertEqual(labels, ["A (USA).m3u", "B (USA).chd"])
        self.assertEqual(kw["extras"][0][0], ("  🔗 4 files", "dim"))

    def test_discs_without_a_playlist_in_storage_are_rows(self):
        self.files["psx/"] = {k: 10 for k in DISCS[1:] + ["psx/B (USA).chd"]}
        self.card()
        _, calls = self.psx(returns([False] * 4))
        _, labels, kw = calls[0]
        self.assertEqual(labels, ["A (USA) (Disc 1).chd", "A (USA) (Disc 2).chd", "A (USA) (Disc 3).chd", "B (USA).chd"])
        self.assertEqual(kw["links"], [[0, 1, 2]] * 3 + [[]])

    def test_toggling_the_playlist_adds_every_disc_and_untoggling_removes_them(self):
        self.card()
        self.psx(toggle("A (USA).m3u"))
        self.assertEqual(sorted(store.card_games("c")["psx"], key=lambda x: x["bucket"]),
                         sorted((g(k) for k in DISCS), key=lambda x: x["bucket"]))
        self.psx(toggle("A (USA).m3u"))
        self.assertEqual(store.card_games("c"), {})

    def test_status_counts_the_whole_game(self):
        self.card()

        def step(labels, kw):
            state = [True, False]  # the playlist switched on
            self.assertEqual(counted(kw, state), 4)
            return state
        self.psx(step)

    def test_a_partial_pick_is_kept_until_the_playlist_is_toggled(self):
        self.card(games={"psx": [g(DISCS[1])]})
        self.psx(returns([False, False]))
        self.assertEqual(store.card_games("c"), {"psx": [g(DISCS[1])]})
        self.psx(toggle("A (USA).m3u"))  # the playlist on: the whole game is on
        self.assertEqual(sorted(x["bucket"] for x in store.card_games("c")["psx"]), sorted(DISCS))

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
        return feed_list(keys, "t", labels, multi=True, initial=initial, links=links, locked=locked)

    def test_space_switches_linked_rows_to_the_new_state(self):
        links = [[0, 2], [], [0, 2]]
        self.assertEqual(self.run_keys(["space", "enter"], ["a", "b", "c"], links), [True, False, True])
        self.assertEqual(self.run_keys(["j", "j", "space", "enter"], ["a", "b", "c"], links, initial=[True, False, False]),
                         [True, False, True])  # partial: the toggled row's new state wins

    def test_toggle_all_reaches_rows_hidden_by_the_filter(self):
        links = [[0, 2], [], [0, 2]]
        self.assertEqual(self.run_keys(["/", "a", "enter", "a", "enter"], ["a", "b", "c"], links), [True, False, True])

    def test_no_links_toggles_one_row(self):
        self.assertEqual(self.run_keys(["space", "enter"], ["a", "b"], None), [True, False])


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
        filters = [c[2].get("filters", "") for c in calls]
        self.assertEqual("genre: Platform (c clear filters)", filters[3])
        self.assertEqual("genre: Platform · year: 2001 (c clear filters)", filters[6])
        self.assertEqual("📦 Pokemon only · genre: Platform · year: 2001 (c clear filters)", filters[8])
        self.assertEqual("", filters[9])
        self.assertNotIn("genre", calls[8][0])
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


class SetFlow(Flow):
    """A set's games over every system the card can play, in one list."""

    def run_set(self, *steps, game_set=SET, device=DEVICE, to_fetch=None):
        script = Script(*steps)
        with mock.patch.object(picker, "filter_list", script), contextlib.redirect_stdout(io.StringIO()):
            changed = cardedit.edit_set("c", game_set, (device, "esde"), to_fetch)
        return changed, script.calls

    def test_set_view_keys_are_the_playable_games_once_in_file_order(self):
        game_set = {"games": [*SET["games"], {"system": "psx", "bucket": "psx/X.chd"}, {"system": "gb", "bucket": "gb/Red.gb"}]}
        self.assertEqual(cardedit.set_view_keys(game_set, [GB, GBA]),
                         [(GBA, "gba/Ruby.zip", ["gba/Ruby.sav"]), (GB, "gb/Red.gb", [])])

    def test_lists_the_sets_games_from_every_system(self):
        self.card()
        _, calls = self.run_set(returns([False, False]))
        title, labels, kw = calls[0]
        self.assertEqual(labels, ["Game Boy — Red", "Game Boy Advance — Ruby"])
        self.assertEqual(title, "📦 Pokemon on c — ✅ synced, ⬜ not, 📦 from a set")
        self.assertEqual(kw["initial"], [False, False])

    def test_toggling_a_game_with_files_picks_its_files_too(self):
        self.card()
        changed, _ = self.run_set(toggle("Game Boy Advance — Ruby"))
        self.assertTrue(changed)
        games = store.card_games("c")
        self.assertEqual({x["bucket"] for x in games["gba"]}, {"gba/Ruby.zip", "gba/Ruby.sav"})
        self.assertNotIn("gb", games)

    def test_switching_off_a_set_reference_game_excludes_it(self):
        self.card(games={store.SETS_KEY: ["pk"]})

        def step(labels, kw):
            self.assertTrue(kw["initial"][0])
            return toggle("Game Boy — Red")(labels, kw)
        self.run_set(step)
        self.assertEqual(store.card_excluded("c"), {"gb": ["gb/Red.gb"]})

    def test_full_system_rows_are_locked_on(self):
        self.card(games={"gb": {"full_system": True}})

        def step(labels, kw):
            self.assertTrue(kw["locked"][0])
            self.assertTrue(kw["initial"][0])
            self.assertEqual(kw["locked_note"][0], edit.FULL_SYSTEM_NOTE)
            return flip(0)(labels, kw)
        self.assertFalse(self.run_set(step)[0])
        self.assertEqual(store.card_games("c"), {"gb": {"full_system": True}})

    def test_games_not_in_storage_or_unplayable_are_hidden(self):
        self.card()
        game_set = {**SET, "games": [*SET["games"], {"system": "psx", "bucket": "psx/X.chd"},
                                     {"system": "gba", "bucket": "gba/Gone.zip"}]}
        _, calls = self.run_set(returns([False, False]), game_set=game_set)
        self.assertEqual(calls[0][1], ["Game Boy — Red", "Game Boy Advance — Ruby"])

    def test_ctrl_c_keeps_the_toggles(self):
        self.card()

        def interrupted(labels, kw):
            kw["session"]["sel"] = [False, True]
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.run_set(interrupted)
        self.assertIn("gba/Ruby.zip", {x["bucket"] for x in self.read("cards.json")["c"]["games"]["gba"]})

    def test_ctrl_c_in_the_series_list_saves_what_was_toggled(self):
        self.card()
        game_set = {**SET, "games": [{**x, "series": "A"} for x in SET["games"]]}

        def red_on_then_series(labels, kw):
            kw["session"]["sel"][labels.index("Game Boy — Red")] = True
            return (cardedit.SERIES_KEY, None)

        def interrupted(labels, kw):
            self.assertEqual(labels, ["A  (2 games)"])
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.run_set(red_on_then_series, interrupted, game_set=game_set)
        self.assertEqual(store.card_games("c"), {"gb": [g("gb/Red.gb")]})

    def run_series(self, game_set, pick, *steps):
        """Drives edit_set; the series list (no multi mode) answers with the index pick, and its labels are kept."""
        script, lists = Script(*steps), []

        def fake(title, labels, **kw):
            if "multi" in kw:
                return script(title, labels, **kw)
            lists.append(list(labels))
            return pick
        with mock.patch.object(picker, "filter_list", fake), contextlib.redirect_stdout(io.StringIO()):
            cardedit.edit_set("c", game_set, (DEVICE, "esde"))
        return script.calls, lists

    def test_series_key_filters_the_rows_and_c_shows_all(self):
        self.files["gb/"]["gb/Blue.gb"] = 5
        self.card()
        game_set = {**SET, "games": [{**SET["games"][0], "series": "Gen 1"}, {**SET["games"][1], "series": "Gen 1"},
                                     {"system": "gb", "bucket": "gb/Blue.gb", "series": "Other"}]}
        keys = (cardedit.VARIANT_KEY, cardedit.SERIES_KEY, cardedit.CLEAR_KEY)
        calls, lists = self.run_series(
            game_set, 0, returns((cardedit.SERIES_KEY, None)), returns((cardedit.CLEAR_KEY, None)), lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(lists, [["Gen 1  (2 games)"]])  # "Other" has one game: left out
        self.assertEqual(calls[0][2]["hotkeys"], keys)
        self.assertEqual(calls[0][2]["filters"], "")
        self.assertEqual(calls[1][2]["filters"], "Gen 1 (c clear filters)")
        self.assertEqual(calls[1][1], ["Game Boy — Red", "Game Boy Advance — Ruby"])
        self.assertEqual(calls[2][2]["filters"], "")

    def test_series_key_filters_to_the_picked_series(self):
        self.files["gb/"]["gb/Blue.gb"] = 5
        self.card()
        game_set = {**SET, "games": [{**SET["games"][0], "series": "A"}, {**SET["games"][1], "series": "B"},
                                     {"system": "gb", "bucket": "gb/Blue.gb", "series": "B"}]}
        calls, _ = self.run_series(game_set, 0, returns((cardedit.SERIES_KEY, None)), lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(calls[1][1], ["Game Boy — Blue", "Game Boy — Red"])
        self.assertEqual(len(calls[1][2]["initial"]), 2)

    def test_series_key_applies_toggles_made_before_it(self):
        self.card()
        game_set = {**SET, "games": [{**SET["games"][0], "series": "A"}, {**SET["games"][1], "series": "A"}]}

        def toggles_then_series(labels, kw):
            kw["session"]["sel"][labels.index("Game Boy Advance — Ruby")] = True
            return (cardedit.SERIES_KEY, None)
        self.run_series(game_set, 0, toggles_then_series, lambda labels, kw: kw["session"]["sel"])
        self.assertIn("gba/Ruby.zip", {x["bucket"] for x in store.card_games("c")["gba"]})

    def test_series_key_without_series_notes_and_lists_again(self):
        self.card()
        notes = []
        with mock.patch.object(edit, "note", notes.append):
            calls, lists = self.run_series(SET, 0, returns((cardedit.SERIES_KEY, None)), lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(lists, [])
        self.assertEqual(len(notes), 1)
        self.assertEqual(calls[1][1], calls[0][1])

    def test_no_select_all(self):
        self.card()
        _, calls = self.run_set(returns([False, False]))
        self.assertIs(calls[0][2]["select_all"], False)

    def test_status_counts_picked_games_and_their_bios(self):
        self.card()
        self.cache = {"gba/": self.files["gba/"], "gb/": self.files["gb/"], "scrapes/gba/": {}, "scrapes/gb/": {},
                      "BIOS/": {"BIOS/gb_bios.bin": 1000, "BIOS/gba_bios.bin": 16}}
        seen = []

        def step(labels, kw):
            kw["status"]([False, False])
            kw["status"]([False, True])  # Ruby (5 + 1) and the GBA BIOS (16)
            return [False, False]
        with mock.patch.object(cardedit, "status_of", side_effect=lambda u, c, fetch=None, count=True: seen.append((u.bytes, count))):
            self.run_set(step)
        self.assertEqual(seen, [(0, False), (22, False)])

    def test_a_multi_disc_game_switches_all_its_discs(self):
        self.files["psx/"] = {k: 10 for k in DISCS[1:3]}  # two discs, no playlist
        discs = {"id": "md", "name": "Discs", "description": "", "games": [
            {"system": "psx", "bucket": DISCS[1]}, {"system": "psx", "bucket": DISCS[2]}]}
        self.card()

        def step(labels, kw):
            self.assertEqual(labels, ["PlayStation — A (USA) (Disc 1)", "PlayStation — A (USA) (Disc 2)"])
            self.assertEqual(kw["links"], [[0, 1], [0, 1]])
            return [True, False]  # one row on: the whole game is
        self.run_set(step, game_set=discs, device=PSX_DEVICE)
        self.assertEqual(sorted(x["bucket"] for x in store.card_games("c")["psx"]), DISCS[1:3])

    def test_a_playlist_in_the_set_hides_its_discs(self):
        self.files["psx/"] = {k: 10 for k in DISCS[:3]}
        playlist = {"id": "pl", "name": "Playlist", "description": "", "games": [
            {"system": "psx", "bucket": DISCS[0]}, {"system": "psx", "bucket": DISCS[1]}]}
        self.card()

        def step(labels, kw):
            self.assertEqual(labels, ["PlayStation — A (USA)"])
            return [True]
        self.run_set(step, game_set=playlist, device=PSX_DEVICE)
        self.assertEqual(sorted(x["bucket"] for x in store.card_games("c")["psx"]), sorted(DISCS[:3]))

    def test_status_counts_what_is_not_on_the_card_yet_to_download(self):
        self.card()
        self.cache = {"gba/": self.files["gba/"], "gb/": self.files["gb/"], "scrapes/gba/": {}, "scrapes/gb/": {},
                      "BIOS/": {}}
        on_card = {"gba/Ruby.zip", "gba/Ruby.sav"}
        seen = []

        def step(labels, kw):
            kw["status"]([False, False])
            kw["status"]([True, True])  # Red (2) to download; Ruby is on the card
            return [False, False]
        with mock.patch.object(cardedit, "status_of", side_effect=lambda u, c, fetch=None, count=True: seen.append(fetch)):
            self.run_set(step, to_fetch=lambda s, keys: {k for k in keys if k not in on_card})
        self.assertEqual(seen, [0, 2])

    def test_w_saves_a_picked_games_note(self):
        self.card(games={"gba": [g("gba/Ruby.zip"), g("gba/Ruby.sav")]})

        def step(labels, kw):
            self.assertEqual(kw["on_note"](labels.index("Game Boy — Red"), "x"),
                             "Switch the game on and press Enter first, then add its note")
            self.assertEqual(kw["on_note"](labels.index("Game Boy Advance — Ruby"), "best one"), "Note saved")
            self.assertEqual(kw["note_text"](labels.index("Game Boy Advance — Ruby")), "best one")
            return kw["session"]["sel"]
        self.assertTrue(self.run_set(step)[0])
        self.assertEqual(self.read("cards.json")["c"]["games"]["gba"],
                         [{**g("gba/Ruby.sav")}, {**g("gba/Ruby.zip"), "note": "best one"}])

    def test_v_adds_the_variant_to_the_card(self):
        vset = {**SET, "games": [{**SET["games"][0], "variants": [{"bucket": "gba/Emerald.zip", "note": "more"}]},
                                 SET["games"][1]]}
        self.card()

        def press_v(labels, kw):
            return (cardedit.VARIANT_KEY, labels.index("Game Boy Advance — Ruby"))

        def now_on(labels, kw):
            self.assertTrue(kw["row_note"](labels.index("Game Boy Advance — Ruby")).endswith("✅ on the card (v removes it)"))
            return kw["session"]["sel"]
        with mock.patch.object(store, "load_sets", return_value=[vset]):
            changed, _ = self.run_set(press_v, now_on, game_set=vset)
        self.assertTrue(changed)
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Emerald.zip")]})

    def test_v_counts_a_variant_on_a_system_the_set_has_no_games_of(self):
        self.with_variants(self.RED)
        self.card(size="1 GB", games={"gba": [g("gba/Zelda.zip")]})
        self.sized()
        seen = []

        def look(labels, kw):
            seen.append(kw["status"](kw["session"]["sel"]))
            return kw["session"]["sel"]
        with self.workers_run_at_once():
            self.run_card(returns((cardedit.SET_KEY, 0)),
                          lambda labels, kw: next(i for i, l in enumerate(labels) if "Variants" in l),
                          lambda labels, kw: (cardedit.VARIANT_KEY, labels.index("Game Boy Advance — Ruby")), look,
                          self.same_as_fresh)
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Zelda.zip")], "gb": [g("gb/Red.gb")]})
        self.assertEqual(seen, [self.fresh(count=False)[0]])

    def test_one_pass_changes_two_systems(self):
        self.card(games={"gba": [g("gba/Zelda.zip")], store.SETS_KEY: ["pk"]}, excluded={"gba": ["gba/Ruby.zip"]})

        def step(labels, kw):
            self.assertEqual(kw["initial"], [True, False])
            return toggle("Game Boy — Red", "Game Boy Advance — Ruby")(labels, kw)
        self.assertTrue(self.run_set(step)[0])
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Zelda.zip")], store.SETS_KEY: ["pk"]})
        self.assertEqual(store.card_excluded("c"), {"gb": ["gb/Red.gb"]})

    def test_a_vita_dlc_in_the_set_is_not_a_row(self):
        self.files["psvita/"] = {G: 10, DLC: 1}
        vita = {"name": "Sony PlayStation Vita", "bucket": "psvita", "folders": {"esde": "psvita"}, "bios": {"files": []}}
        catalog = {**CATALOG, "systems": CATALOG["systems"] + [vita]}
        game_set = {"id": "v", "name": "Vita", "description": "", "games": [
            {"system": "psvita", "bucket": G}, {"system": "psvita", "bucket": DLC}]}
        self.card()
        with mock.patch.object(store, "repo_json", lambda name: catalog[name]):
            _, calls = self.run_set(returns([True]), game_set=game_set, device={**DEVICE, "systems": ["psvita"]})
        self.assertEqual(calls[0][1], ["Sony PlayStation Vita — G [PCSE00349] [USA] [NoNpDRM]"])
        self.assertEqual(store.card_games("c"), {"psvita": [g(G)]})

    def test_the_set_list_lists_only_systems_with_set_games(self):
        self.card()
        listed = []

        def files(prefix, sizes=True):
            listed.append(prefix)
            return self.files.get(prefix, {})
        out = io.StringIO()
        with mock.patch.object(inventory, "current", return_value=None), mock.patch.object(inventory, "files", files), \
                mock.patch.object(picker, "filter_list", Script(returns(None))), contextlib.redirect_stdout(out):
            cardedit.pick_card_set("c", (DEVICE, "esde"), [GBA, GB, PSX])
        self.assertEqual(sorted(listed), ["gb/", "gba/"])  # no Pokemon game on PSX
        self.assertEqual(out.getvalue().count("📡 Listing"), 2, out.getvalue())

    def run_all(self, *steps, systems=(GBA, GB)):
        script = Script(*steps)
        with mock.patch.object(picker, "filter_list", script), contextlib.redirect_stdout(io.StringIO()):
            changed = cardedit.edit_all("c", (DEVICE, "esde"), list(systems))
        return changed, script.calls

    ALL_LABELS = ["Game Boy Advance — Emerald.zip", "Game Boy — Red.gb", "Game Boy Advance — Ruby.sav",
                  "Game Boy Advance — Ruby.zip", "Game Boy Advance — Zelda.zip"]

    def test_edit_all_lists_every_file_of_every_system_with_system_names(self):
        self.card()
        _, calls = self.run_all(lambda labels, kw: kw["session"]["sel"])
        title, labels, kw = calls[0]
        self.assertEqual(labels, self.ALL_LABELS)
        self.assertEqual(title, "🌐 All games on c — ✅ synced, ⬜ not, 📦 from a set")
        self.assertEqual(kw["hotkeys"], (cardedit.VARIANT_KEY, cardedit.SET_KEY, cardedit.CLEAR_KEY))
        self.assertIs(kw["select_all"], False)

    def test_edit_all_toggle_saves_picks_on_the_right_system(self):
        self.card()
        changed, _ = self.run_all(toggle("Game Boy — Red.gb", "Game Boy Advance — Zelda.zip"))
        self.assertTrue(changed)
        games = store.card_games("c")
        self.assertEqual([x["bucket"] for x in games["gb"]], ["gb/Red.gb"])
        self.assertEqual([x["bucket"] for x in games["gba"]], ["gba/Zelda.zip"])

    def test_edit_all_lists_a_full_system_locked_on(self):
        self.card(games={"gb": {"full_system": True}})

        def step(labels, kw):
            i = labels.index("Game Boy — Red.gb")
            self.assertTrue(kw["locked"][i])
            self.assertTrue(kw["initial"][i])
            self.assertFalse(kw["locked"][labels.index("Game Boy Advance — Zelda.zip")])
            return kw["session"]["sel"]
        self.assertFalse(self.run_all(step)[0])
        self.assertEqual(store.card_games("c"), {"gb": {"full_system": True}})

    def test_edit_all_sorts_by_title_then_system(self):
        self.files["gb/"]["gb/Zelda.gb"] = 4
        self.card()
        _, calls = self.run_all(lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(calls[0][1], ["Game Boy Advance — Emerald.zip", "Game Boy — Red.gb", "Game Boy Advance — Ruby.sav",
                                       "Game Boy Advance — Ruby.zip", "Game Boy — Zelda.gb", "Game Boy Advance — Zelda.zip"])

    def test_edit_all_set_key_narrows_to_a_set_then_c_clears(self):
        self.card()
        _, calls = self.run_all(returns((cardedit.SET_KEY, None)), returns(0), returns((cardedit.CLEAR_KEY, None)),
                                lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(calls[1][1], [f"{themeart.set_emoji(SET)} Pokemon  (3 games)"])  # the set list
        self.assertEqual(calls[2][1], ["Game Boy — Red.gb", "Game Boy Advance — Ruby.sav", "Game Boy Advance — Ruby.zip"])
        self.assertEqual(calls[2][2]["filters"], f"{themeart.set_emoji(SET)} Pokemon only (c clear filters)")
        self.assertEqual(calls[3][1], self.ALL_LABELS)
        self.assertEqual(calls[3][2]["filters"], "")

    def test_edit_all_notes_a_storage_error_and_changes_nothing(self):
        self.card()
        notes = []
        with mock.patch.object(store, "folder_keys", side_effect=OSError("down")), \
                mock.patch.object(edit, "note", notes.append):
            changed, calls = self.run_all()
        self.assertIs(changed, False)
        self.assertEqual(calls, [])
        self.assertEqual(len(notes), 1)
        self.assertIn("Couldn't list Game Boy Advance in storage: down", notes[0])

    def test_edit_all_lists_each_folder_once(self):
        self.card(games={"gb": {"full_system": True}})
        listed = []
        real = store.folder_keys

        def counting(bucket, say=True):
            listed.append(bucket)
            return real(bucket, say)
        with mock.patch.object(store, "folder_keys", counting):
            self.run_all(lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(sorted(listed), ["gb", "gba"])

    def test_edit_card_a_opens_the_all_games_view(self):
        self.card()
        with mock.patch.object(cardedit, "edit_all", return_value=False) as opened:
            calls = self.run_card(returns((cardedit.ALL_KEY, 0)), returns(None))
        self.assertEqual(len(calls), 2)
        self.assertIn(cardedit.ALL_KEY, calls[0][2]["hotkeys"])
        self.assertEqual(opened.call_args[0][:2], ("c", (DEVICE, "esde")))
        self.assertEqual({s["bucket"] for s in opened.call_args[0][2]}, {"gba", "gb"})
        self.assertIn(("a", "every game across this card's systems"), cardedit.LIST_KEYS)
        self.assertIn("a all", cardedit.LIST_HINT)


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

    def test_the_review_lists_the_first_dropped_games_and_counts_the_rest(self):
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde",
                                             "games": {"gb": [g(f"gb/{n}.gb") for n in "ABCDEFG"]}}})
        picks = iter([0, (edit.SETUP_KEY, 0), None, 4])  # Cards, v on the card, back, Done
        out = io.StringIO()
        with mock.patch.object(store, "repo_json", side_effect=lambda name: [dict(s) for s in CATALOG[name]]), \
                mock.patch.object(store, "load_manifest", return_value=CATALOG), \
                mock.patch.object(store, "load_sets", return_value=[]), \
                mock.patch.object(picker, "filter_list", side_effect=lambda *a, **k: next(picks)), \
                mock.patch.object(picker, "choose_setup", return_value=({**DEVICE, "systems": ["gba"]}, "esde")), \
                mock.patch.object(ui, "choose", return_value="d"), \
                contextlib.redirect_stdout(out):
            self.assertEqual(edit.edit_manifest(), 0)
        lines = out.getvalue().splitlines()
        at = lines.index("  ➖ gb: 7 removed")
        self.assertEqual(lines[at + 1:at + 7], [f"       {n}.gb" for n in "ABCDE"] + ["       … and 2 more"])


class GamesStatus(unittest.TestCase):
    def test_the_games_list_status_leaves_room_for_the_row_at_80_columns(self):
        rows = []

        async def script(pilot):
            rows.append(" ".join(t for t, _ in screen_lines(pilot.app)[-1]))
            await pilot.press("escape")

        def bottom(fetch, games=812, cursor=9):
            rows.clear()
            status = cardedit.status_of(U(123_400_000_000, 1234, False), 512 * 10 ** 9, fetch, count=False)
            pilot_list(script, "t", [f"Game {i}" for i in range(games)], multi=True, esc_asks=False, cursor=cursor,
                       status=lambda _s: status)
            return rows[0]
        row = bottom(None)
        self.assertTrue(row.startswith("+0 −0 · 💾 123.4 GB / 512 GB · 388.6 GB free · view: all "), row)
        self.assertTrue(row.endswith(" row 10 · 812/812 shown"), row)
        row = bottom(None, games=3700, cursor=2039)  # the full form doesn't fit: the same numbers without words
        self.assertTrue(row.startswith("+0 −0 · 💾 123.4 GB / 512 GB · 388.6 GB free · view: all "), row)
        self.assertTrue(row.endswith(" 2040 · 3700/3700"), row)
        self.assertNotIn("row", row)
        row = bottom(12_300_000_000, games=3700, cursor=2039)  # opened from a sync: no room, the row gives way (and the status is cut)
        self.assertTrue(row.startswith("+0 −0 · 💾 123.4 GB / 512 GB · 388.6 GB free · ⬇️  12.3 GB to download"), row)
        self.assertNotIn("row", row)
        self.assertNotIn("3700", row)


class Poll(unittest.TestCase):
    def test_filter_list_polls_while_idle_and_colors_the_status(self):
        polled, status = [], []

        async def script(pilot):
            await pilot.pause(picker.POLL_MS * 2 / 1000)
            status.extend(screen_lines(pilot.app)[-1])
            await pilot.press("enter")
        self.assertEqual(pilot_list(script, "t", ["a"], poll=lambda: polled.append(1),
                                    status=lambda s: ("over", "red")), 0)
        self.assertTrue(polled)
        self.assertEqual(status[0], ("over", "bold color(1) on default"))
        self.assertTrue(status[-1][0].endswith("row 1 · 1/1 shown"))


if __name__ == "__main__":
    unittest.main()


class GameFiltersTest(unittest.TestCase):
    GBA = {"bucket": "gba", "name": "Game Boy Advance"}
    KEYS = ["gba/A.zip", "gba/B.zip", "gba/C.zip"]

    def filters(self):
        with mock.patch.object(cardedit, "_spawn", lambda fn: None), mock.patch.object(cardedit, "_metadata", {"gba": None}):
            return cardedit.GameFilters(self.GBA)

    def test_nothing_narrows_the_list_at_first(self):
        f = self.filters()
        self.assertTrue(all(f.keep(k) for k in self.KEYS))
        self.assertEqual(f.describe(), "")

    def test_a_set_narrows_the_list_and_c_clears_every_filter(self):
        f = self.filters()
        game_set = {"name": "Picks", "games": [{"system": "gba", "bucket": "gba/A.zip"}]}
        current = []
        self.assertTrue(f.handle(cardedit.SET_KEY, self.KEYS, {}, lambda name: current.append(name) or game_set))
        self.assertEqual([k for k in self.KEYS if f.keep(k)], ["gba/A.zip"])
        self.assertIn("Picks only", f.describe())
        self.assertTrue(f.describe().endswith("(c clear filters)"))
        f.handle(cardedit.SET_KEY, self.KEYS, {}, lambda name: current.append(name))  # cancelled: the set stays
        self.assertEqual(current, [None, "Picks"])
        self.assertEqual([k for k in self.KEYS if f.keep(k)], ["gba/A.zip"])
        with mock.patch.object(surprise, "past_keys", return_value={"gba/B.zip"}):
            f.handle(cardedit.PAST_SURPRISE_KEY, self.KEYS, {}, None)
        self.assertEqual([k for k in self.KEYS if f.keep(k)], [])
        self.assertIn("past surprises only", f.describe())
        place = {"session": {"query": "zel"}}
        self.assertTrue(f.handle(cardedit.CLEAR_KEY, self.KEYS, place, None))
        self.assertEqual(place, {"session": {}})  # the / filter too
        self.assertTrue(all(f.keep(k) for k in self.KEYS))
        self.assertEqual(f.describe(), "")

    def test_no_past_surprises_leaves_the_list_and_says_so(self):
        f, notes = self.filters(), []
        with mock.patch.object(surprise, "past_keys", return_value=set()), mock.patch.object(edit, "note", notes.append):
            self.assertTrue(f.handle(cardedit.PAST_SURPRISE_KEY, self.KEYS, {}, None))
        self.assertIsNone(f.past)
        self.assertIn("No past surprises on Game Boy Advance", notes[0])

    def test_m_offers_the_keys_the_other_filters_keep(self):
        f, offered = self.filters(), []
        f.past = {"gba/B.zip", "gba/C.zip"}

        def pick_meta(system, meta, meta_filt, keys):
            offered.append(keys("genre"))
        with mock.patch.object(cardedit, "pick_meta", pick_meta):
            self.assertTrue(f.handle(cardedit.META_KEY, self.KEYS, {}, None))
        self.assertEqual(offered, [["gba/B.zip", "gba/C.zip"]])

    def test_other_keys_are_not_filter_keys(self):
        f = self.filters()
        for pressed in (None, cardedit.VARIANT_KEY):
            self.assertFalse(f.handle(pressed, self.KEYS, {}, None))
