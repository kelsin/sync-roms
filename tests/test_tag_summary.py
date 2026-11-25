import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401
from sync_roms import picker, ui  # noqa: E402

INFOS = [("⚔️", "RPG", "Turn-based games"), ("📖", "Story", ""), ("🎮", "Co-op", "With a friend")]


def model(infos=None, height=30, width=80, rows=3):
    infos = INFOS if infos is None else infos
    m = picker._ListModel("t", [f"game {n}" for n in range(rows)], False, None, "", 0, None, None, "", (), None, None,
                          True, None, None, True, None, None, None, None, tag_info=lambda i: infos if i != 1 else [])
    m.resize(height, width)
    return m


class TagLines(unittest.TestCase):
    def test_a_line_per_tag_with_descriptions_in_a_column(self):
        self.assertEqual(picker.tag_lines(INFOS, 80), ["⚔️ RPG    Turn-based games", "📖 Story", "🎮 Co-op  With a friend"])

    def test_long_lines_are_cut_with_an_ellipsis(self):
        self.assertEqual(picker.tag_lines(INFOS[:1], 12), ["⚔️ RPG  Tur…"])
        self.assertEqual(picker.tag_lines(INFOS[:1], 0), [""])

    def test_names_on_one_line(self):
        self.assertEqual(picker.tag_names(INFOS), "⚔️ RPG · 📖 Story · 🎮 Co-op")


class Scroll(unittest.TestCase):
    def test_no_scroll_when_it_fits(self):
        self.assertEqual([picker.scroll_offset(n, 20, 20) for n in range(100)], [0] * 100)

    def test_holds_moves_a_cell_a_tick_holds_and_restarts(self):
        hold, over = picker.SCROLL_HOLD, 5
        offsets = [picker.scroll_offset(n, 25, 20) for n in range(over + 2 * hold + 3)]
        self.assertEqual(offsets[:hold + 1], [0] * (hold + 1))
        self.assertEqual(offsets[hold:hold + over + 1], list(range(over + 1)))
        self.assertEqual(offsets[hold + over:over + 2 * hold], [over] * hold)
        self.assertEqual(offsets[over + 2 * hold], 0)

    def test_window_by_cells_never_splits_a_wide_character(self):
        self.assertEqual(picker.window("ab📖cd", 0, 4), "ab📖")
        self.assertEqual(picker.window("ab📖cd", 0, 3), "ab ")
        self.assertEqual(picker.window("ab📖cd", 3, 3), " cd")
        self.assertEqual(picker.window("ab📖cd", 4, 3), "cd ")
        self.assertEqual(picker.window("ab", 0, 5), "ab   ")


class Model(unittest.TestCase):
    def test_roomy_list_shows_every_tag_and_keeps_its_rows(self):
        m = model(height=30)
        self.assertEqual(m.tag_area(), picker.tag_lines(INFOS, 80))
        self.assertEqual(m.view, 30 - 5 - 3)

    def test_a_tight_list_shows_one_line_of_names(self):
        m = model(height=12)
        self.assertEqual(len(m.tag_area()), 1)
        self.assertTrue(m.tag_area()[0].startswith("⚔️ RPG · 📖 Story"))
        self.assertEqual(m.view, 12 - 6)

    def test_a_game_without_tags_shows_nothing_new(self):
        m = model(height=30)
        m.key("j")
        self.assertEqual(m.tag_area(), [])
        self.assertEqual(m.view, 30 - 5)

    def test_no_tag_info_shows_nothing(self):
        m = picker._ListModel("t", ["a"], False, None, "", 0, None, None, "", (), None, None, True, None, None, True,
                              None, None, None, None)
        self.assertEqual(m.tag_area(), [])

    def test_the_one_line_scrolls_until_its_end_then_stays_put_and_restarts(self):
        m = model(height=12, width=20)
        over = ui.cell_width(picker.tag_names(INFOS)) - 20
        self.assertGreater(over, 0)
        start = m.tag_area()[0]
        moved = sum(m.scroll_advance() for _ in range(picker.SCROLL_HOLD + over + 4))
        self.assertEqual(moved, over)
        self.assertTrue(picker.tag_names(INFOS).endswith(m.tag_area()[0].rstrip()))
        for _ in range(picker.SCROLL_HOLD + 1):
            m.scroll_advance()
        self.assertEqual(m.tag_area()[0], start)
        self.assertEqual(ui.cell_width(m.tag_area()[0]), 20)

    def test_a_line_that_fits_never_moves(self):
        m = model(height=12, width=120)
        self.assertFalse(any(m.scroll_advance() for _ in range(100)))

    def test_it_waits_while_a_notice_or_prompt_has_the_screen(self):
        m = model(height=12, width=20)
        m.scroll = picker.SCROLL_HOLD
        m.notice = "hello"
        self.assertFalse(m.scroll_advance())
        m.notice, m.note = "", ("x", 1)
        self.assertFalse(m.scroll_advance())
        m.note, m.asking = None, True
        self.assertFalse(m.scroll_advance())
        m.asking = False
        self.assertTrue(m.scroll_advance())

    def test_moving_the_highlight_restarts_the_scroll(self):
        m = model(height=12, width=20, rows=4)
        m.scroll = picker.SCROLL_HOLD + 4
        m.key("j")
        m.key("j")
        self.assertEqual(m.scroll, 0)


if __name__ == "__main__":
    unittest.main()
