import contextlib
import io
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import m3u, ui  # noqa: E402

FAH = ["Fahrenheit (USA) (Disc 1) (Key Disc) (Sega CD).chd", "Fahrenheit (USA) (Disc 2) (Sega CD).chd"]


class M3uTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def touch(self, *names, text=""):
        for n in names:
            with open(os.path.join(self.dir, n), "w") as f:
                f.write(text)

    def read(self, name):
        with open(os.path.join(self.dir, name)) as f:
            return f.read()

    def run_cmd(self, dry_run=False, answer=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(ui, "confirm", return_value=answer):
            m3u.m3u_command(SimpleNamespace(m3u=self.dir, dry_run=dry_run))
        return out.getvalue()

    def test_groups(self):
        files = FAH + ["Chrono Cross (USA) (Disc 1).chd", "Chrono Cross (USA) (Disc 2).chd",
                       "FF IX (USA) (Disc 1) (Rev 1).chd", "FF IX (USA) (Disc 2) (Rev 1).chd", "Solo (USA) (Disc 1).chd"]
        self.assertEqual(m3u.disc_groups(files), {
            "Fahrenheit (USA) (Sega CD).m3u": FAH,
            "Chrono Cross (USA).m3u": ["Chrono Cross (USA) (Disc 1).chd", "Chrono Cross (USA) (Disc 2).chd"],
            "FF IX (USA) (Rev 1).m3u": ["FF IX (USA) (Disc 1) (Rev 1).chd", "FF IX (USA) (Disc 2) (Rev 1).chd"]})

    def test_creates_missing(self):
        self.touch(*FAH)
        self.run_cmd()
        self.assertEqual(self.read("Fahrenheit (USA) (Sega CD).m3u"), "\n".join(FAH) + "\n")

    def test_creates_for_rvz(self):
        discs = ["Game (USA) (Disc 1).rvz", "Game (USA) (Disc 2).rvz"]
        self.touch(*discs)
        self.run_cmd()
        self.assertEqual(self.read("Game (USA).m3u"), "\n".join(discs) + "\n")

    def test_rewrites_wrong_and_partial(self):
        self.touch(*FAH)
        self.touch("Fahrenheit (USA) (Sega CD).m3u", text=FAH[1] + "\n")
        self.touch("Other.m3u", text=FAH[0] + "\ngone.chd\n")
        self.run_cmd()
        self.assertEqual(self.read("Fahrenheit (USA) (Sega CD).m3u"), "\n".join(FAH) + "\n")
        self.assertEqual(self.read("Other.m3u"), FAH[0] + "\n")

    def test_deletes_dead_only_when_confirmed(self):
        self.touch("Dead.m3u", text="gone.chd\n")
        self.run_cmd()
        self.assertTrue(os.path.exists(os.path.join(self.dir, "Dead.m3u")))
        self.run_cmd(answer=True)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "Dead.m3u")))

    def test_renames_playlist_with_other_name(self):
        self.touch(*FAH)
        self.touch("Fahrenheit.m3u", text="\n".join(FAH) + "\n")
        self.run_cmd()
        self.assertEqual(sorted(f for f in os.listdir(self.dir) if f.endswith(".m3u")), ["Fahrenheit (USA) (Sega CD).m3u"])
        self.assertEqual(self.read("Fahrenheit (USA) (Sega CD).m3u"), "\n".join(FAH) + "\n")

    def test_dry_run_changes_nothing(self):
        self.touch(*FAH)
        self.run_cmd(dry_run=True)
        self.assertEqual(sorted(os.listdir(self.dir)), sorted(FAH))


if __name__ == "__main__":
    unittest.main()
