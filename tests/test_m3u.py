import contextlib
import io
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import downloads, m3u, ui  # noqa: E402

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


class FileGroupsTest(unittest.TestCase):
    def test_discs_and_playlist_are_one_group(self):
        keys = ["psx/A (USA) (Disc 1).chd", "psx/A (USA) (Disc 2).chd", "psx/A (USA).m3u", "psx/B (USA).chd"]
        groups = m3u.file_groups(keys)
        whole = ["psx/A (USA).m3u", "psx/A (USA) (Disc 1).chd", "psx/A (USA) (Disc 2).chd"]
        for k in whole:
            self.assertEqual(groups[k], whole)
        self.assertNotIn("psx/B (USA).chd", groups)  # a single-disc game is no group

    def test_three_discs_with_tags_in_order(self):
        keys = ["segacd/" + f for f in FAH + ["Fahrenheit (USA) (Disc 3) (Sega CD).chd", "Fahrenheit (USA) (Sega CD).m3u"]]
        self.assertEqual(m3u.file_groups(keys)[keys[2]],
                         ["segacd/Fahrenheit (USA) (Sega CD).m3u"] + keys[:3])

    def test_no_playlist_groups_the_discs(self):
        keys = ["gc/G (Disc 2).rvz", "gc/G (Disc 1).rvz"]
        self.assertEqual(m3u.file_groups(keys)["gc/G (Disc 2).rvz"], ["gc/G (Disc 1).rvz", "gc/G (Disc 2).rvz"])

    def test_subfolders_group_within_their_folder(self):
        keys = ["psx/x/A (Disc 1).chd", "psx/x/A (Disc 2).chd", "psx/x/A.m3u", "psx/y/A (Disc 1).chd", "psx/A.m3u"]
        groups = m3u.file_groups(keys)
        self.assertEqual(groups["psx/x/A.m3u"], ["psx/x/A.m3u", "psx/x/A (Disc 1).chd", "psx/x/A (Disc 2).chd"])
        self.assertNotIn("psx/y/A (Disc 1).chd", groups)
        self.assertNotIn("psx/A.m3u", groups)


class HiddenDiscsTest(unittest.TestCase):
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

    def disc_folder(self):
        os.mkdir(os.path.join(self.dir, ".multi-disc"))
        for f in FAH:
            open(os.path.join(self.dir, ".multi-disc", f), "w").close()

    def test_disc_keys_are_only_multi_disc_games(self):
        keys = ["psx/" + f for f in FAH] + ["psx/Single (USA).chd", "psx/Lone (USA) (Disc 1).chd"]
        self.assertEqual(m3u.disc_keys(keys), {"psx/" + f for f in FAH})

    def test_rom_rel_puts_discs_in_the_disc_folder(self):
        discs = {"psx/" + f for f in FAH}
        self.assertEqual(downloads.rom_rel("psx/" + FAH[0], False, ".multi-disc", discs), ".multi-disc/" + FAH[0])
        self.assertEqual(downloads.rom_rel("psx/Fahrenheit.m3u", False, ".multi-disc", discs), "Fahrenheit.m3u")
        self.assertEqual(downloads.rom_rel("psx/" + FAH[0], False), FAH[0])

    def test_hide_discs_moves_loose_discs(self):
        self.touch(*FAH)
        discs = {"psx/" + f for f in FAH}
        self.assertEqual(len(downloads.hide_discs(self.dir, ".multi-disc", discs, dry_run=True)), 2)
        self.assertEqual(sorted(os.listdir(self.dir)), sorted(FAH))
        downloads.hide_discs(self.dir, ".multi-disc", discs)
        self.assertEqual(os.listdir(self.dir), [".multi-disc"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, ".multi-disc"))), sorted(FAH))

    def test_prefix_playlists_points_at_the_discs_and_still_counts_as_current(self):
        self.disc_folder()
        original = "\n".join(FAH) + "\n"
        self.touch("Fahrenheit.m3u", text=original)
        self.assertEqual(m3u.prefix_playlists(self.dir, ".multi-disc"), 1)
        self.assertEqual(self.read("Fahrenheit.m3u"), "".join(f".multi-disc/{f}\n" for f in FAH))
        self.assertEqual(m3u.prefix_playlists(self.dir, ".multi-disc"), 0)
        path, size = os.path.join(self.dir, "Fahrenheit.m3u"), len(original.encode())
        self.assertTrue(downloads.is_current(path, size, ".multi-disc"))
        self.assertFalse(downloads.is_current(path, size + 1, ".multi-disc"))
        self.assertFalse(downloads.is_current(path, size))

    def test_find_extras_looks_in_the_disc_folder(self):
        self.disc_folder()
        self.touch("Fahrenheit.m3u", "Gone.m3u")
        keys = ["psx/" + f for f in FAH] + ["psx/Fahrenheit.m3u"]
        discs = {"psx/" + f for f in FAH}
        self.assertEqual(downloads.find_extras(self.dir, keys, disc_dir=".multi-disc", discs=discs),
                         [os.path.join(self.dir, "Gone.m3u")])
        self.assertEqual(downloads.find_extras(self.dir, keys[1:], disc_dir=".multi-disc", discs={keys[1]}),
                         [os.path.join(self.dir, "Gone.m3u"), os.path.join(self.dir, ".multi-disc", FAH[0])])

    def test_playlist_pass_leaves_the_disc_folder_alone(self):
        self.disc_folder()
        self.touch("Fahrenheit.m3u", text="".join(f".multi-disc/{f}\n" for f in FAH))
        self.assertEqual(m3u.plan_m3u(self.dir), [])


if __name__ == "__main__":
    unittest.main()
