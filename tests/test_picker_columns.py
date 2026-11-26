import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401
from sync_roms import picker  # noqa: E402

LABELS = ["B", "A", "C", "A"]
SYSTEMS = ["snes", "gba", "nes", "nes"]
COLUMNS = [picker.Column("name", "Name", True), picker.Column("system", "System", True),
           picker.Column("year", "Year", True)]


def model(years=None, sort=None, multi=False, columns=COLUMNS, pinned=None, labels=LABELS, systems=SYSTEMS, **kw):
    years = ["1994", "1994", None, "1990"] if years is None else years
    values = {"system": systems, "year": years}
    extras = [[(f"  {s}", "cyan"), (f"  {y or '—'}", "dim")] for s, y in zip(systems, years)]
    m = picker._ListModel("t", list(labels), multi, None, "", 0, extras, None, "", (), None, None, True, None, None,
                          True, None, None, None, None, columns=columns,
                          sort_value=lambda i, c: values[c][i] if c in values else None,
                          sort=sort or picker.Sort(("year", "name", "system")), pinned=pinned, **kw)
    m.resize(30, 80)
    m.years = years  # the list the sort values read: tests change it in place
    return m


class SortOrder(unittest.TestCase):
    def test_order_puts_first_then_the_default_then_the_rest(self):
        s = picker.Sort(("year", "name", "system"))
        self.assertEqual(s.order(["name", "system", "year", "size"]), ["year", "name", "system", "size"])
        s.first = "name"
        self.assertEqual(s.order(["name", "system", "year", "size"]), ["name", "year", "system", "size"])
        s.first = "size"
        self.assertEqual(s.order(["name", "system", "year", "size"]), ["size", "year", "name", "system"])
        self.assertEqual(s.order(["name", "year"]), ["year", "name"])

    def test_games_sort_is_year_name_system(self):
        self.assertEqual(picker.GAMES_SORT.order(["name", "system", "year"]), ["year", "name", "system"])


class Sorting(unittest.TestCase):
    def test_default_sort_year_name_system(self):
        self.assertEqual(model().vis, [3, 1, 0, 2])

    def test_o_menu_sets_first_column(self):
        m = model()
        m.key("o")
        self.assertIsNotNone(m.sort_menu)
        self.assertEqual([c.header for c in m.sort_columns()], ["Name", "System", "Year"])
        self.assertEqual(m.sort_menu, 2)  # on the current first column
        m.key("escape")
        self.assertIsNone(m.sort_menu)
        self.assertIsNone(m.sort.first)
        self.assertEqual(m.vis, [3, 1, 0, 2])
        m.key("o")
        m.key("k")
        m.key("up")
        m.key("enter")
        self.assertIsNone(m.sort_menu)
        self.assertEqual(m.sort.first, "name")
        self.assertEqual(m.sort.order(["name", "system", "year"]), ["name", "year", "system"])
        self.assertEqual(m.vis, [3, 1, 0, 2])  # A 1990, A 1994, B, C

    def test_the_menu_keeps_other_keys_from_the_list(self):
        m = model(multi=True)
        m.key("o")
        m.key("space")
        m.key("V")
        self.assertEqual(m.state, [False] * 4)
        self.assertEqual(m.view_mode, 0)
        self.assertIsNotNone(m.sort_menu)
        m.key("q")
        self.assertIsNone(m.sort_menu)

    def test_O_reverses_all(self):
        m = model()
        m.key("O")
        self.assertTrue(m.sort.reverse)
        self.assertEqual(m.vis, [0, 1, 3, 2])
        m.key("O")
        self.assertFalse(m.sort.reverse)
        self.assertEqual(m.vis, [3, 1, 0, 2])

    def test_reverse_keeps_unknown_last(self):
        m = model()
        self.assertEqual(m.vis[-1], 2)
        m.key("O")
        self.assertEqual(m.vis[-1], 2)

    def test_unknown_later_values_stay_last_both_ways(self):
        m = model(years=["1994", "1994", "1994"], labels=["A", "A", "B"], systems=["nes", None, "gba"])
        self.assertEqual(m.vis, [0, 1, 2])
        m.key("O")
        self.assertEqual(m.vis, [2, 0, 1])

    def test_late_values_keep_cursor(self):
        m = model()
        m.key("G")
        self.assertEqual(m.vis[m.cur], 2)
        m.years[2] = "1980"
        m.update()
        self.assertEqual(m.vis[m.cur], 2)
        self.assertEqual(m.vis[0], 2)

    def test_the_cursor_argument_names_a_row(self):
        values = {"year": ["1994", "1994", None, "1990"]}
        m = picker._ListModel("t", LABELS, False, None, "", 2, None, None, "", (), None, None, True, None, None, True,
                              None, None, None, None, columns=[COLUMNS[0], COLUMNS[2]],
                              sort_value=lambda i, c: values.get(c, [None] * 4)[i], sort=picker.Sort(("year", "name")))
        self.assertEqual(m.vis[m.cur], 2)

    def test_a_query_still_puts_the_cursor_on_top(self):
        m = model()
        m.key("G")
        m.key("/")
        m.key("a")
        self.assertEqual(m.cur, 0)

    def test_missing_first_column_falls_back(self):
        s = picker.Sort(("year", "name", "system"))
        s.first = "size"
        m = model(sort=s)
        self.assertEqual(m.vis, [3, 1, 0, 2])
        self.assertEqual(s.first, "size")

    def test_pinned_rows_stay_last(self):
        labels = ["B", "A", "C", "➕ New"]
        m = model(labels=labels, pinned=[False, False, False, True], years=["1994", "1994", None, None])
        m.key("o")
        m.key("g")
        m.key("enter")
        self.assertEqual(m.sort.first, "name")
        self.assertEqual(m.vis, [1, 0, 2, 3])
        m.key("O")
        self.assertEqual(m.vis, [2, 0, 1, 3])

    def test_default_sort_is_the_sortable_columns_in_display_order(self):
        m = picker._ListModel("t", LABELS, False, None, "", 0, [[(f"  {s}", "")] for s in SYSTEMS], None, "", (), None,
                              None, True, None, None, True, None, None, None, None, columns=COLUMNS[:2],
                              sort_value=lambda i, c: SYSTEMS[i] if c == "system" else None)
        self.assertEqual(m.sort.order(["name", "system"]), ["name", "system"])
        self.assertEqual(m.vis, [1, 3, 0, 2])  # A gba, A nes, B, C

    def test_no_columns_keeps_the_callers_order(self):
        m = picker._ListModel("t", LABELS, False, None, "", 0, None, None, "", (), None, None, True, None, None, True,
                              None, None, None, None)
        self.assertEqual(m.vis, [0, 1, 2, 3])
        m.key("o")
        m.key("O")
        self.assertIsNone(m.sort_menu)
        self.assertEqual(m.vis, [0, 1, 2, 3])


class Keys(unittest.TestCase):
    def test_slash_matches_system_cell(self):
        m = model()
        m.key("/")
        for c in "snes":
            m.key(c)
        self.assertEqual(m.vis, [0])

    def test_V_cycles_view_and_o_does_not(self):
        m = picker._ListModel("t", ["a", "b"], True, None, "", 0, None, None, "", (), None, None, True, None, None,
                              True, None, None, None, None)
        m.key("o")
        self.assertEqual(m.view_mode, 0)
        self.assertIsNone(m.sort_menu)
        m.key("ctrl+o")
        self.assertEqual(m.view_mode, 0)
        m.key("V")
        self.assertEqual(m.view_mode, 1)

    def test_header_takes_a_row(self):
        self.assertEqual(model().view, 30 - 6 - 1)

    def test_header_row_fits_width(self):
        m = model()
        header = picker.header_row(m, 30)
        self.assertEqual(header.cell_len, 30)
        self.assertIn("Year ▲", header.plain)
        self.assertTrue(header.plain.startswith("Name"))
        m.key("O")
        self.assertIn("Year ▼", picker.header_row(m, 30).plain)

    def test_header_lines_up_with_the_cells(self):
        m = model(multi=True)
        header = picker.header_row(m, 60).plain
        self.assertTrue(header.startswith("   Name"))
        widths = m.column_widths()
        start = m.label_width
        self.assertEqual(header[start:start + 8], "  System")
        self.assertGreaterEqual(widths[0], len("  System ▲"))

    def test_sort_menu_lines_mark_the_first_column(self):
        m = model()
        m.key("o")
        lines = m.sort_menu_lines()
        self.assertEqual([text for text, _ in lines], ["Name", "System", "Year ▲"])
        self.assertEqual([on for _, on in lines], [False, False, True])

    def test_poll_waits_while_the_menu_is_up(self):
        calls = []
        m = model()
        m.poll = lambda: calls.append(1)
        m.key("o")
        m.tick()
        self.assertEqual(calls, [])
        m.key("escape")
        m.tick()
        self.assertEqual(calls, [1])

    def test_help_lists_sort_keys(self):
        lines = picker.help_lines(True, "", sortable=True)
        self.assertIn("o               sort by a column", lines)
        self.assertIn("O               reverse the order", lines)
        self.assertIn("V               view: all / on / changed", lines)
        self.assertFalse(any(line.startswith("o ") for line in picker.help_lines(True, "")))

    def test_hint_offers_sorting_only_with_sortable_columns(self):
        self.assertIn("V view", picker.MULTI_HINT)
        self.assertEqual(model().sort_hint(), " · o sort · O reverse")
        m = picker._ListModel("t", ["a"], True, None, "", 0, None, None, "", (), None, None, True, None, None,
                              True, None, None, None, None)
        self.assertEqual(m.sort_hint(), "")


class OnScreen(unittest.TestCase):
    def test_the_app_draws_the_header_the_menu_and_returns_the_callers_index(self):
        seen = []
        years = ["1994", "1994", None, "1990"]

        async def script(pilot):
            seen.append(helpers.screen_text(pilot.app))
            await pilot.press("o")
            seen.append(helpers.screen_text(pilot.app))
            await pilot.press("escape", "enter")
        extras = [[(f"  {s}", "cyan"), (f"  {y or '—'}", "dim")] for s, y in zip(SYSTEMS, years)]
        got = helpers.pilot_list(script, "t", LABELS, extras=extras, columns=COLUMNS, sort=picker.Sort(("year", "name")),
                                 sort_value=lambda i, c: {"system": SYSTEMS, "year": years}.get(c, [None] * 4)[i])
        self.assertEqual(got, 3)  # the top row is the 1990 game
        before, menu = seen
        self.assertTrue(before[4].startswith("Name    System    Year ▲ "))
        self.assertTrue(before[5].startswith("A       nes       1990 "))
        self.assertIn("o sort · O revers", before[2])  # cut at 80 cells
        self.assertEqual([line.strip() for line in menu[5:8]], ["Name", "System", "Year ▲"])
        self.assertIn(picker.SORT_MENU_HINT, menu[2])


if __name__ == "__main__":
    unittest.main()
