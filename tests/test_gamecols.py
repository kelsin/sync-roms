import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import gamecols, gamemeta, picker, store  # noqa: E402

SYSTEMS = [{"bucket": "snes", "name": "Super Nintendo", "short": "SNES"}, {"bucket": "gba", "name": "Game Boy Advance"}]


def meta(indexes):
    """Patch gamemeta.Metadata.get: indexes is a dict (bucket -> index) or a callable returning one."""
    def get(self):
        found = indexes() if callable(indexes) else indexes
        return found.get(self.bucket, None) if found is not None else gamemeta.LOADING
    return get


class GameColumnsTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.object(store, "repo_json", lambda name: SYSTEMS))
        self.enterContext(mock.patch.object(gamemeta, "_spawn", lambda fn: None))

    def test_columns_and_cells(self):
        index = {"snes": {"snes/A.sfc": {"year": {"1994"}}}, "gba": {}}
        with mock.patch.object(gamemeta.Metadata, "get", meta(index)):
            cols = gamecols.GameColumns([("snes", "A", "snes/A.sfc"), ("gba", "B", "gba/B.gba")])
            kw = cols.kwargs()
        self.assertEqual([c.id for c in kw["columns"]], ["name", "system", "year"])
        self.assertEqual(kw["extras"][0], [("  SNES", "dim"), ("  1994", "dim")])
        self.assertEqual(kw["extras"][1], [("  Game Boy Advance", "dim"), ("  —", "dim")])
        self.assertIs(kw["sort"], picker.GAMES_SORT)
        self.assertEqual(kw["sort_value"](0, "system"), "snes")
        self.assertEqual(kw["sort_value"](0, "name"), store.sort_key("A"))
        self.assertEqual(kw["sort_value"](1, "year"), None)

    def test_years_fill_in_on_poll(self):
        state = {"index": None}
        with mock.patch.object(gamemeta.Metadata, "get", meta(lambda: state["index"])):
            cols = gamecols.GameColumns([("snes", "A", "snes/A.sfc")])
            kw = cols.kwargs()
            self.assertEqual(kw["extras"][0][1], ("  —", "dim"))
            kw["poll"]()
            self.assertEqual(kw["extras"][0][1], ("  —", "dim"))
            state["index"] = {"snes": {"snes/A.sfc": {"year": {"1994"}}}}
            kw["poll"]()
        self.assertEqual(kw["extras"][0][1], ("  1994", "dim"))
        self.assertEqual(kw["sort_value"](0, "year"), "1994")

    def test_stem_year_for_saves(self):
        year = lambda y: {"year": {y}}  # noqa: E731
        index = {"snes": {"snes/Chrono Trigger (USA).sfc": year("1995")}}
        with mock.patch.object(gamemeta.Metadata, "get", meta(index)):
            cols = gamecols.GameColumns([("snes", "Chrono Trigger (USA)", None)])
            self.assertEqual(cols.kwargs()["extras"][0][1], ("  1995", "dim"))
        index = {"snes": {"snes/Chrono Trigger (USA).sfc": year("1995"), "snes/sub/Chrono Trigger (USA).smc": year("1996")}}
        with mock.patch.object(gamemeta.Metadata, "get", meta(index)):
            cols = gamecols.GameColumns([("snes", "Chrono Trigger (USA)", None)])
            self.assertEqual(cols.kwargs()["extras"][0][1], ("  —", "dim"))

    def test_caller_poll_and_extras_kept(self):
        calls = []
        extra = [[("  1 MB", "green")]]
        with mock.patch.object(gamemeta.Metadata, "get", meta({"snes": {}})):
            cols = gamecols.GameColumns([("snes", "A", "snes/A.sfc")], [picker.Column("size", "Size", True)],
                                        extra_values=lambda i, c: 7)
            kw = cols.kwargs(extra, lambda: calls.append(1))
            kw["poll"]()
            self.assertEqual(kw["columns"][-1].id, "size")
            self.assertEqual(kw["extras"][0][2:], [("  1 MB", "green")])
            self.assertEqual(kw["sort_value"](0, "size"), 7)
            self.assertEqual(calls, [1])
            kw["poll"]()
            self.assertEqual(calls, [1, 1])


if __name__ == "__main__":
    unittest.main()
