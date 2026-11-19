import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import update_setup_guide  # noqa: E402


class SetupGuideTest(unittest.TestCase):
    def test_device_list_matches_devices_json(self):
        with open(update_setup_guide.GUIDE) as f:
            html = f.read()
        self.assertEqual(update_setup_guide.embedded(html), update_setup_guide.devices_json(),
                         "run tools/update_setup_guide.py")

    def test_guide_command_opens_the_packaged_page(self):
        from unittest import mock
        from sync_roms import commands
        with mock.patch("webbrowser.open", return_value=True) as opened:
            self.assertEqual(commands.run(["guide"]), 0)
        url = opened.call_args[0][0]
        self.assertTrue(url.startswith("file://") and url.endswith("/sync_roms/data/setup-guide.html"))
        self.assertTrue(os.path.exists(update_setup_guide.GUIDE))


if __name__ == "__main__":
    unittest.main()
