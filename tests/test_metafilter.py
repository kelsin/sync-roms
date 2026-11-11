import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import metafilter as mf  # noqa: E402


class Values(unittest.TestCase):
    def test_year_is_the_first_four_digits(self):
        for date in ("1999", "1999-03-04", "19990304", "03/04/1999"):
            self.assertEqual(mf.values({"releasedate": date}), {"year": {"1999"}}, date)
        for date in ("", "unknown", "Unknown", "99", None, 1999):
            self.assertEqual(mf.values({"releasedate": date}), {}, date)

    def test_players_groups_cover_the_range(self):
        self.assertEqual(mf.players("1"), ("1 player",))
        self.assertEqual(mf.players("1-2"), ("1 player", "2 players"))
        self.assertEqual(mf.players("2+"), ("2 players", "3-4 players", "5+ players"))
        self.assertEqual(mf.players("1-4"), ("1 player", "2 players", "3-4 players"))
        self.assertEqual(mf.players("4"), ("3-4 players",))
        self.assertEqual(mf.players("8"), ("5+ players",))
        self.assertEqual(mf.players(""), ())
        self.assertEqual(mf.values({"players": "unknown"}), {})
        self.assertEqual(mf.values({"players": "1-2"}), {"players": {"1 player", "2 players"}})

    def test_genre_is_its_first_segment(self):
        self.assertEqual(mf.values({"genre": "Sports / Baseball"}), {"genre": {"Sports"}})
        self.assertEqual(mf.values({"genre": " Platform "}), {"genre": {"Platform"}})
        self.assertEqual(mf.values({"genre": "Shoot'em Up, Vertical"}), {"genre": {"Shoot'em Up, Vertical"}})
        self.assertEqual(mf.values({"genre": "unknown"}), {})

    def test_developer_and_publisher_are_trimmed(self):
        self.assertEqual(mf.values({"developer": " Nintendo ", "publisher": "Capcom", "name": "x"}),
                         {"developer": {"Nintendo"}, "publisher": {"Capcom"}})
        self.assertEqual(mf.values({"developer": "", "publisher": "  "}), {})
        self.assertEqual(mf.values("not an entry"), {})


IDX = mf.index({"A.zip": {"genre": "Platform", "releasedate": "1999", "players": "1-2"},
                "B.zip": {"genre": "Platform / Run", "releasedate": "2001-01-01", "players": "1"},
                "C.zip": {"genre": "Puzzle", "releasedate": "19990304"},
                "D.zip": {}}, "gba")


class Index(unittest.TestCase):
    def test_keys_are_bucket_keys(self):
        self.assertEqual(sorted(IDX), ["gba/A.zip", "gba/B.zip", "gba/C.zip", "gba/D.zip"])
        self.assertIsNone(mf.index([], "gba"))

    def test_counts_sort_by_count_then_name_and_years_by_year(self):
        keys = list(IDX) + ["gba/None.zip"]
        self.assertEqual(mf.counts(IDX, keys, "genre"), [("Platform", 2), ("Puzzle", 1)])
        self.assertEqual(mf.counts(IDX, keys, "year"), [("1999", 2), ("2001", 1)])
        self.assertEqual(mf.counts(IDX, keys, "players"), [("1 player", 2), ("2 players", 1)])
        self.assertEqual(mf.counts(IDX, keys, "developer"), [])
        self.assertEqual(mf.counts(IDX, ["gba/C.zip"], "genre"), [("Puzzle", 1)])

    def test_filters_combine_with_and(self):
        def hits(filters):
            return sorted(k for k in IDX if mf.matches(IDX[k], filters))
        self.assertEqual(hits({}), sorted(IDX))
        self.assertEqual(hits({"genre": "Platform"}), ["gba/A.zip", "gba/B.zip"])
        self.assertEqual(hits({"genre": "Platform", "year": "1999"}), ["gba/A.zip"])
        self.assertEqual(hits({"players": "2 players"}), ["gba/A.zip"])
        self.assertEqual(hits({"genre": "Puzzle", "players": "1 player"}), [])  # C has no players value

    def test_describe_in_field_order(self):
        self.assertEqual(mf.describe({"year": "1999", "genre": "Platform"}), "genre: Platform · year: 1999")
        self.assertEqual(mf.describe({}), "")


if __name__ == "__main__":
    unittest.main()
