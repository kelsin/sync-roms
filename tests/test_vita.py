import os
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import vita  # noqa: E402


class VitaTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def zip(self, name, category="gd", title_id="PCSE00120", entry="app/PCSE00120/sce_sys/param.sfo"):
        keys = [("CATEGORY", category), ("TITLE_ID", title_id)]
        key_table = b"".join(k.encode() + b"\0" for k, _ in keys)
        index, data, key_off = b"", b"", 0
        for k, v in keys:
            value = v.encode() + b"\0"
            index += struct.pack("<HHIII", key_off, 0x204, len(value), len(value), len(data))
            data += value
            key_off += len(k) + 1
        key_start = 20 + len(index)
        sfo = b"\0PSF\1\1\0\0" + struct.pack("<III", key_start, key_start + len(key_table), len(keys)) + index + key_table + data
        path = os.path.join(self.dir, name)
        with zipfile.ZipFile(path, "w") as z:
            z.writestr(entry, sfo)
        return path

    def files(self):
        return sorted(os.listdir(self.dir))

    def test_zip_gets_a_psvita_file_and_stays(self):
        path = self.zip("Persona 4 GOLDEN [PCSE00120].zip")
        self.assertIsNone(vita.make_psvita(path))
        self.assertEqual(self.files(), ["Persona 4 GOLDEN [PCSE00120].psvita", "Persona 4 GOLDEN [PCSE00120].zip"])
        with open(path[:-4] + ".psvita") as f:
            self.assertEqual(f.read(), "PCSE00120")

    def test_param_sfo_at_the_root(self):
        self.assertIsNone(vita.make_psvita(self.zip("A.zip", entry="sce_sys/param.sfo")))

    def test_zip_without_a_game_gets_no_psvita_file(self):
        self.assertEqual(vita.make_psvita(self.zip("Patch.zip", category="gp")), "no game in the zip")
        self.assertEqual(self.files(), ["Patch.zip"])

    def test_add_skips_zips_that_have_one_and_reports_bad_zips(self):
        self.zip("A.zip", title_id="PCSE00001")
        self.zip("B.zip", title_id="PCSE00002")
        with open(os.path.join(self.dir, "B.psvita"), "w") as f:
            f.write("old")
        with open(os.path.join(self.dir, "Bad.zip"), "w") as f:
            f.write("not a zip")
        failures = vita.add_psvita_files([self.dir])
        self.assertEqual([os.path.basename(p) for p, _ in failures], ["Bad.zip"])
        self.assertEqual(self.files(), ["A.psvita", "A.zip", "B.psvita", "B.zip", "Bad.zip"])
        with open(os.path.join(self.dir, "B.psvita")) as f:
            self.assertEqual(f.read(), "old")


if __name__ == "__main__":
    unittest.main()
