import unittest
from unittest import mock

import helpers  # noqa: F401  (isolate first)
from sync_roms import commands


class RefreshTests(unittest.TestCase):
    def test_runs_steps_in_order(self):
        with mock.patch.object(commands, "run", return_value=0) as run:
            self.assertEqual(commands.refresh_cmd(None), 0)
        self.assertEqual([c.args[0] for c in run.call_args_list], list(commands.REFRESH_STEPS))

    def test_stops_at_first_failure(self):
        with mock.patch.object(commands, "run", side_effect=[0, 3, 0, 0]) as run:
            self.assertEqual(commands.refresh_cmd(None), 3)
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
