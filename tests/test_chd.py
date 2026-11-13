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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import chd, external, m3u, runtime, store, ui  # noqa: E402

CD = {"chd": {"mode": "cd"}}
DVD = {"chd": {"mode": "dvd", "codec": "zlib"}}
PS3 = {"chd": {"mode": "dvd", "codec": "zstd", "keep": [".pkg", ".rap", ".dkey", ".key"]}}
EXTRACT = {"chd": {"mode": "extract"}}
XISO = {"chd": {"mode": "xiso", "m3u": False}}
ZAR = {"chd": {"mode": "zar", "m3u": False}}
XISO_TAG = b"\0" * 31337 + b"in!xiso!2.7.1"
CUE = 'FILE "Game (Track 1).bin" BINARY\n  TRACK 01 MODE2/2352\nFILE "Game (Track 2).bin" BINARY\n'
GDI = '3\n1 0 4 2352 track01.bin 0\n2 600 0 2352 "track 02.raw" 0\n3 45000 4 2352 track03.bin 0\n'


class FakeTools:
    """Stands in for run_tool: chdman create writes the output, 7z x writes `archive` files into -o."""

    def __init__(self, archive=(), fail=()):
        self.calls, self.archive, self.fail = [], archive, fail

    def __call__(self, cmd, progress=None, tty=False):
        self.calls.append(cmd)
        if cmd[0] in ("7z", "unar"):
            out = cmd[cmd.index("-o") + 1] if cmd[0] == "unar" else next(a for a in cmd if a.startswith("-o"))[2:]
            names = self.archive.get(os.path.basename(cmd[-1]), ()) if isinstance(self.archive, dict) else self.archive
            for name in names:
                with open(os.path.join(out, name), "w") as f:
                    f.write(CUE if name.endswith(".cue") else "x")
        elif cmd[0] == "iso2zar":
            if "zar" in self.fail:
                return "zar failed"
            if "empty" not in self.fail:
                with open(cmd[2], "wb") as f:
                    f.write(b"zar")
        elif cmd[0] == "extract-xiso":
            mode = cmd[-2]
            if mode == "-r" and not chd.is_optimized_xiso(cmd[-1]):  # like the real tool: an optimized image is skipped,
                out = os.path.join(cmd[cmd.index("-d") + 1], os.path.basename(cmd[-1]))  # else rewritten into -d, -D deletes it
                os.remove(cmd[-1])
                with open(out, "wb") as f:
                    f.write(XISO_TAG)
            return "xiso failed" if mode in self.fail else None
        elif cmd[1].startswith("create") or cmd[1] == "copy":
            open(cmd[cmd.index("-o") + 1], "w").close()
        return f"{cmd[1]} failed" if cmd[1] in self.fail else None


class ChdTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.realpath(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        systemp = tempfile.TemporaryDirectory()  # stale_local_scratch looks at this, never at the real temp folder
        self.addCleanup(systemp.cleanup)
        patch = mock.patch.object(tempfile, "tempdir", os.path.realpath(systemp.name))
        patch.start()
        self.addCleanup(patch.stop)
        self.tools = {"7z": "7z", "chdman": "chdman", "extract-xiso": "extract-xiso", "iso2zar": "iso2zar", "np": 1}

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
        self.assertEqual(chd.chd_command_line("c", DVD["chd"], "g.cue", "g.chd", 4), ["c", "createcd", "-i", "g.cue", "-o", "g.chd", "-np", "4", "-c", "cdzl"])
        self.assertEqual(chd.chd_command_line("c", CD["chd"], "g.cue", "g.chd", 4), ["c", "createcd", "-i", "g.cue", "-o", "g.chd", "-np", "4"])

    def test_chd_with_another_codec_is_recompressed_to_zlib(self):
        self.touch("Game.chd")
        path = os.path.join(self.dir, "Game.chd")
        info = {"dvd": "Compression:   lzma (LZMA), zlib (Deflate)\nMetadata Tag='DVD '", "cd": "Compression:   cdlz (CD LZMA)\nMetadata Tag='CHT2'",
                "zlib": "Compression:   zlib (Deflate)\nMetadata Tag='DVD '", "cdzl": "Compression:   cdzl (CD Deflate)\nMetadata Tag='CHT2'"}
        for kind, wanted in (("dvd", "zlib"), ("cd", "cdzl"), ("zlib", None), ("cdzl", None)):
            with mock.patch.object(external, "tool_output", return_value=info[kind]):
                self.assertEqual(chd.wrong_codec("chdman", DVD["chd"], path), wanted)
        fake = FakeTools()
        with mock.patch.object(external, "tool_output", return_value=info["cd"]), mock.patch.object(external, "run_tool", fake), \
                mock.patch.object(external, "find_tool", return_value="chdman"):
            self.assertIsNone(chd.chd_image(self.tools, DVD["chd"], path, [path]))
            self.assertEqual([c[1] for c in fake.calls], ["copy", "verify"])
            self.assertEqual(fake.calls[0][fake.calls[0].index("-c") + 1], "cdzl")
            self.assertEqual(self.files(), ["Game.chd"])
            jobs = chd.plan_chd(self.dir, {os.path.basename(self.dir).lower(): DVD})
        self.assertEqual([j[2] for j in jobs], [path])

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
        stale = []
        chd.plan_chd(self.dir, {}, stale=stale)
        self.assertEqual(stale, [os.path.join(self.dir, "psx", ".chd-abc123")])
        chd.remove_stale_chd_temp(stale)
        self.assertEqual(os.listdir(os.path.join(self.dir, "psx")), ["Game.zip"])

    def test_stop_tools_ends_a_running_tool_and_blocks_new_ones(self):
        self.addCleanup(setattr, external, "_tools_stopped", False)
        result = []
        thread = threading.Thread(target=lambda: result.append(external.run_tool(["sleep", "30"])))
        thread.start()
        deadline = time.monotonic() + 5
        while not external._tool_procs:
            if time.monotonic() > deadline:
                self.fail("the tool never started")
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

    def test_archive_beside_its_existing_chd_is_verified_and_removed(self):
        self.touch("Game.zip")
        self.touch("Game.chd")
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

    def test_archive_disc_keys_are_kept_beside_the_chd(self):
        self.touch("Game.zip")
        with mock.patch.object(external, "run_tool", FakeTools(archive=["Game.iso", "Game.dkey", "readme.txt"])) as fake:
            error = chd.chd_archive(self.tools, PS3["chd"], os.path.join(self.dir, "Game.zip"))
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Game.chd", "Game.dkey"])
        self.assertEqual([c[-2:] for c in fake.calls if c[1] == "createdvd"], [["-c", "zstd"]])

    def test_psn_archive_is_extracted_to_its_pkg_and_rap_files(self):
        self.touch("Game.rar")
        with mock.patch.object(external, "run_tool", FakeTools(archive=["Game.pkg", "UP0001.rap", "cover.jpg"])) as fake:
            error = chd.chd_archive(self.tools, PS3["chd"], os.path.join(self.dir, "Game.rar"))
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Game.pkg", "UP0001.rap"])
        self.assertFalse([c for c in fake.calls if c[0] == "chdman"])

    def test_nested_archives_are_extracted(self):
        self.touch("Game.rar")
        fake = FakeTools(archive={"Game.rar": ["Inner.rar", "Inner.r00", "cover.jpg"], "Inner.rar": ["Game.pkg", "Disc.zip"],
                                  "Disc.zip": ["Disc.iso"]})
        with mock.patch.object(external, "run_tool", fake):
            error = chd.chd_archive(self.tools, PS3["chd"], os.path.join(self.dir, "Game.rar"))
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Disc.chd", "Game.pkg"])

    def test_failed_inner_archive_keeps_the_archive(self):
        self.touch("Game.rar")
        fake = FakeTools(archive={"Game.rar": ["Inner.rar"]})
        real = fake.__call__
        with mock.patch.object(external, "run_tool", lambda cmd, *a, **k: "bad" if cmd[-1].endswith("Inner.rar") else real(cmd)):
            error = chd.chd_archive(self.tools, PS3["chd"], os.path.join(self.dir, "Game.rar"))
        self.assertEqual(error, "Inner.rar in the archive: bad")
        self.assertEqual(self.files(), ["Game.rar"])

    def test_rars_use_unar_when_it_is_installed(self):
        self.touch("Game.rar")
        fake = FakeTools(archive={"Game.rar": ["Disc.zip"], "Disc.zip": ["Game.pkg"]})
        with mock.patch.object(external, "run_tool", fake):
            error = chd.chd_archive(dict(self.tools, unar="unar"), PS3["chd"], os.path.join(self.dir, "Game.rar"))
        self.assertIsNone(error)
        self.assertEqual([c[0] for c in fake.calls], ["unar", "7z"])
        self.assertEqual(self.files(), ["Game.pkg"])

    def test_extract_only_systems_keep_inner_archives(self):
        self.touch("Game.7z")
        with mock.patch.object(external, "run_tool", FakeTools(archive={"Game.7z": ["Disk.zip"]})):
            error = chd.chd_archive(self.tools, EXTRACT["chd"], os.path.join(self.dir, "Game.7z"))
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Disk.zip"])

    def test_rar_archives_are_planned_for_cd_only(self):
        self.touch("ps3/Game.rar", "ps3/Game.pkg")
        jobs = chd.plan_chd(self.dir, chd.chd_folders([dict(PS3, folders={"esde": "ps3"})]))
        self.assertEqual([(j[2], j[3]) for j in jobs], [(os.path.join(self.dir, "ps3", "Game.rar"), None)])
        self.assertNotIn(".rar", external.ARCHIVE_EXTS)

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

    def test_zar_plan_takes_every_iso(self):
        self.touch("xbox360/A.iso", "xbox360/B.zip", "xbox360/C.zar")
        jobs = chd.plan_chd(self.dir, {"xbox360": ZAR})
        self.assertEqual([(os.path.basename(p), owned is None) for _, _, p, owned in jobs], [("B.zip", True), ("A.iso", False)])

    def test_loose_iso_becomes_a_zar_and_is_removed(self):
        self.touch("Game.iso", text="redump")
        with mock.patch.object(external, "run_tool", FakeTools()):
            error = chd.chd_image(self.tools, ZAR["chd"], os.path.join(self.dir, "Game.iso"), [os.path.join(self.dir, "Game.iso")])
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Game.zar"])

    def test_failed_or_empty_zar_keeps_the_iso(self):
        for fail, message in (("zar", "zar failed"), ("empty", "iso2zar wrote nothing")):
            self.touch("Game.iso", text="redump")
            with mock.patch.object(external, "run_tool", FakeTools(fail=(fail,))):
                error = chd.chd_image(self.tools, ZAR["chd"], os.path.join(self.dir, "Game.iso"), [os.path.join(self.dir, "Game.iso")])
            self.assertEqual(error, message)
            self.assertEqual(self.files(), ["Game.iso"])

    def test_archive_of_an_iso_becomes_a_zar(self):
        self.touch("Game.zip")
        with mock.patch.object(external, "run_tool", FakeTools(archive=["Game.iso", "readme.txt"])):
            error = chd.chd_archive(self.tools, ZAR["chd"], os.path.join(self.dir, "Game.zip"))
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Game.zar"])

    def test_zar_archive_without_an_iso_or_onto_an_existing_zar_is_kept(self):
        self.touch("Game.zip")
        with mock.patch.object(external, "run_tool", FakeTools(archive=["readme.txt"])):
            self.assertEqual(chd.chd_archive(self.tools, ZAR["chd"], os.path.join(self.dir, "Game.zip")), "no iso in the archive")
        self.touch("Game.zar")
        with mock.patch.object(external, "run_tool", FakeTools(archive=["Game.iso"])):
            self.assertEqual(chd.chd_archive(self.tools, ZAR["chd"], os.path.join(self.dir, "Game.zip")), "Game.zar already exists")
        self.assertEqual(self.files(), ["Game.zar", "Game.zip"])

    def test_shipped_chd_settings(self):
        systems = {s["bucket"]: s for s in store.repo_json("systems")}
        self.assertEqual(systems["psx"]["chd"], {"mode": "cd"})
        self.assertEqual(systems["wii"]["chd"], {"mode": "extract"})
        self.assertEqual(systems["ps2"]["chd"], {"mode": "dvd", "codec": "zlib"})
        self.assertEqual(systems["ps3"]["chd"], PS3["chd"])
        self.assertFalse(systems["3do"]["chd"]["m3u"])
        self.assertEqual(systems["xbox"]["chd"], {"mode": "xiso", "m3u": False})
        self.assertEqual(systems["xbox360"]["chd"], {"mode": "zar", "m3u": False})
        self.assertEqual(systems["pc98"]["chd"], {"mode": "extract", "m3u": False})
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

    def local_temp(self, free, other_device=True, target_free=10 ** 12):
        """Patches the system temp folder to a folder of its own, on another device when other_device, with free bytes
        left (target_free on every other volume)."""
        local = os.path.join(self.dir, "local")
        os.makedirs(local, exist_ok=True)
        real_stat = os.stat

        def stat(path, *a, **k):
            r = real_stat(path, *a, **k)
            if other_device and os.fspath(path) == local:
                return os.stat_result((r.st_mode, r.st_ino, r.st_dev + 1, *tuple(r)[3:]))
            return r

        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(tempfile, "tempdir", local))
        stack.enter_context(mock.patch.object(os, "stat", stat))
        stack.enter_context(mock.patch.object(chd.shutil, "disk_usage",
                                              lambda p: SimpleNamespace(free=free if os.fspath(p) == local else target_free)))
        return local, stack

    def zip_of(self, name, **files):
        os.makedirs(os.path.dirname(os.path.join(self.dir, name)), exist_ok=True)
        with zipfile.ZipFile(os.path.join(self.dir, name), "w") as z:
            for n, data in files.items():
                z.writestr(n, data)

    def run_convert(self, root, cpus=4):
        calls = []

        def fake_run(cmd, progress=None, tty=False):
            calls.append(cmd)
            return FakeTools(archive=["Game.iso"])(cmd, progress, tty) if cmd[0] == "7z" else FakeTools()(cmd, progress, tty)

        with mock.patch.object(external, "run_tool", fake_run), mock.patch.object(external, "find_tool", lambda t: t), \
                mock.patch.object(os, "cpu_count", return_value=cpus), contextlib.redirect_stdout(io.StringIO()) as out:
            code = chd.chd_command(SimpleNamespace(chd=root, dry_run=False))
        return code, calls, out.getvalue()

    def test_archive_unpacks_to_local_temp_on_another_device_with_room(self):
        self.zip_of("psx/Game.zip", **{"Game.iso": "x" * 100})
        local, stack = self.local_temp(free=10 ** 12)
        with stack:
            code, calls, _ = self.run_convert(os.path.join(self.dir, "psx"))
        self.assertEqual(code, 0)
        unpack = next(a for a in calls[0] if a.startswith("-o"))[2:]
        self.assertEqual(os.path.dirname(unpack), local)
        create = next(c for c in calls if c[1:2] == ["createcd"])
        self.assertEqual(os.path.dirname(create[create.index("-i") + 1]), unpack)
        self.assertEqual(create[create.index("-o") + 1], os.path.join(self.dir, "psx", ".Game.chd.part"))
        verify = next(c for c in calls if c[1:2] == ["verify"])
        self.assertEqual(verify[-1], os.path.join(self.dir, "psx", ".Game.chd.part"))
        self.assertEqual(os.listdir(os.path.join(self.dir, "psx")), ["Game.chd"])
        self.assertEqual(os.listdir(local), [])

    def test_archive_unpacks_beside_itself_without_room_on_the_same_device_or_for_extraction(self):
        cases = {"no room": (99, True, "psx", "Game.zip"), "no margin": (2 ** 30 + 99, True, "psx", "Game.zip"), "same device": (10 ** 12, False, "psx", "Game.zip"),
                 "extraction": (10 ** 12, True, "gc", "Game.zip"), "size unknown": (10 ** 12, True, "psx", "Game.7z")}
        for case, (free, other, folder, name) in cases.items():
            with self.subTest(case):
                path = os.path.join(case, folder, name)
                self.zip_of(path, **{"Game.iso": "x" * 100}) if name.endswith(".zip") else self.touch(path)
                _, stack = self.local_temp(free=free, other_device=other)
                with stack, mock.patch.object(chd, "chd_folders", lambda s: {"psx": CD, "gc": EXTRACT}), \
                        mock.patch.object(external, "tool_output", return_value=None):
                    code, calls, _ = self.run_convert(os.path.join(self.dir, case, folder))
                self.assertEqual(code, 0)
                unpack = next(a for a in calls[0] if a.startswith("-o"))[2:]
                self.assertEqual(os.path.dirname(unpack), os.path.join(self.dir, case, folder))

    def test_unpacked_size_comes_from_the_listing(self):
        self.zip_of("a.zip", **{"A.cue": "c" * 10, "A.bin": "b" * 90})
        self.zip_of("nested.zip", **{"A.iso": "x", "Disc.zip": "z"})
        self.touch("a.rar", "a.7z")
        listing = "Path = a.7z\nType = 7z\n\n----------\nPath = A.iso\nFolder = -\nSize = 4000\n\nPath = sub\nFolder = +\nSize = 0\n\n"
        with mock.patch.object(external, "tool_output", return_value=listing) as out:
            self.assertEqual(chd.unpacked_size(self.tools, os.path.join(self.dir, "a.7z")), 4000)
            self.assertEqual(out.call_args[0][0][:3], ["7z", "l", "-slt"])
            self.assertEqual(chd.unpacked_size(self.tools, os.path.join(self.dir, "a.zip")), 100)
            self.assertEqual(out.call_count, 1)  # a zip is read without the tool
        self.assertIsNone(chd.unpacked_size(self.tools, os.path.join(self.dir, "nested.zip")))  # inner archives grow it
        self.assertIsNone(chd.unpacked_size(self.tools, os.path.join(self.dir, "a.rar")))
        with mock.patch.object(external, "tool_output", return_value=None):
            self.assertIsNone(chd.unpacked_size(self.tools, os.path.join(self.dir, "a.7z")))

    def test_failed_archive_leaves_nothing_in_local_scratch(self):
        self.touch("Game.zip")
        local = os.path.join(self.dir, "local")
        os.makedirs(local)
        with mock.patch.object(external, "run_tool", FakeTools(archive=["Game.iso"], fail=("createdvd",))):
            error = chd.chd_archive(self.tools, DVD["chd"], os.path.join(self.dir, "Game.zip"), scratch=local)
        self.assertEqual(error, "createdvd failed")
        self.assertEqual(self.files(), ["Game.zip", "local"])
        self.assertEqual(os.listdir(local), [])

    def test_kept_files_reach_their_names_only_once_moved_and_a_failed_move_is_an_error(self):
        local = os.path.join(self.dir, "local")
        os.makedirs(local)
        real_move, seen = chd.shutil.move, []

        def move(src, dst):
            seen.append((os.path.basename(dst), os.path.exists(os.path.join(self.dir, "Game.pkg"))))
            return real_move(src, dst)

        def full(src, dst):
            with open(dst, "w") as f:
                f.write("half")
            raise OSError(28, "No space left on device")

        for fake_move in (move, full):
            self.touch("Game.zip")
            with mock.patch.object(external, "run_tool", FakeTools(archive=["Game.iso", "Game.pkg"])), \
                    mock.patch.object(chd.shutil, "move", fake_move):
                error = chd.chd_archive(self.tools, PS3["chd"], os.path.join(self.dir, "Game.zip"), scratch=local)
            if fake_move is move:
                self.assertIsNone(error)
                self.assertEqual(seen, [(".Game.pkg.part", False)])
                self.assertTrue(external.own_temp(seen[0][0]))
                self.assertEqual(self.files(), ["Game.chd", "Game.pkg", "local"])
                os.remove(os.path.join(self.dir, "Game.pkg"))
            else:
                self.assertEqual(error, "[Errno 28] No space left on device")
                self.assertEqual(self.files(), ["Game.chd", "Game.zip", "local"])
            self.assertEqual(os.listdir(local), [])

    def test_archive_iso_is_rewritten_without_a_copy(self):
        self.touch("Game.zip")
        local = os.path.join(self.dir, "local")
        os.makedirs(local)
        fake = FakeTools(archive=["Game.iso"])
        with mock.patch.object(external, "run_tool", fake), mock.patch.object(chd.shutil, "copyfile", side_effect=AssertionError("copied")):
            error = chd.chd_archive(self.tools, XISO["chd"], os.path.join(self.dir, "Game.zip"), scratch=local)
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Game.iso", "local"])
        self.assertTrue(chd.is_optimized_xiso(os.path.join(self.dir, "Game.iso")))
        rewrite = next(c for c in fake.calls if "-r" in c)
        self.assertEqual(os.path.dirname(os.path.dirname(rewrite[-1])), local)  # read from scratch, written on the target
        self.assertEqual(os.path.dirname(rewrite[rewrite.index("-d") + 1]), self.dir)
        self.assertEqual(os.listdir(local), [])

    def test_archive_of_an_optimized_iso_is_moved_out_unchanged(self):
        self.touch("Game.zip")
        local = os.path.join(self.dir, "local")
        os.makedirs(local)

        def fake(cmd, progress=None, tty=False):
            if cmd[0] == "7z":
                with open(os.path.join(next(a for a in cmd if a.startswith("-o"))[2:], "Game.iso"), "wb") as f:
                    f.write(XISO_TAG)
                return None
            return FakeTools()(cmd, progress, tty)

        with mock.patch.object(external, "run_tool", fake):
            error = chd.chd_archive(self.tools, XISO["chd"], os.path.join(self.dir, "Game.zip"), scratch=local)
        self.assertIsNone(error)
        self.assertEqual(self.files(), ["Game.iso", "local"])
        self.assertTrue(chd.is_optimized_xiso(os.path.join(self.dir, "Game.iso")))
        self.assertEqual(os.listdir(local), [])

    def test_jobs_at_once_are_capped_by_free_space(self):
        self.touch("psx/A.iso", "psx/B.iso", "psx/C.iso", text="x" * 100)
        for target_free, workers, np in ((250, 2, "3"), (50, 1, "6"), (10 ** 12, 3, "2")):
            with self.subTest(target_free=target_free):
                _, stack = self.local_temp(free=10 ** 12, target_free=target_free)
                with stack:
                    code, calls, out = self.run_convert(os.path.join(self.dir, "psx"), cpus=6)
                self.assertEqual(code, 0)
                self.assertIn(f"{workers} at a time", out)
                self.assertEqual({c[c.index("-np") + 1] for c in calls if c[1:2] == ["createcd"]}, {np})
                for n in ("A", "B", "C"):
                    os.remove(os.path.join(self.dir, "psx", n + ".chd"))
                    self.touch(f"psx/{n}.iso", text="x" * 100)

    def test_local_scratch_of_a_run_no_longer_running_is_removed(self):
        local, stack = self.local_temp(free=10 ** 12)
        dead, mine, other = (os.path.join(local, n) for n in (".chd-99999999-ab", f".chd-{os.getpid()}-cd", "keep"))
        for d in (dead, mine, other):
            os.makedirs(d)
        self.touch("psx/Game.iso")
        with stack:
            self.run_convert(os.path.join(self.dir, "psx"))
        self.assertEqual(sorted(os.listdir(local)), sorted(os.path.basename(d) for d in (mine, other)))
        self.assertTrue(external.own_temp(os.path.basename(dead)))

    def test_dry_run_changes_nothing_and_needs_no_tools(self):
        self.touch("psx/Game.zip")
        args = SimpleNamespace(chd=self.dir, dry_run=True)
        with mock.patch.object(external, "find_tool", lambda t: None):
            self.assertEqual(chd.chd_command(args), 0)
        self.assertEqual(os.listdir(os.path.join(self.dir, "psx")), ["Game.zip"])

    def bars(self, on_say=None):
        """Patches ui.ProgressBar to record each bar made and the lines it says (each also passed to on_say)."""
        made = []

        class Bar(ui.ProgressBar):
            def __init__(bar, *a, **k):
                super().__init__(*a, **k)
                bar.lines = []
                made.append(bar)

            def say(bar, line):
                bar.lines.append(line)
                if on_say:
                    on_say(line)
                super().say(line)

        return made, mock.patch.object(ui, "ProgressBar", Bar)

    def test_bar_is_weighted_by_bytes_and_biggest_jobs_go_first(self):
        self.touch("psx/A.iso", text="x" * 100)
        self.touch("psx/B.iso", text="x" * 300)
        made, patch = self.bars()
        seen = {}

        def fake_run(cmd, progress=None, tty=False):
            if cmd[1:2] == ["createcd"]:
                seen[os.path.basename(cmd[cmd.index("-i") + 1])] = made[0].fraction()
            return FakeTools()(cmd, progress, tty)

        with patch, mock.patch.object(external, "run_tool", fake_run), mock.patch.object(external, "find_tool", lambda t: t), \
                mock.patch.object(os, "cpu_count", return_value=1), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(chd.chd_command(SimpleNamespace(chd=self.dir, dry_run=False)), 0)
        self.assertEqual(list(seen), ["B.iso", "A.iso"])
        self.assertAlmostEqual(seen["A.iso"], 0.75)  # B, three quarters of the bytes, is done
        self.assertEqual(made[0].total, 400)
        self.assertIn("2 to convert (400 B)", out.getvalue())

    def test_results_print_as_jobs_finish(self):
        self.touch("psx/A.iso", text="x" * 300)
        self.touch("psx/B.iso", text="x" * 100)
        b_said = threading.Event()

        def fake_run(cmd, progress=None, tty=False):
            if cmd[1:2] == ["createcd"] and cmd[cmd.index("-i") + 1].endswith("A.iso"):
                b_said.wait(2)  # A finishes only once B's result is out
            return FakeTools()(cmd, progress, tty)

        made, patch = self.bars(lambda line: b_said.set() if "B.iso" in line else None)
        with patch, mock.patch.object(external, "run_tool", fake_run), mock.patch.object(external, "find_tool", lambda t: t), \
                mock.patch.object(os, "cpu_count", return_value=2), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(chd.chd_command(SimpleNamespace(chd=self.dir, dry_run=False)), 0)
        self.assertEqual([l.strip() for l in made[0].lines], ["✅ psx/B.iso", "✅ psx/A.iso"])
        self.assertTrue(b_said.is_set())

    def test_multi_disc_archive_progress_counts_every_disc(self):
        self.touch("Game.zip")
        seen = []

        def fake(cmd, progress=None, tty=False):
            if cmd[0] == "chdman":
                if cmd[1] == "createcd":
                    open(cmd[cmd.index("-o") + 1], "w").close()
                progress(100)
                return None
            return FakeTools(archive=["Game (Disc 1).iso", "Game (Disc 2).iso"])(cmd, progress, tty)

        with mock.patch.object(external, "run_tool", fake):
            self.assertIsNone(chd.chd_archive(self.tools, CD["chd"], os.path.join(self.dir, "Game.zip"), seen.append))
        self.assertEqual([round(f, 2) for f in seen], [0.2, 0.56, 0.6, 0.96, 1.0])  # unpacked, then each disc half the rest

    def run_on_card(self, root, dry_run=False, answer=None, yes=False):
        """chd_command on root with a saved card named SD; answer is what the terminal types (None: no terminal)."""
        def ask(prompt):
            if answer is None:
                raise EOFError
            return answer

        with mock.patch.object(store, "load_cards", return_value={"SD": {"device": "full"}}), \
                mock.patch.object(ui, "_input", ask), mock.patch.object(ui, "ASSUME_YES", yes), \
                mock.patch.object(external, "run_tool", FakeTools()), mock.patch.object(external, "find_tool", lambda t: t), \
                contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            try:
                code = chd.chd_command(SimpleNamespace(chd=root, dry_run=dry_run))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def test_converting_inside_a_saved_card_asks_first(self):
        root = os.path.join(self.dir, "SD", "psx")
        for case, kwargs, code in (("yes typed", {"answer": "y"}, 0), ("no typed", {"answer": "n"}, 1), ("enter", {"answer": ""}, 1),
                                   ("--yes", {"yes": True}, 1), ("no terminal", {}, 1)):
            with self.subTest(case):
                self.touch("SD/psx/Game.iso")
                got, out, err = self.run_on_card(root, **kwargs)
                self.assertEqual(got, code)
                self.assertIn("card SD", out)
                self.assertIn("download", out)
                self.assertEqual(os.listdir(root), ["Game.chd"] if code == 0 else ["Game.iso"])
                if code:
                    self.assertIn("Not converting", err)
                os.remove(os.path.join(root, os.listdir(root)[0]))

    def test_dry_run_inside_a_saved_card_only_warns(self):
        self.touch("SD/psx/Game.iso")
        with mock.patch.object(ui, "confirm", side_effect=AssertionError("asked")):
            code, out, _ = self.run_on_card(os.path.join(self.dir, "SD", "psx"), dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("card SD", out)

    def test_card_warning_shows_on_stderr_under_quiet(self):
        self.touch("SD/psx/Game.iso")
        with mock.patch.object(ui, "QUIET", True):
            code, out, err = self.run_on_card(os.path.join(self.dir, "SD", "psx"), answer="n")
        self.assertEqual(code, 1)
        self.assertIn("card SD", err)

    def test_folder_outside_any_card_is_not_guarded(self):
        self.touch("psx/Game.iso")
        code, out, _ = self.run_on_card(os.path.join(self.dir, "psx"))
        self.assertEqual(code, 0)
        self.assertNotIn("card SD", out)

    def test_converting_inside_the_storage_folder_says_to_update_the_cache(self):
        self.touch("psx/Game.iso")
        for storage, dry_run, hint in ((self.dir, False, True), (self.dir, True, False), (os.path.join(self.dir, "other"), False, False)):
            with self.subTest(storage=storage, dry_run=dry_run), mock.patch.object(runtime, "ROOT", storage):
                _, out, _ = self.run_on_card(os.path.join(self.dir, "psx"), dry_run=dry_run)
                self.assertEqual("sync-roms cache update" in out, hint)
                if not dry_run:
                    os.rename(os.path.join(self.dir, "psx", "Game.chd"), os.path.join(self.dir, "psx", "Game.iso"))


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
