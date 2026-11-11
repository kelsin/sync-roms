import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from helpers import DataDir  # noqa: E402
from sync_roms import budget, cardedit, edit, picker, s3, sizecache, store, ui  # noqa: E402

U = budget.Usage


def system(bucket, name, bios=()):
    return {"bucket": bucket, "name": name, "folders": {"esde": bucket}, "bios": {"files": list(bios)}}


GBA, GB, PSX = system("gba", "Game Boy Advance", ["gba_bios.bin"]), system("gb", "Game Boy", ["gb_bios.bin"]), system("psx", "PlayStation")
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
                         ("💾 1.5 GB / 512 GB · 510.5 GB free · 3 game(s)", False))
        text, over = cardedit.header(U(600 * 10 ** 9, 9, False), 512 * 10 ** 9)
        self.assertTrue(over)
        self.assertIn("88 GB over", text)
        self.assertEqual(cardedit.header(U(10 ** 9, 1, False), None), ("💾 1 GB used · 1 game(s)", False))
        text, over = cardedit.header(U(10 ** 9, 1, True), None)
        self.assertTrue(text.endswith("… still sizing"))
        self.assertFalse(over)

    def test_status_is_red_when_over(self):
        self.assertEqual(cardedit.status_of(U(2, 0, False), 1)[1], "red")
        self.assertIsInstance(cardedit.status_of(U(1, 0, False), 2), str)

    def test_system_labels(self):
        card = {"games": {"psx": {"full_system": True}}}
        usages = {"gba": U(2 * 10 ** 9, 4, False), "gb": U(0, 0, False), "psx": U(0, 0, True)}
        labels, extras = cardedit.system_labels(card, [GBA, GB, PSX], {"gb"}, usages)
        self.assertEqual([l.strip() for l in labels], ["Game Boy Advance", "⭐ Game Boy", "PlayStation"])  # file order
        self.assertTrue(labels[1].startswith("⭐ "))
        self.assertEqual(extras[0], [("  4 picked", "green"), ("  2 GB", "dim")])
        self.assertEqual(extras[1], [("  recommended", "cyan")])
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
        return next(self.steps)(labels, kw)


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


class Flow(DataDir):
    def setUp(self):
        super().setUp()
        self.files = {"gba/": {"gba/Emerald.zip": 3, "gba/Ruby.zip": 5, "gba/Ruby.sav": 1, "gba/Zelda.zip": 7},
                      "gb/": {"gb/Red.gb": 2}}
        self.cache = {}
        self.started = []
        for target, attrs in ((store, {"load_catalog": lambda: CATALOG, "load_sets": lambda: [SET],
                                       "repo_json": lambda name: CATALOG[name],
                                       "recommended_systems": lambda device, systems: set()}),
                              (s3, {"list_sizes": lambda prefix, sizes=True: self.files.get(prefix, {})}),
                              (sizecache, {"cached": lambda p: self.cache.get(p),
                                           "refresh_async": lambda p, done: self.started.append((p, done))}),
                              (edit, {"note": lambda text: None})):
            for name, new in attrs.items():
                p = mock.patch.object(target, name, new)
                p.start()
                self.addCleanup(p.stop)

    def card(self, **entry):
        self.write_json("cards.json", {"c": {"device": "d", "layout": "esde", **entry}})

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

    def test_system_list_is_what_the_device_plays_in_file_order(self):
        self.card(size="1 GB", games={"gba": [g("gba/Ruby.zip")]})
        self.cache = {"gba/": self.files["gba/"], "scrapes/gba/": {}, "BIOS/": {"BIOS/gba_bios.bin": 16}}
        with mock.patch.object(store, "recommended_systems", return_value={"gb"}):
            calls = self.run_card(returns(None))
        title, labels, kw = calls[0]
        self.assertEqual([l.strip() for l in labels], ["Game Boy Advance", "⭐ Game Boy"])
        self.assertEqual(kw["extras"][0], [("  1 picked", "green"), ("  5 B", "dim")])  # the ROM
        self.assertEqual(kw["status"](None), "💾 21 B / 1 GB · 1 GB free · 1 game(s)")  # ROM and the GBA BIOS
        self.assertEqual([p for p, _ in self.started], ["BIOS/"])

    def test_sizes_arrive_in_the_background_and_redraw(self):
        self.card(games={"gba": [g("gba/Ruby.zip")]})

        def step(labels, kw):
            self.assertIn("still sizing", kw["status"](None))
            self.assertEqual(kw["extras"][0][1], ("  …", "dim"))
            self.cache.update({"gba/": self.files["gba/"], "scrapes/gba/": {}, "BIOS/": {}})
            kw["poll"]()  # nothing finished yet: unchanged
            self.assertEqual(kw["extras"][0][1], ("  …", "dim"))
            for _, done in self.started:
                done({})  # what the worker thread calls
            kw["poll"]()
            self.assertEqual(kw["extras"][0][1], ("  5 B", "dim"))
            self.assertEqual(kw["status"](None), "💾 5 B used · 1 game(s)")
            return None
        self.run_card(step)

    def test_full_system_hotkey_saves_and_restores_the_list(self):
        self.card(games={"gba": [g("gba/Ruby.zip")]})
        seen = []

        def look(labels, kw):
            seen.append(store.card_games("c"))
            return (cardedit.FULL_KEY, 0)
        self.run_card(returns((cardedit.FULL_KEY, 0)), look, returns(None))
        self.assertEqual(seen[0], {"gba": {"full_system": True}})
        self.assertEqual(store.card_games("c"), {"gba": [g("gba/Ruby.zip")]})

    def test_entering_a_system_refreshes_its_sizes(self):
        self.card()
        self.run_card(returns(0), returns([False] * 4), returns(None))
        self.assertEqual([p for p, _ in self.started], ["BIOS/", "gba/", "scrapes/gba/"])

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

    def test_set_list_hotkey_syncs_the_full_set(self):
        self.card()

        def refs_on(labels, kw):
            self.assertEqual(kw["extras"], [[("  📦 full set", "green")]])
            return None
        self.run_system(returns((cardedit.SET_KEY, 0)), returns((cardedit.FULL_KEY, 0)), refs_on,
                        lambda labels, kw: kw["session"]["sel"])
        self.assertEqual(store.card_games("c"), {"sets": ["pk"]})

    def test_game_view_status_counts_pending_picks(self):
        self.card(size="1 GB")
        self.cache = {"gba/": self.files["gba/"], "scrapes/gba/": {}, "BIOS/": {"BIOS/gba_bios.bin": 16}, "gb/": {}}

        def step(labels, kw):
            self.assertEqual(kw["status"]([False] * 4), "💾 0 B / 1 GB · 1 GB free · 0 game(s)")
            self.assertEqual(kw["status"]([True, False, False, True]), "💾 26 B / 1 GB · 1 GB free · 2 game(s)")
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
        with mock.patch.object(cardedit, "status_of", side_effect=lambda u, c: seen.append(u.bytes)):
            self.run_system(step)
        self.assertEqual(seen, [1002, 1021])

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
            self.run_system(filtered_pass, returns((cardedit.FULL_KEY, 0)), returns(None), interrupted)
        entry = self.read("cards.json")["c"]  # the first pass, the set reference and the interrupted pass
        self.assertEqual(entry["games"], {"gba": [g("gba/Ruby.zip"), g("gba/Zelda.zip")], "sets": ["pk"]})
        self.assertEqual(entry["excluded"], {"gba": ["gba/Ruby.zip"]})

    def test_full_system_has_no_game_list(self):
        self.card(games={"gba": {"full_system": True}})
        changed, calls = self.run_system()
        self.assertFalse(changed)
        self.assertEqual(calls, [])


class SetupChange(DataDir):
    def test_changing_the_device_drops_games_it_cannot_play_at_save(self):
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde",
                                             "games": {"gba": [g("gba/A.zip")], "gb": [g("gb/B.gb")]}}})
        picks = iter([(edit.SETUP_KEY, 0), 3])  # v on the card, then Done
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


class SizeCacheMemo(DataDir):
    def test_a_rewritten_cache_is_read_again(self):
        with mock.patch.object(s3, "location", return_value="here"):
            self.write_json("sizes.json", {"source": "here", "prefixes": {"gba/": {"built": 1, "files": {"a": 1}}}})
            self.assertEqual(sizecache.cached("gba/"), {"a": 1})
            self.write_json("sizes.json", {"source": "here", "prefixes": {"gba/": {"built": 1, "files": {"a": 22}}}})
            self.assertEqual(sizecache.cached("gba/"), {"a": 22})


if __name__ == "__main__":
    unittest.main()
