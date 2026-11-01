import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sync_roms import chd, cli, commands, diff, edit, m3u, picker, runtime, s3, scrape_files, store, ui, upload, usersettings  # noqa: E402
from test_edit import EditFlow  # noqa: E402

ENV = ("ROMS_BUCKET", "ROMS_ENDPOINT", "ROMS_PROFILE", "ROMS_WRITE_PROFILE")


class Isolated(unittest.TestCase):
    """Runs cli.sync() with a given argv and settings.json, leaving the process-wide settings as they were."""
    def setUp(self):
        for name in ("BUCKET", "ENDPOINT", "PROFILE", "WRITE_PROFILE"):
            p = mock.patch.object(runtime, name, getattr(runtime, name))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        for name in ENV:
            os.environ.pop(name, None)
        runtime.OVERRIDES.clear()
        self.addCleanup(runtime.OVERRIDES.clear)

    def sync(self, argv, settings=None, **patches):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(sys, "argv", ["sync-roms"] + argv))
            st.enter_context(mock.patch.object(usersettings, "load_settings", lambda: dict(settings or {})))
            for target, name, value in patches.values():
                st.enter_context(mock.patch.object(target, name, value))
            st.enter_context(contextlib.redirect_stdout(out))
            st.enter_context(contextlib.redirect_stderr(err))
            try:
                code = cli.sync()
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()


class ResolveTest(Isolated):
    def test_precedence_flag_env_settings_default(self):
        saved = {"profile": "from-settings"}
        with mock.patch.object(usersettings, "load_settings", lambda: saved):
            self.assertEqual(usersettings.resolve_settings()["profile"], ("from-settings", "settings.json"))
            os.environ["ROMS_PROFILE"] = "from-env"
            self.assertEqual(usersettings.resolve_settings()["profile"], ("from-env", "env ROMS_PROFILE"))
            runtime.OVERRIDES["profile"] = "from-flag"
            self.assertEqual(usersettings.resolve_settings()["profile"], ("from-flag", "--profile"))
        with mock.patch.object(usersettings, "load_settings", lambda: {}):
            runtime.OVERRIDES.clear()
            os.environ.pop("ROMS_PROFILE")
            self.assertEqual(usersettings.resolve_settings()["write_profile"], ("roms", "default"))

    def test_global_flags_set_the_runtime(self):
        code, _, _ = self.sync(["--devices", "--profile", "p1", "--write-profile=p2", "--bucket", "b", "--endpoint", "http://x"])
        self.assertEqual(code, 0)
        self.assertEqual((runtime.PROFILE, runtime.WRITE_PROFILE, runtime.BUCKET, runtime.ENDPOINT), ("p1", "p2", "b", "http://x"))

    def test_flag_beats_env_beats_settings_for_a_subcommand(self):
        os.environ["ROMS_PROFILE"] = "env"
        self.sync(["config", "show", "--profile", "flag"], {"profile": "saved"})
        self.assertEqual(runtime.OVERRIDES["profile"], "flag")
        code, out, _ = self.sync(["config", "show", "--profile", "flag"], {"profile": "saved"})
        self.assertRegex(out, r"profile\s+flag\s+--profile")

    def test_devices_m3u_and_cd_honor_the_profile_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            for argv in (["--devices"], ["--m3u", tmp], ["--cd", tmp], ["devices"]):
                with self.subTest(argv=argv):
                    runtime.PROFILE = "unset"
                    self.sync(argv, {"profile": "saved-profile", "bucket": "saved-bucket"})
                    self.assertEqual((runtime.PROFILE, runtime.BUCKET), ("saved-profile", "saved-bucket"))

    def test_devices_does_not_ask_for_a_bucket(self):
        with mock.patch("builtins.input", side_effect=AssertionError("asked")):
            self.assertEqual(self.sync(["--devices"], {})[0], 0)

    def test_a_flag_without_a_value_is_a_usage_error(self):
        self.assertEqual(self.sync(["--devices", "--profile"])[0], 2)


class QuietVerboseTest(Isolated):
    def test_quiet_silences_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = self.sync(["--m3u", tmp, "--quiet"], {})
        self.assertEqual((code, out), (0, ""))

    def test_without_quiet_it_prints(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("playlists", self.sync(["--m3u", tmp], {})[1])

    def test_quiet_keeps_json_data(self):
        code, out, _ = self.sync(["devices", "--json", "--quiet"], {})
        self.assertEqual(code, 0)
        self.assertIsInstance(json.loads(out), list)

    def test_quiet_does_not_leak_into_the_next_run(self):
        self.sync(["--devices", "--quiet"], {})
        self.assertNotEqual(self.sync(["--devices"], {})[1], "")

    def test_quiet_and_verbose_conflict(self):
        self.assertEqual(self.sync(["--devices", "--quiet", "--verbose"], {})[0], 2)

    def test_verbose_reports_settings_on_stderr(self):
        _, out, err = self.sync(["--devices", "--verbose"], {"bucket": "mybucket"})
        self.assertIn("mybucket", err)
        self.assertNotIn("mybucket", out)

    def test_quiet_prompts_go_to_stderr(self):
        err = io.StringIO()
        with mock.patch.object(ui, "QUIET", True), mock.patch("builtins.input", return_value="y") as inp, \
                contextlib.redirect_stderr(err):
            self.assertTrue(ui.confirm("Go?"))
        inp.assert_called_once_with()
        self.assertIn("Go?", err.getvalue())


class DiffJsonTest(Isolated):
    def test_diff_json(self):
        manifest = {"systems": [{"name": "GBA", "bucket": "gba", "folders": {}, "bios": {"files": []}}]}
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "Mine.gba"), "wb") as f:
                f.write(b"abc")
            code, out, _ = self.sync(["diff", tmp, "--system", "gba", "--json"], {"bucket": "b"},
                                     m=(store, "load_manifest", lambda names=(): manifest),
                                     r=(s3, "list_with_etags", lambda prefix: {"Theirs.gba": (5, '"e"')}),
                                     fp=(diff, "local_fingerprint", lambda p: ("l",)),
                                     bf=(diff, "bucket_fingerprint", lambda *a: ("r",)))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"system": "gba", "only_local": [{"path": "Mine.gba", "size": 3}],
                                           "only_bucket": [{"path": "Theirs.gba", "size": 5}]})

    def test_diff_json_needs_a_system(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self.sync(["diff", tmp, "--json"], {"bucket": "b"},
                                     m=(store, "load_manifest", lambda names=(): {"systems": [
                                         {"name": "GBA", "bucket": "gba", "folders": {}, "bios": {"files": []}}]}))
        self.assertEqual(code, 2)
        self.assertIn("--system", err)

    def test_json_alone_is_refused_for_other_commands(self):
        self.assertEqual(self.sync(["--m3u", "--json"], {})[0], 2)


class DryRunJsonTest(Isolated):
    SYSTEM = {"name": "Game Boy Advance", "bucket": "gba", "folders": {"esde": "gba"}, "bios": {"files": []},
              "games": [{"bucket": "gba/Game.zip"}, {"bucket": "gba/Gone.zip"}]}
    MANIFEST = {"systems": [SYSTEM], "devices": [], "layouts": {"esde": {"label": "ES-DE", "roms_dir": "ROMs", "bios_dir": "BIOS"}}}

    def run_plan(self, argv):
        with tempfile.TemporaryDirectory() as card:
            return self.sync([card] + argv, {"bucket": "b"},
                             m=(store, "load_manifest", lambda names=(): self.MANIFEST),
                             c=(store, "load_cards", lambda: {}),
                             l=(s3, "list_sizes", lambda prefix: {"gba/Game.zip": 5} if prefix == "gba/" else {}),
                             t=(s3, "fetch_texts", lambda keys: {}),
                             s=(cli.picker, "saved_setup", lambda *a: (None, "esde")),
                             a=(cli.clean, "clean_android_media", lambda *a: None))

    def test_dry_run_json_is_one_document(self):
        code, out, _ = self.run_plan(["--dry-run", "--json", "--systems", "all", "--yes"])
        self.assertEqual(code, 0)
        plan = json.loads(out)
        self.assertEqual([d["key"] for d in plan["downloads"]], ["gba/Game.zip"])
        self.assertEqual(plan["downloads"][0]["size"], 5)
        self.assertEqual(plan["missing"]["roms"], ["gba/Gone.zip"])
        self.assertEqual(plan["delete"], [])
        self.assertEqual(plan["totals"]["files"], 1)

    def test_json_without_dry_run_is_refused(self):
        self.assertEqual(self.run_plan(["--json", "--yes"])[0], 2)

    def test_dry_run_without_json_is_unchanged(self):
        self.assertIn("Dry run", self.run_plan(["--dry-run", "--systems", "all", "--yes"])[1])


if __name__ == "__main__":
    unittest.main()
