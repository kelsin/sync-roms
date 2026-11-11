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

    def test_genre_is_its_first_segment(self):
        self.assertEqual(mf.values({"genre": "Sports / Baseball"}), {"genre": {"Sports"}})
        self.assertEqual(mf.values({"genre": " Platform "}), {"genre": {"Platform"}})
        self.assertEqual(mf.values({"genre": "Shoot'em Up, Vertical"}), {"genre": {"Shoot'em Up, Vertical"}})
        self.assertEqual(mf.values({"genre": "unknown"}), {})

    def test_players_are_not_a_field(self):
        self.assertEqual(mf.values({"players": "1-2"}), {})
        self.assertNotIn("players", dict(mf.FIELDS))

    def test_developer_and_publisher_are_trimmed(self):
        self.assertEqual(mf.values({"developer": " Nintendo ", "publisher": "Capcom", "name": "x"}),
                         {"developer": {"Nintendo"}, "publisher": {"Capcom"}})
        self.assertEqual(mf.values({"developer": "", "publisher": "  "}), {})
        self.assertEqual(mf.values("not an entry"), {})


IDX = mf.index({"A.zip": {"genre": "Platform", "releasedate": "1999"},
                "B.zip": {"genre": "Platform / Run", "releasedate": "2001-01-01"},
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
        self.assertEqual(mf.counts(IDX, keys, "developer"), [])
        self.assertEqual(mf.counts(IDX, ["gba/C.zip"], "genre"), [("Puzzle", 1)])

    def test_filters_combine_with_and(self):
        def hits(filters):
            return sorted(k for k in IDX if mf.matches(IDX[k], filters))
        self.assertEqual(hits({}), sorted(IDX))
        self.assertEqual(hits({"genre": "Platform"}), ["gba/A.zip", "gba/B.zip"])
        self.assertEqual(hits({"genre": "Platform", "year": "1999"}), ["gba/A.zip"])
        self.assertEqual(hits({"genre": "Puzzle", "developer": "X"}), [])  # C has no developer

    def test_values_are_alphabetical(self):
        idx = mf.index({"A.zip": {"developer": "Zed", "publisher": "zulu", "genre": "Sports"},
                        "B.zip": {"developer": "Zed", "publisher": "zulu", "genre": "Sports"},
                        "C.zip": {"developer": "Alpha", "publisher": "Bravo", "genre": "Action"}}, "gba")
        self.assertEqual(mf.counts(idx, list(idx), "developer"), [("Alpha", 1), ("Zed", 2)])
        self.assertEqual(mf.counts(idx, list(idx), "publisher"), [("Bravo", 1), ("zulu", 2)])
        self.assertEqual(mf.counts(idx, list(idx), "genre"), [("Action", 1), ("Sports", 2)])

    def test_spellings_that_differ_by_case_are_one_value(self):
        idx = mf.index({"A.zip": {"developer": "capcom", "genre": "action"},
                        "B.zip": {"developer": "Capcom", "genre": "Action"},
                        "C.zip": {"developer": "Capcom", "genre": "ACTION / Run"},
                        "D.zip": {"developer": "Konami", "genre": "Puzzle"}}, "gba")
        # the most common spelling is shown; on a tie, the first seen
        self.assertEqual(mf.counts(idx, list(idx), "developer"), [("Capcom", 3), ("Konami", 1)])
        self.assertEqual(mf.counts(idx, list(idx), "genre"), [("action", 3), ("Puzzle", 1)])
        for value in ("Capcom", "capcom", "CAPCOM"):
            self.assertEqual(sorted(k for k in idx if mf.matches(idx[k], {"developer": value})),
                             ["gba/A.zip", "gba/B.zip", "gba/C.zip"], value)
        self.assertEqual(sorted(k for k in idx if mf.matches(idx[k], {"genre": "Action"})),
                         ["gba/A.zip", "gba/B.zip", "gba/C.zip"])

    def test_describe_in_field_order(self):
        self.assertEqual(mf.describe({"year": "1999", "genre": "Platform"}), "genre: Platform · year: 1999")
        self.assertEqual(mf.describe({}), "")


if __name__ == "__main__":
    unittest.main()
