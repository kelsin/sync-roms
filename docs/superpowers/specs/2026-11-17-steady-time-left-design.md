# Steadier time left on the progress bar

## Why

The time left shown by `ui.ProgressBar` (sync downloads, uploads, CHD conversion) swings a lot. It is the remaining
bytes divided by the speed of the last `SPEED_WINDOW` (5) seconds, redrawn every 0.25s, so one file finishing, an fsync
pause or a burst rescales the whole remaining time. When nothing moves for 5 seconds the estimate disappears and comes
back with a wild number, and the first estimate appears after 1 second of data.

## Goals

- A time left that moves smoothly and still follows a real change of speed within about a minute.
- The speed shown stays the current (5 second) speed.

## Non-goals

- The scrape header's estimate (`scrape_online._progress`), which is the run's average and already steady.
- Modelling per-file overhead (uploads go biggest first, so the estimate runs low until the small files at the end).

## Approaches

1. **Rate over the last 60 seconds for the time left (picked).** Uses the sample queue already in `ProgressBar`; easy
   to test with a fake clock; follows a real slowdown within a minute.
2. Whole-run average: steadiest, but wrong for a long time after the speed really changes.
3. Exponential smoothing: about the same behaviour as 1, harder to test and reason about.

## Design

All in `ui.ProgressBar.draw`:

- `ETA_WINDOW = 60` and `ETA_MIN = 5` (seconds) next to `SPEED_WINDOW`.
- Samples are kept for `ETA_WINDOW` seconds instead of `SPEED_WINDOW`.
- The speed shown (and the disk speed) is measured from the oldest sample no older than `SPEED_WINDOW` seconds, as
  today.
- Time left is the remaining bytes divided by the rate from the oldest kept sample to now (the whole run while it is
  shorter than `ETA_WINDOW`).
- No time left is shown until the kept samples span `ETA_MIN` seconds.
- During a stall the time left stays up and grows as the 60 second rate decays; it goes away only when that rate is 0,
  that is when nothing has moved for `ETA_WINDOW` seconds.

## Tests

In `tests/test_ui_progress.py`, with the fake clock already used there: the estimate uses the 60 second rate while the
speed shown uses the 5 second one; no estimate before 5 seconds; a short stall keeps the estimate; a 60 second stall
drops it. The existing `test_stalled_transfer_shows_no_eta` changes to match.
