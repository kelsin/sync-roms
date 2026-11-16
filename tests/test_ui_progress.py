import contextlib
import io
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import ui  # noqa: E402


class ByteProgressTest(unittest.TestCase):
    def test_fraction_is_a_running_total_capped_per_job(self):
        moved = ui.ByteProgress([10, 0])  # an empty file counts as 1 byte
        self.assertEqual(moved.total, 11)
        moved.add(0, 4)
        moved.add(0, 100)  # more than the job's size doesn't overshoot
        self.assertEqual(moved.done, 10)
        moved.finish(1)
        moved.finish(0)
        self.assertEqual((moved.done, moved.fraction()), (11, 1.0))


class HelperTest(unittest.TestCase):
    def test_print_head_shows_the_first_n_and_the_rest_counted(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ui.print_head([1, 2, 3], 2, lambda n: f"#{n}")
        self.assertEqual(out.getvalue().split("\n")[:3], ["       #1", "       #2", "       … and 1 more"])

    def test_wait_drawing_redraws_until_the_result_is_ready(self):
        calls, drawn = [], []

        def get(timeout):
            calls.append(timeout)
            if len(calls) < 3:
                raise ui.FutureTimeout
            return "done"

        with mock.patch.object(ui, "POLL", 0.5):
            self.assertEqual(ui.wait_drawing(mock.Mock(draw=drawn.append), 7, get), "done")
        self.assertEqual((calls, drawn), ([0.5] * 3, [7, 7]))


class SpeedWindowTest(unittest.TestCase):
    def draw_at(self, bar, now, fraction):
        out = io.StringIO()
        bar.fraction = lambda: fraction
        with mock.patch.object(ui.time, "monotonic", return_value=now), contextlib.redirect_stdout(out), \
                mock.patch.object(ui.shutil, "get_terminal_size", return_value=os.terminal_size((200, 24))):
            bar.shown = True
            bar.draw(0)
        return out.getvalue()

    def test_speed_is_the_recent_rate_not_the_run_average(self):
        with mock.patch.object(ui.time, "monotonic", return_value=0):
            bar = ui.ProgressBar(1, lambda: 0, 1000 * 1024 * 1024)
        self.draw_at(bar, 0, 0.0)
        self.draw_at(bar, 10, 0.5)  # slow start would average to 50 MB/s over 10s
        line = self.draw_at(bar, 12, 0.6)  # but the last window moved 100 MB in 2s
        self.assertIn("50.0 MB/s", line)
        line = self.draw_at(bar, 14, 0.8)  # window now spans 10s..14s: 300 MB in 4s
        self.assertIn("75.0 MB/s", line)

    def test_stalled_transfer_shows_no_eta(self):
        with mock.patch.object(ui.time, "monotonic", return_value=0):
            bar = ui.ProgressBar(1, lambda: 0, 1024)
        self.draw_at(bar, 0, 0.5)
        line = self.draw_at(bar, 3, 0.5)
        self.assertIn("0 B/s", line)
        self.assertNotIn("left", line)


class BottleneckTest(unittest.TestCase):
    def line(self, received, written, columns=200):
        io_ = ui.ByteProgress([10 ** 9])
        io_.add(0, received)
        io_.wrote(written)
        with mock.patch.object(ui.time, "monotonic", return_value=0):
            bar = ui.ProgressBar(1, io_.fraction, 10 ** 9, io=io_)
        out = io.StringIO()
        bar.shown = True
        with contextlib.redirect_stdout(out), mock.patch.object(ui.shutil, "get_terminal_size", return_value=os.terminal_size((columns, 24))):
            with mock.patch.object(ui.time, "monotonic", return_value=0):
                bar.draw(0)
            io_.add(0, 20 * 1024 * 1024)
            io_.wrote(5 * 1024 * 1024)
            with mock.patch.object(ui.time, "monotonic", return_value=2):
                bar.draw(0)
        return out.getvalue()

    def test_shows_both_rates(self):
        line = self.line(1024, 1024)
        self.assertIn("net 10.0 MB/s · disk 2.5 MB/s", line)

    def test_big_backlog_blames_the_disk(self):
        self.assertIn("waiting on disk", self.line(200 * 1024 * 1024, 1024))

    def test_small_backlog_blames_the_network(self):
        self.assertIn("waiting on network", self.line(1024, 1024))

    def test_narrow_terminal_drops_waiting_on_first(self):
        line = self.line(1024, 1024, columns=120)
        self.assertNotIn("waiting", line)
        self.assertIn("disk 2.5 MB/s", line)

    def test_narrower_terminal_drops_disk_too(self):
        line = self.line(1024, 1024, columns=100)
        self.assertNotIn("disk", line)
        self.assertIn("10.0 MB/s", line)

    def test_line_never_reaches_the_terminal_width(self):
        for columns in (70, 100, 120, 140):
            last = self.line(1024, 1024, columns=columns).split("\r\033[J")[-1]
            plain = ui.re.sub(r"\033\[[0-9;]*m", "", last)
            self.assertLess(len(plain), columns)


if __name__ == "__main__":
    unittest.main()


class ActiveTest(unittest.TestCase):
    def test_active_is_in_start_order_and_drops_finished_jobs(self):
        moved = ui.ByteProgress([10, 20, 30])
        moved.start(1)
        moved.add(0, 5)  # first bytes count as a start
        self.assertEqual(moved.active(["a", "b", "c"]), [("b", 0, 20), ("a", 5, 10)])
        moved.finish(1)
        moved.add(1, 3)  # a late callback doesn't bring it back
        moved.start(1)
        self.assertEqual(moved.active(["a", "b", "c"]), [("a", 5, 10)])


class BlockTest(unittest.TestCase):
    def draw(self, active, columns=80, rows=24):
        bar = ui.ProgressBar(len(active), lambda: 0.5, active=lambda: active)
        bar.shown = True
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                mock.patch.object(ui.shutil, "get_terminal_size", return_value=os.terminal_size((columns, rows))):
            bar.draw(0)
        return out.getvalue()

    def lines(self, text):
        return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text).replace("\r", "").split("\n")

    def test_lists_each_file_in_flight_below_the_bar_and_returns_to_it(self):
        out = self.draw([("gba/a.zip", 5, 10), ("gba/b.zip", 0, 2048)])
        below = self.lines(out)[1:]
        self.assertEqual(len(below), 2)
        self.assertIn("gba/a.zip", below[0])
        self.assertIn("50%", below[0])
        self.assertIn("gba/b.zip", below[1])
        self.assertIn("2.0 KB", below[1])
        self.assertTrue(out.endswith("\x1b[2A\r"))  # cursor back on the bar line

    def test_short_terminal_shows_fewer_files_and_counts_the_rest(self):
        out = self.draw([(f"gba/{n}.zip", 0, 1) for n in range(8)], rows=5)  # room for rows - 2 = 3 lines
        below = self.lines(out)[1:]
        self.assertEqual(len(below), 3)
        self.assertIn("gba/0.zip", below[0])
        self.assertIn("gba/1.zip", below[1])
        self.assertIn("… and 6 more", below[2])

    def test_no_room_shows_no_block(self):
        out = self.draw([("gba/a.zip", 0, 1)], rows=2)
        self.assertEqual(len(self.lines(out)), 1)
        self.assertFalse(out.endswith("A\r"))

    def test_long_names_never_wrap(self):
        out = self.draw([("psx/" + "x" * 300 + ".chd", 0, 10 ** 9)], columns=40)
        for line in self.lines(out)[1:]:
            self.assertLessEqual(len(line), 39)
        self.assertIn("…", self.lines(out)[1])

    def test_no_active_draws_just_the_bar(self):
        out = self.draw([])
        self.assertEqual(len(self.lines(out)), 1)

    def test_say_and_clear_wipe_the_block_too(self):
        bar = ui.ProgressBar(1, lambda: 0)
        bar.shown = True
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            bar.say("x")
            bar.clear()
        self.assertEqual(out.getvalue(), "\r\x1b[Jx\n\r\x1b[J")

    def test_non_tty_never_prints_the_block(self):
        bar = ui.ProgressBar(1, lambda: 0, active=lambda: [("gba/a.zip", 0, 1)])
        bar.shown = False
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            bar.draw(0)
        self.assertNotIn("gba/a.zip", out.getvalue())
