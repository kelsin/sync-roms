# Steadier Time Left Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The progress bar's time left is computed from the last 60 seconds of progress instead of the last 5, so it stops swinging.

**Architecture:** `ui.ProgressBar.draw` already keeps a queue of `(time, bytes moved, bytes written)` samples. Keep them for 60 seconds, measure the speed shown from the oldest sample of the last 5 seconds (as today) and the time left from the oldest kept sample.

**Tech Stack:** Python standard library, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-17-steady-time-left-design.md`

## Global Constraints

- Only `src/sync_roms/ui.py` and `tests/test_ui_progress.py` change.
- The speed shown and the disk speed stay the `SPEED_WINDOW` (5 second) figures; existing speed tests keep their assertions.
- `ETA_WINDOW = 60`, `ETA_MIN = 5` (seconds).
- No commit: the user commits.
- Match the file's style: long lines, short trailing comments, no new helpers or classes unless needed.

## Review Focus

- Draws further apart than `SPEED_WINDOW` (only the newest sample is recent): no speed text, no crash.
- A bar with no `total_bytes`: no speed and no time left, as today.
- A stall right from the start (nothing ever moved): no time left.
- Progress resuming after a 60 second stall: the time left comes back once the kept samples span `ETA_MIN` seconds and the rate is above 0.
- The line still never reaches the terminal width (`BottleneckTest.test_line_never_reaches_the_terminal_width`).

---

### Task 1: Time left from the last 60 seconds

**Files:**
- Modify: `src/sync_roms/ui.py:19` (constants) and `ProgressBar.__init__`/`draw` (about lines 304-331)
- Test: `tests/test_ui_progress.py`

- [ ] **Step 1: Write the failing tests**

Add to `SpeedWindowTest` in `tests/test_ui_progress.py` (it has `draw_at(bar, now, fraction)`):

```python
    def bar(self):
        with mock.patch.object(ui.time, "monotonic", return_value=0):
            return ui.ProgressBar(1, lambda: 0, 1000 * 1024 * 1024)

    def test_time_left_uses_the_last_minute_not_the_last_seconds(self):
        bar = self.bar()
        self.draw_at(bar, 0, 0.0)
        self.draw_at(bar, 30, 0.25)
        line = self.draw_at(bar, 32, 0.5)  # 250 MB in the last 2s, but 500 MB in 32s
        self.assertIn("125.0 MB/s", line)
        self.assertIn("0m32s left", line)  # the 2s speed alone would say 0m04s

    def test_no_time_left_in_the_first_seconds(self):
        bar = self.bar()
        self.draw_at(bar, 0, 0.0)
        line = self.draw_at(bar, 4, 0.4)
        self.assertIn("100.0 MB/s", line)
        self.assertNotIn("left", line)
        self.assertIn("0m05s left", self.draw_at(bar, 5, 0.5))

    def test_short_stall_keeps_the_time_left(self):
        bar = self.bar()
        self.draw_at(bar, 0, 0.0)
        self.draw_at(bar, 10, 0.5)
        self.draw_at(bar, 16, 0.5)
        line = self.draw_at(bar, 20, 0.5)
        self.assertIn("0 B/s", line)
        self.assertIn("0m20s left", line)

    def test_time_left_goes_when_nothing_moved_for_a_minute(self):
        bar = self.bar()
        self.draw_at(bar, 0, 0.0)
        self.draw_at(bar, 10, 0.5)
        self.draw_at(bar, 68, 0.5)
        line = self.draw_at(bar, 71, 0.5)
        self.assertIn("0 B/s", line)
        self.assertNotIn("left", line)
```

`BottleneckTest.line` draws at t=0 and t=2 and its width tests count on a time left being in the line. Add one more draw at t=-10, before the t=0 draw and with the same counters, so the kept samples span 12 seconds (the time left becomes `9m20s`/`7m20s`, the same width as before). Its assertions don't change.

- [ ] **Step 2: Run the tests to see them fail**

Run: `python -m unittest tests.test_ui_progress -v`
Expected: `test_time_left_uses_the_last_minute_not_the_last_seconds`, `test_no_time_left_in_the_first_seconds` and `test_short_stall_keeps_the_time_left` FAIL; the rest pass.

- [ ] **Step 3: Implement in `src/sync_roms/ui.py`**

- Next to `SPEED_WINDOW`: `ETA_WINDOW = 60  # seconds the time left is averaged over` and `ETA_MIN = 5  # seconds of progress before a time left is shown`.
- In `draw`: drop samples older than `ETA_WINDOW` (always keeping one). The speed and disk speed are measured from the oldest sample no older than `SPEED_WINDOW` (the newest sample always qualifies), with the existing `span >= 1` rule on that sample's age. The time left is `eta(remaining bytes / rate since the oldest kept sample)`, shown only when the kept samples span at least `ETA_MIN` seconds and that rate is above 0.
- Update the `self.samples` comment in `__init__` to say `ETA_WINDOW`.

- [ ] **Step 4: Run the tests**

Run: `python -m unittest tests.test_ui_progress -v`
Expected: all pass.

Run: `python -m unittest discover -s tests`
Expected: OK.
