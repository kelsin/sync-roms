import contextlib
import io
import os
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from sync_roms import chd, external, m3u, store  # noqa: E402

CD = {"chd": {"mode": "cd"}}
DVD = {"chd": {"mode": "dvd", "args": ["-c", "zlib"]}}
EXTRACT = {"chd": {"mode": "extract"}}
XISO = {"chd": {"mode": "xiso", "m3u": False}}
XISO_TAG = b"\0" * 31337 + b"in!xiso!2.7.1"
CUE = 'FILE "Game (Track 1).bin" BINARY\n  TRACK 01 MODE2/2352\nFILE "Game (Track 2).bin" BINARY\n'
GDI = '3\n1 0 4 2352 track01.bin 0\n2 600 0 2352 "track 02.raw" 0\n3 45000 4 2352 track03.bin 0\n'


class FakeTools:
    """Stands in for run_tool: chdman create writes the output, 7z x writes `archive` files into -o."""

    def __init__(self, archive=(), fail=()):
        self.calls, self.archive, self.fail = [], archive, fail

    def __call__(self, cmd, progress=None):
        self.calls.append(cmd)
        if cmd[0] == "7z":
            out = next(a for a in cmd if a.startswith("-o"))[2:]
            for name in self.archive:
                with open(os.path.join(out, name), "w") as f:
                    f.write(CUE if name.endswith(".cue") else "x")
        elif cmd[0] == "extract-xiso":
            mode = cmd[-2]
            if mode == "-r":  # like the real tool: the rewritten image is written into -d, -D deletes the original
                out = os.path.join(cmd[cmd.index("-d") + 1], os.path.basename(cmd[-1]))
                os.remove(cmd[-1])
                with open(out, "wb") as f:
                    f.write(XISO_TAG)
            return "xiso failed" if mode in self.fail else None
        elif cmd[1].startswith("create"):
            open(cmd[cmd.index("-o") + 1], "w").close()
        return f"{cmd[1]} failed" if cmd[1] in self.fail else None


class ChdTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.tools = {"7z": "7z", "chdman": "chdman", "extract-xiso": "extract-xiso", "np": 1}

    def touch(self, *names, text=""):
        for n in names:
            path = os.path.join(self.dir, n)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)

    def files(self):
        return sorted(os.listdir(self.dir))

    def test_sheet_tracks(self):
        self.touch("a.cue", text=CUE)
        self.touch("a.gdi", text=GDI)
        self.assertEqual(chd.sheet_tracks(os.path.join(self.dir, "a.cue")), ["Game (Track 1).bin", "Game (Track 2).bin"])
        self.assertEqual(chd.sheet_tracks(os.path.join(self.dir, "a.gdi")), ["track01.bin", "track 02.raw", "track03.bin"])

    def test_plan_finds_system_from_folder_names(self):
        folders = {"psx": CD, "gc": EXTRACT}
        self.touch("roms/psx/A.zip", "roms/psx/B.cue", "roms/psx/B (Track 1).bin", "roms/gc/C.7z", "roms/gc/D.iso",
                   "roms/gba/E.zip", "roms/psx/.dot.zip", "roms/psx/._A.zip", "roms/psx/.chd-x/F.iso", text=CUE)
        jobs = chd.plan_chd(os.path.join(self.dir, "roms"), folders)
        self.assertEqual([(os.path.basename(p), owned is None) for _, _, p, owned in jobs],
                         [("C.7z", True), (".dot.zip", True), ("A.zip", True), ("B.cue", False)])

    def test_dot_prefixed_discs_and_playlists_are_handled(self):
        self.touch(".G (Disc 1).chd", ".G (Disc 2).chd", ".G (Disc 2).chd.part")
        plan = m3u.plan_m3u(self.dir)
        self.assertEqual([(a, os.path.basename(p)) for a, p, _ in plan], [("create", ".G.m3u")])

    def test_plan_in_the_system_folder_itself(self):
        folder = os.path.join(self.dir, "PS")
        os.makedirs(folder)
        open(os.path.join(folder, "A.zip"), "w").close()
        jobs = chd.plan_chd(folder, {"ps": CD})
        self.assertEqual([(s, r) for s, r, _, _ in jobs], [(CD, folder)])

    def test_iso_used_by_a_sheet_is_not_converted_twice(self):
        self.touch("A.cue", text='FILE "A.iso" BINARY\n')
        self.touch("A.iso", "B.iso")
        images = chd.disc_images([os.path.join(self.dir, n) for n in ("A.cue", "A.iso", "B.iso")])
        self.assertEqual([os.path.basename(i) for i, _ in images], ["A.cue", "B.iso"])

    def test_dvd_systems_use_createdvd_for_iso_and_createcd_for_sheets(self):
        self.assertEqual(chd.chd_command_line("c", DVD["chd"], "g.iso", "g.chd", 4),
                         ["c", "createdvd", "-i", "g.iso", "-o", "g.chd", "-np", "4", "-c", "zlib"])
        self.assertEqual(chd.chd_command_line("c", DVD["chd"], "g.cue", "g.chd", 4), ["c", "createcd", "-i", "g.cue", "-o", "g.chd", "-np", "4"])

    def test_loose_image_is_converted_verified_and_cleaned_up(self):
        self.touch("Game.cue", text=CUE)
        self.touch("Game (Track 1).bin", "Game (Track 2).bin", "Other.bin")
        fake = FakeTools()
        with mock.patch.object(external, "run_tool", fake):
            error = chd.chd_image(self.tools, CD["chd"], os.path.join(self.dir, "Game.cue"),
                                  [os.path.join(self.dir, n) for n in ("Game.cue", "Game (Track 1).bin", "Game (Track 2).bin")])
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Game.chd", "Other.bin"])
        self.assertEqual([c[1] for c in fake.calls], ["createcd", "verify"])

    def test_chd_is_built_under_a_hidden_part_name_and_renamed_after_verify(self):
        self.touch("Game.iso")
        seen = []

        def fake(cmd, progress=None):
            if cmd[1] == "verify":
                seen.append(sorted(os.listdir(self.dir)))
            elif cmd[1].startswith("create"):
                open(cmd[cmd.index("-o") + 1], "w").close()

        with mock.patch.object(external, "run_tool", fake):
            self.assertIsNone(chd.make_chd(self.tools, CD["chd"], os.path.join(self.dir, "Game.iso"), os.path.join(self.dir, "Game.chd")))
        self.assertEqual(seen, [[".Game.chd.part", "Game.iso"]])
        self.assertEqual(self.files(), ["Game.chd", "Game.iso"])

    def test_stale_part_file_from_a_killed_run_is_replaced(self):
        self.touch("Game.iso", ".Game.chd.part", text="half")
        with mock.patch.object(external, "run_tool", FakeTools()):
            self.assertIsNone(chd.make_chd(self.tools, CD["chd"], os.path.join(self.dir, "Game.iso"), os.path.join(self.dir, "Game.chd")))
        self.assertEqual(sorted(os.listdir(self.dir)), ["Game.chd", "Game.iso"])
        self.assertEqual(os.path.getsize(os.path.join(self.dir, "Game.chd")), 0)

    def test_stale_extraction_folders_are_removed(self):
        self.touch("psx/.chd-abc123/Game.bin", "psx/Game.zip")
        chd.remove_stale_chd_temp(self.dir)
        self.assertEqual(os.listdir(os.path.join(self.dir, "psx")), ["Game.zip"])

    def test_stop_tools_ends_a_running_tool_and_blocks_new_ones(self):
        self.addCleanup(setattr, external, "_tools_stopped", False)
        result = []
        thread = threading.Thread(target=lambda: result.append(external.run_tool(["sleep", "30"])))
        thread.start()
        while not external._tool_procs:
            time.sleep(0.01)
        external.stop_tools()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(result[0])
        self.assertEqual(external.run_tool(["true"]), "interrupted")

    def test_failed_verify_keeps_the_originals_and_drops_the_chd(self):
        self.touch("Game.iso")
        with mock.patch.object(external, "run_tool", FakeTools(fail=("verify",))):
            error = chd.chd_image(self.tools, DVD["chd"], os.path.join(self.dir, "Game.iso"), [os.path.join(self.dir, "Game.iso")])
        self.assertEqual(error, "verify failed")
        self.assertEqual(self.files(), ["Game.iso"])

    def test_archive_is_converted_and_removed(self):
        self.touch("Game.zip")
        fake = FakeTools(archive=["Game.cue", "Game (Track 1).bin", "Game (Track 2).bin"])
        with mock.patch.object(external, "run_tool", fake):
            error = chd.chd_archive(self.tools, CD["chd"], os.path.join(self.dir, "Game.zip"))
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Game.chd"])

    def test_failed_archive_is_kept_and_leaves_no_temp_folder(self):
        self.touch("Game.zip")
        with mock.patch.object(external, "run_tool", FakeTools(archive=["Game.iso"], fail=("createdvd",))):
            error = chd.chd_archive(self.tools, DVD["chd"], os.path.join(self.dir, "Game.zip"))
        self.assertEqual(error, "createdvd failed")
        self.assertEqual(self.files(), ["Game.zip"])

    def test_archive_without_a_disc_image_is_kept(self):
        self.touch("Game.zip")
        with mock.patch.object(external, "run_tool", FakeTools(archive=["readme.txt"])):
            error = chd.chd_archive(self.tools, CD["chd"], os.path.join(self.dir, "Game.zip"))
        self.assertEqual(error, "no disc image in the archive")
        self.assertEqual(self.files(), ["Game.zip"])

    def test_extract_only_systems_keep_their_files_as_extracted(self):
        self.touch("Game.7z")
        with mock.patch.object(external, "run_tool", FakeTools(archive=["Game.rvz"])):
            error = chd.chd_archive(self.tools, EXTRACT["chd"], os.path.join(self.dir, "Game.7z"))
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Game.rvz"])

    def extract_with(self, files, links=()):
        def fake(cmd, progress=None):
            out = next(a for a in cmd if a.startswith("-o"))[2:]
            for name in files:
                os.makedirs(os.path.dirname(os.path.join(out, name)), exist_ok=True)
                with open(os.path.join(out, name), "w") as f:
                    f.write("x")
            for name in links:
                os.symlink(os.path.join(out, files[0]), os.path.join(out, name))
        return mock.patch.object(external, "run_tool", fake)

    def test_extract_mode_fails_on_duplicate_basenames(self):
        self.touch("Game.7z")
        with self.extract_with(["a/G.rvz", "b/G.rvz"]):
            error = chd.chd_archive(self.tools, EXTRACT["chd"], os.path.join(self.dir, "Game.7z"))
        self.assertEqual(error, "G.rvz appears more than once in the archive")
        self.assertEqual(self.files(), ["Game.7z"])

    def test_extract_mode_skips_symlinks_and_clashes_with_dangling_links(self):
        self.touch("Game.7z")
        with self.extract_with(["G.rvz"], links=["link.rvz"]):
            self.assertIsNone(chd.chd_archive(self.tools, EXTRACT["chd"], os.path.join(self.dir, "Game.7z")))
        self.assertEqual(self.files(), ["G.rvz"])
        self.touch("Game.7z")
        os.symlink(os.path.join(self.dir, "missing"), os.path.join(self.dir, "H.rvz"))
        with self.extract_with(["H.rvz"]):
            error = chd.chd_archive(self.tools, EXTRACT["chd"], os.path.join(self.dir, "Game.7z"))
        self.assertEqual(error, "H.rvz already exists")

    def test_sheets_naming_tracks_outside_their_folder_are_skipped(self):
        evil = 'FILE "../secret.bin" BINARY\n'
        for i, text in enumerate((evil, 'FILE "/etc/hosts" BINARY\n', 'FILE "a\\..\\b.bin" BINARY\n', 'FILE "sub/t.bin" BINARY\n')):
            self.touch(f"s{i}.cue", text=text)
        self.touch("ok.cue", text=CUE)
        images = chd.disc_images([os.path.join(self.dir, f) for f in sorted(os.listdir(self.dir))])
        self.assertEqual([os.path.basename(i) for i, _ in images], ["ok.cue"])

    def test_skipped_sheets_are_reported_and_archives_allow_subfolder_tracks(self):
        self.touch("s.cue", text='FILE "sub/t.bin" BINARY\n')
        path = os.path.join(self.dir, "s.cue")
        skipped = []
        self.assertEqual(chd.disc_images([path], skipped=skipped), [])
        self.assertEqual(skipped, [path])
        self.assertEqual([i for i, _ in chd.disc_images([path], strict=False)], [path])

    def test_extract_mode_compares_contents_and_case_insensitive_names(self):
        self.touch("Game.7z")
        self.touch("G.rvz", text="y")  # same size as the extracted "x", different content
        with self.extract_with(["G.rvz"]):
            error = chd.chd_archive(self.tools, EXTRACT["chd"], os.path.join(self.dir, "Game.7z"))
        self.assertEqual(error, "G.rvz already exists")
        os.remove(os.path.join(self.dir, "G.rvz"))
        with self.extract_with(["a/G.rvz", "b/g.RVZ"]):
            error = chd.chd_archive(self.tools, EXTRACT["chd"], os.path.join(self.dir, "Game.7z"))
        self.assertIn("appears more than once", error)

    def test_archive_fails_when_two_discs_map_to_one_chd(self):
        self.touch("Game.zip")
        with self.extract_with(["a/G.iso", "b/g.ISO"]):
            error = chd.chd_archive(self.tools, DVD["chd"], os.path.join(self.dir, "Game.zip"))
        self.assertEqual(error, "two discs in the archive would make the same .chd")
        self.assertEqual(self.files(), ["Game.zip"])

    def test_chd_image_never_deletes_its_own_output(self):
        self.touch("Game.cue", "Game.chd")
        with mock.patch.object(external, "run_tool", FakeTools()):
            chd.chd_image(self.tools, CD["chd"], os.path.join(self.dir, "Game.cue"),
                          [os.path.join(self.dir, n) for n in ("Game.cue", "Game.chd")])
        self.assertEqual(self.files(), ["Game.chd"])

    def test_xiso_plan_skips_optimized_isos_and_other_files(self):
        self.touch("xbox/A.iso", "xbox/B.zip", "xbox/C.cue")
        with open(os.path.join(self.dir, "xbox", "Done.iso"), "wb") as f:
            f.write(XISO_TAG)
        jobs = chd.plan_chd(self.dir, {"xbox": XISO})
        self.assertEqual([(os.path.basename(p), owned is None) for _, _, p, owned in jobs], [("B.zip", True), ("A.iso", False)])

    def test_loose_iso_is_rewritten_in_place(self):
        self.touch("Game.iso", text="redump")
        fake = FakeTools()
        with mock.patch.object(external, "run_tool", fake):
            error = chd.chd_image(self.tools, XISO["chd"], os.path.join(self.dir, "Game.iso"), [os.path.join(self.dir, "Game.iso")])
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Game.iso"])
        self.assertTrue(chd.is_optimized_xiso(os.path.join(self.dir, "Game.iso")))
        self.assertEqual([c[-2] for c in fake.calls], ["-r", "-l"])

    def test_failed_xiso_rewrite_leaves_the_iso_untouched(self):
        self.touch("Game.iso", text="redump")
        with mock.patch.object(external, "run_tool", FakeTools(fail=("-l",))):
            error = chd.chd_image(self.tools, XISO["chd"], os.path.join(self.dir, "Game.iso"), [os.path.join(self.dir, "Game.iso")])
        self.assertEqual(error, "xiso failed")
        self.assertEqual(self.files(), ["Game.iso"])
        with open(os.path.join(self.dir, "Game.iso")) as f:
            self.assertEqual(f.read(), "redump")

    def test_archive_of_an_iso_is_converted_and_removed(self):
        self.touch("Game.zip")
        with mock.patch.object(external, "run_tool", FakeTools(archive=["Game.iso", "readme.txt"])):
            error = chd.chd_archive(self.tools, XISO["chd"], os.path.join(self.dir, "Game.zip"))
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Game.iso"])
        self.assertTrue(chd.is_optimized_xiso(os.path.join(self.dir, "Game.iso")))

    def test_archive_without_an_iso_or_onto_an_existing_one_is_kept(self):
        self.touch("Game.zip")
        with mock.patch.object(external, "run_tool", FakeTools(archive=["readme.txt"])):
            self.assertEqual(chd.chd_archive(self.tools, XISO["chd"], os.path.join(self.dir, "Game.zip")), "no iso in the archive")
        self.touch("Game.iso")
        with mock.patch.object(external, "run_tool", FakeTools(archive=["Game.iso"])):
            self.assertEqual(chd.chd_archive(self.tools, XISO["chd"], os.path.join(self.dir, "Game.zip")), "Game.iso already exists")
        self.assertEqual(self.files(), ["Game.iso", "Game.zip"])

    def test_shipped_chd_settings(self):
        systems = {s["bucket"]: s for s in store.repo_json("systems")}
        self.assertEqual(systems["psx"]["chd"], {"mode": "cd"})
        self.assertEqual(systems["wii"]["chd"], {"mode": "extract"})
        self.assertFalse(systems["3do"]["chd"]["m3u"])
        self.assertEqual(systems["xbox"]["chd"], {"mode": "xiso", "m3u": False})
        self.assertNotIn("chd", systems["gba"])
        folders = chd.chd_folders(systems.values())
        self.assertIs(folders["megacd"], systems["segacd"])
        self.assertIs(folders["ps"], systems["psx"])

    def test_command_creates_playlists_for_converted_multi_disc_games(self):
        self.touch("psx/Game (Disc 1).zip", "psx/Game (Disc 2).zip")
        fake = FakeTools(archive=["x.iso"])

        def fake_run(cmd, progress=None):
            if cmd[0] == "7z":
                out = next(a for a in cmd if a.startswith("-o"))[2:]
                name = os.path.basename(cmd[-1]).replace(".zip", ".iso")
                open(os.path.join(out, name), "w").close()
                return None
            return fake(cmd, progress)

        args = SimpleNamespace(chd=os.path.join(self.dir, "psx"), dry_run=False)
        with mock.patch.object(external, "run_tool", fake_run), mock.patch.object(external, "find_tool", lambda t: t):
            self.assertEqual(chd.chd_command(args), 0)
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, "psx"))), ["Game (Disc 1).chd", "Game (Disc 2).chd", "Game.m3u"])

    def test_jobs_share_the_cores(self):
        self.touch("psx/A.zip", "psx/B.zip", "psx/C.zip")
        calls = []

        def fake_run(cmd, progress=None):
            calls.append(cmd)
            if cmd[0] == "7z":
                out = next(a for a in cmd if a.startswith("-o"))[2:]
                open(os.path.join(out, os.path.basename(cmd[-1]).replace(".zip", ".iso")), "w").close()
            elif cmd[1].startswith("create"):
                open(cmd[cmd.index("-o") + 1], "w").close()

        args = SimpleNamespace(chd=self.dir, dry_run=False)
        with mock.patch.object(external, "run_tool", fake_run), mock.patch.object(external, "find_tool", lambda t: t), \
                mock.patch.object(os, "cpu_count", return_value=6):
            self.assertEqual(chd.chd_command(args), 0)
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, "psx"))), ["A.chd", "B.chd", "C.chd"])
        self.assertEqual({c[c.index("-np") + 1] for c in calls if c[1:2] == ["createcd"]}, {"2"})

    def test_playlists_are_fixed_even_when_nothing_converts(self):
        self.touch("psx/Game (Disc 1).chd", "psx/Game (Disc 2).chd", "gc/Wii.rvz")
        args = SimpleNamespace(chd=self.dir, dry_run=False)
        self.assertEqual(chd.chd_command(args), 0)
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, "psx"))), ["Game (Disc 1).chd", "Game (Disc 2).chd", "Game.m3u"])

    def test_dry_run_previews_playlists_without_writing_them(self):
        self.touch("psx/Game (Disc 1).chd", "psx/Game (Disc 2).chd")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(chd.chd_command(SimpleNamespace(chd=self.dir, dry_run=True)), 0)
        self.assertIn("create Game.m3u", out.getvalue())
        self.assertEqual(len(os.listdir(os.path.join(self.dir, "psx"))), 2)

    def test_no_playlists_for_3do_or_extract_only_systems(self):
        self.touch("3do/Game (Disc 1).chd", "3do/Game (Disc 2).chd")
        self.assertEqual(chd.chd_command(SimpleNamespace(chd=self.dir, dry_run=False)), 0)
        self.assertEqual(len(os.listdir(os.path.join(self.dir, "3do"))), 2)

    def test_run_tool_reports_chdman_percentages_and_the_error_line(self):
        code = "import sys; sys.stderr.write('Compressing, 12.5% complete... \\rCompressing, 50.0% complete... \\rbad input\\n'); sys.exit(1)"
        seen = []
        self.assertEqual(external.run_tool([sys.executable, "-c", code], seen.append), "bad input")
        self.assertEqual(seen, [12.5, 50.0])

    def test_make_chd_reports_create_then_verify_progress(self):
        self.touch("Game.iso")
        seen = []

        def fake(cmd, progress=None):
            if cmd[1].startswith("create"):
                open(cmd[cmd.index("-o") + 1], "w").close()
                progress(50)
            else:
                progress(50)

        with mock.patch.object(external, "run_tool", fake):
            chd.make_chd(self.tools, CD["chd"], os.path.join(self.dir, "Game.iso"), os.path.join(self.dir, "Game.chd"), seen.append)
        self.assertEqual(len(seen), 2)
        self.assertAlmostEqual(seen[0], 0.45)
        self.assertAlmostEqual(seen[1], 0.95)

    def test_dry_run_changes_nothing_and_needs_no_tools(self):
        self.touch("psx/Game.zip")
        args = SimpleNamespace(chd=self.dir, dry_run=True)
        with mock.patch.object(external, "find_tool", lambda t: None):
            self.assertEqual(chd.chd_command(args), 0)
        self.assertEqual(os.listdir(os.path.join(self.dir, "psx")), ["Game.zip"])


class UnzipArchiveTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def touch(self, name, text=""):
        with open(os.path.join(self.dir, name), "w") as f:
            f.write(text)

    def make_zip(self, **files):
        path = os.path.join(self.dir, "a.zip")
        with zipfile.ZipFile(path, "w") as z:
            for name, data in files.items():
                z.writestr(name, data)
        return path

    def test_existing_file_is_not_overwritten(self):
        path = self.make_zip(**{"G.iso": "new"})
        self.touch("G.iso", "older")
        self.assertEqual(chd.unzip_archive(path), "G.iso already exists")
        with open(os.path.join(self.dir, "G.iso")) as f:
            self.assertEqual(f.read(), "older")
        self.assertTrue(os.path.exists(path))

    def test_leftover_archive_is_removed_when_already_extracted(self):
        path = self.make_zip(**{"G.iso": "same"})
        self.touch("G.iso", "same")
        self.assertIsNone(chd.unzip_archive(path))
        self.assertFalse(os.path.exists(path))
        self.assertEqual(os.listdir(self.dir), ["G.iso"])

    def test_duplicate_basenames_in_an_archive_fail(self):
        path = self.make_zip(**{"a/G.iso": "1", "b/G.iso": "2"})
        self.assertEqual(chd.unzip_archive(path), "G.iso appears more than once in the archive")
        self.assertTrue(os.path.exists(path))
        self.assertEqual(os.listdir(self.dir), ["a.zip"])

    def test_symlinks_in_an_archive_are_skipped(self):
        path = os.path.join(self.dir, "a.7z")
        open(path, "w").close()

        def fake(cmd, progress=None):
            out = next(a for a in cmd if a.startswith("-o"))[2:]
            with open(os.path.join(out, "G.iso"), "w") as f:
                f.write("x")
            os.symlink(os.path.join(out, "G.iso"), os.path.join(out, "link.iso"))
        with mock.patch.object(external, "find_tool", return_value="7z"), mock.patch.object(external, "run_tool", fake):
            self.assertIsNone(chd.unzip_archive(path))
        self.assertEqual(sorted(os.listdir(self.dir)), ["G.iso"])

if __name__ == "__main__":
    unittest.main()
