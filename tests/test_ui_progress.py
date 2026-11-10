import contextlib
import io
import os
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
            last = self.line(1024, 1024, columns=columns).split("\r\033[K")[-1]
            plain = ui.re.sub(r"\033\[[0-9;]*m", "", last)
            self.assertLess(len(plain), columns)


if __name__ == "__main__":
    unittest.main()
