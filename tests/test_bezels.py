import helpers  # noqa: F401  (isolate first)
import unittest
from unittest import mock

from sync_roms import bezels, inventory

LISTING = {"os/android/bezels/magicx-zero40/": 0, "os/android/bezels/magicx-zero40/retroarch/gb.cfg": 86,
           "os/android/bezels/magicx-zero40/.DS_Store": 6, "os/android/bezels/magicx-zero40-pro/x.png": 1}


class Bezels(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(inventory, "files", lambda prefix, sizes=True: {k: v for k, v in LISTING.items() if k.startswith(prefix)})
        p.start()
        self.addCleanup(p.stop)

    def test_files_only_the_device(self):
        self.assertEqual(set(bezels.files("magicx-zero40")), {"os/android/bezels/magicx-zero40/retroarch/gb.cfg"})

    def test_devices(self):
        self.assertEqual(bezels.devices(), ["magicx-zero40", "magicx-zero40-pro"])

    def test_jobs_target_bezels_folder(self):
        jobs = bezels.jobs("magicx-zero40", "/card")
        self.assertEqual(jobs, [("os/android/bezels/magicx-zero40/retroarch/gb.cfg", "/card/Bezels/retroarch/gb.cfg", 86)])

    def test_no_device(self):
        self.assertEqual(bezels.files(None), {})


if __name__ == "__main__":
    unittest.main()
