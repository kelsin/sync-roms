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

    def test_add_skips_dlc_and_update_zips(self):
        self.zip("G [PCSE00349] [USA] [NoNpDRM].zip", title_id="PCSE00349")
        self.zip("G [PCSE00349] [USA] [PATCH] [v1.02] [NoNpDRM].zip", category="gp", title_id="PCSE00349")
        self.zip("D [PCSE00349] [USA] [DLC-X].zip", category="ac", title_id="PCSE00349")
        self.assertEqual(vita.add_psvita_files([self.dir]), [])
        self.assertEqual([f for f in self.files() if f.endswith(".psvita")], ["G [PCSE00349] [USA] [NoNpDRM].psvita"])


GAME = "psvita/1001 Spikes [PCSE00349] [USA] [NoNpDRM].zip"
OLD = "psvita/1001 Spikes [PCSE00349] [USA] [PATCH] [v1.02] [NoNpDRM].zip"
NEW = "psvita/1001 Spikes [PCSE00349] [USA] [PATCH] [v1.11] [NoNpDRM].zip"
UNTAGGED = "psvita/1001 Spikes [PCSE00349] [USA] [PATCH] [NoNpDRM].zip"
DLC_A = "psvita/5-Level Boost [PCSE00349] [USA] [DLC-ADDCONT049LVL000].zip"
DLC_B = "psvita/Accessory Pack [PCSE00349] [USA] [DLC-U000100PRM014ACA].zip"
OTHER = "psvita/Tearaway [PCSA00144] [USA] [NoNpDRM].zip"
OTHER_DLC = "psvita/Costume [PCSA00144] [USA] [DLC-X].zip"
NO_ID = "psvita/World of Final Fantasy.rar"
FOLDER = [GAME, OLD, NEW, UNTAGGED, DLC_B, DLC_A, OTHER, OTHER_DLC, NO_ID]


class ExtrasTest(unittest.TestCase):
    def test_kind(self):
        self.assertEqual([vita.kind(k) for k in (GAME, OLD, DLC_A, NO_ID)], ["game", "update", "dlc", "game"])

    def test_is_extra_only_under_psvita(self):
        self.assertTrue(vita.is_extra(OLD))
        self.assertTrue(vita.is_extra(DLC_A))
        self.assertFalse(vita.is_extra(GAME))
        self.assertFalse(vita.is_extra("gba/Hack [PCSE00001] [PATCH].zip"))

    def test_extras_are_every_dlc_then_the_newest_update(self):
        self.assertEqual(vita.extras([GAME], FOLDER), {GAME: [DLC_A, DLC_B, NEW]})

    def test_untagged_update_loses_to_a_versioned_one_but_counts_alone(self):
        self.assertEqual(vita.extras([GAME], [GAME, UNTAGGED, OLD]), {GAME: [OLD]})
        self.assertEqual(vita.extras([GAME], [GAME, UNTAGGED]), {GAME: [UNTAGGED]})

    def test_games_without_extras_and_non_games_are_left_out(self):
        self.assertEqual(vita.extras([OTHER, NO_ID, DLC_A, "gba/A [PCSE00349].zip"], FOLDER), {OTHER: [OTHER_DLC]})
        self.assertEqual(vita.extras([NO_ID], FOLDER), {})

    def test_folder_keys_may_be_a_dict(self):
        self.assertEqual(vita.extras([GAME], {GAME: 1, DLC_A: 2}), {GAME: [DLC_A]})


if __name__ == "__main__":
    unittest.main()
