import getpass
import io
import json
import os
import re
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from realdir_guard import RealDataDirGuard  # noqa: E402
from sync_roms import cli, scrape_online, store, usersettings  # noqa: E402
from test_completion import script_for  # noqa: E402
from test_scripting import Isolated  # noqa: E402


class Translate(unittest.TestCase):
    def test_scrape(self):
        self.assertEqual(cli.translate(["scrape"]), ["--scrape"])
        self.assertEqual(cli.translate(["scrape", "--system", "gba", "--retry", "--skip-media", "manuals,covers", "-n"]),
                         ["--scrape", "--system", "gba", "--retry", "--skip-media", "manuals,covers", "-n"])
        self.assertEqual(cli.translate(["scrape", "--set-credentials"]), ["--scrape", "--set-credentials"])

    def test_match(self):
        self.assertEqual(cli.translate(["scrape", "match", "gba", "a.zip", "123"]), ["--scrape-match", "gba", "a.zip", "123"])
        self.assertEqual(cli.translate(["scrape", "match", "-n", "gba", "a b.zip", "Metroid Fusion"]),
                         ["--scrape-match", "gba", "a b.zip", "Metroid Fusion", "-n"])

    def test_match_values_starting_with_a_dash(self):
        self.assertEqual(cli.translate(["scrape", "match", "gba", "a.zip", "-1"]), ["--scrape-match", "gba", "a.zip", "-1"])
        self.assertEqual(cli.translate(["scrape", "match", "gba", "-x.zip", "-Foo", "-n"]),
                         ["--scrape-match", "gba", "-x.zip", "-Foo", "-n"])
        self.assertEqual(cli.translate(["scrape", "match", "gba", "-x.zip", "Foo"]), ["--scrape-match", "gba", "-x.zip", "Foo"])
        for argv, want in ((["scrape", "match", "gba", "a.zip", "-1"], ["gba", "a.zip", "-1"]),
                           (["scrape", "match", "-n", "gba", "-x.zip", "-Foo"], ["gba", "-x.zip", "-Foo"])):
            with self.subTest(argv=argv):
                args = cli.build_parser().parse_args(cli.translate(argv))
                self.assertEqual(args.scrape_match, want)
                self.assertEqual(cli.check_modes(args), "--scrape-match")

    def test_parses(self):
        args = cli.build_parser().parse_args(cli.translate(["scrape", "match", "-n", "gba", "a.zip", "123"]))
        self.assertEqual(args.scrape_match, ["gba", "a.zip", "123"])
        self.assertTrue(args.dry_run)


class Modes(unittest.TestCase):
    def modes(self, *argv):
        return cli.check_modes(cli.build_parser().parse_args(cli.translate(list(argv))))

    def refused(self, *argv):
        with self.assertRaises(SystemExit) as cm, mock.patch("sys.stderr", io.StringIO()):
            self.modes(*argv)
        self.assertEqual(cm.exception.code, 2)

    def test_valid(self):
        self.assertEqual(self.modes("scrape", "--system", "gba", "--retry", "--skip-media", "covers,manuals"), "--scrape")
        self.assertEqual(self.modes("scrape", "match", "gba", "a.zip", "1"), "--scrape-match")
        self.assertEqual(self.modes("scrape", "--set-credentials"), "--scrape")
        self.assertEqual(self.modes("diff", "--system", "gba"), "--diff")

    def test_refusals(self):
        self.refused("--retry")
        self.refused("--skip-media", "covers")
        self.refused("--set-credentials")
        self.refused("--system", "gba")
        self.refused("diff", "--retry")
        self.refused("--scrape", "--upload")
        self.refused("--scrape", "--scrape-match", "gba", "a", "1")
        self.refused("scrape", "match", "--retry", "gba", "a.zip", "1")
        self.refused("scrape", "match", "--system", "gba", "gba", "a.zip", "1")
        self.refused("scrape", "--set-credentials", "--retry")
        self.refused("scrape", "--set-credentials", "--dry-run")
        self.refused("scrape", "/some/card")

    def test_skip_media_validated(self):
        with mock.patch("sys.stderr", io.StringIO()) as err, self.assertRaises(SystemExit):
            self.modes("scrape", "--skip-media", "covers,bogus")
        self.assertIn("bogus", err.getvalue())
        self.assertIn("manuals", err.getvalue())

    def test_skip_media_only_scraper_types(self):
        with mock.patch("sys.stderr", io.StringIO()) as err, self.assertRaises(SystemExit):
            self.modes("scrape", "--skip-media", "custom")
        self.assertIn("custom", err.getvalue())

    def test_help_explains_dry_run_and_replace(self):
        text = cli.help_text("scrape")
        self.assertNotIn("custom", text)
        self.assertIn("--dry-run", text)
        self.assertIn("replacing", text)

    def test_skip_media_becomes_a_list(self):
        args = cli.build_parser().parse_args(cli.translate(["scrape", "--skip-media", "covers, manuals"]))
        cli.check_modes(args)
        self.assertEqual(args.skip_media, ["covers", "manuals"])


class Dispatch(Isolated):
    def test_scrape_runs_with_args(self):
        seen = {}
        ensure = mock.Mock()
        code, _, _ = self.sync(["scrape", "--system", "gba", "--retry", "-n", "--skip-media", "covers"],
                               cmd=(scrape_online, "scrape_command", lambda a: seen.update(vars(a)) or 0),
                               ens=(usersettings, "ensure_bucket", ensure))
        self.assertEqual(code, 0)
        ensure.assert_called_once()
        self.assertEqual((seen["system"], seen["retry"], seen["dry_run"], seen["skip_media"]), ("gba", True, True, ["covers"]))

    def test_match_runs_with_args(self):
        seen = {}
        code, _, _ = self.sync(["scrape", "match", "gba", "a.zip", "Metroid"],
                               cmd=(scrape_online, "match_command", lambda a: seen.update(vars(a)) or 0),
                               ens=(usersettings, "ensure_bucket", mock.Mock()))
        self.assertEqual(code, 0)
        self.assertEqual((seen["system"], seen["rom"], seen["game"]), ("gba", "a.zip", "Metroid"))

    def test_set_credentials_needs_no_bucket(self):
        ensure = mock.Mock()
        ran = mock.Mock(return_value=0)
        code, _, _ = self.sync(["scrape", "--set-credentials"], cmd=(scrape_online, "set_credentials", ran),
                               ens=(usersettings, "ensure_bucket", ensure))
        self.assertEqual(code, 0)
        ran.assert_called_once()
        ensure.assert_not_called()


class SetCredentials(RealDataDirGuard):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        p = mock.patch.object(store, "data_dir", lambda: self.dir)
        p.start()
        self.addCleanup(p.stop)
        self.path = os.path.join(self.dir, "settings.json")

    def run_it(self, inputs, passwords, saved=None):
        if saved:
            for k, v in saved.items():
                usersettings.save_setting(k, v)
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=inputs), mock.patch.object(getpass, "getpass", side_effect=passwords), \
                mock.patch("sys.stdout", out), mock.patch("sys.stderr", out):
            code = scrape_online.set_credentials()
        return code, out.getvalue()

    def test_saves_without_printing_values(self):
        code, out = self.run_it(["me"], ["s3cret"])
        self.assertEqual(code, 0)
        with open(self.path) as f:
            saved = json.load(f)
        self.assertEqual(saved, {"screenscraper_user": "me", "screenscraper_password": "s3cret"})
        for value in saved.values():
            self.assertNotIn(value, out)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_blank_keeps_existing(self):
        saved = {"screenscraper_user": "me", "screenscraper_password": "s3cret"}
        code, out = self.run_it(["newme"], [""], saved)
        self.assertEqual(code, 0)
        with open(self.path) as f:
            now = json.load(f)
        self.assertEqual(now, dict(saved, screenscraper_user="newme"))
        for value in list(saved.values()) + ["newme"]:
            self.assertNotIn(value, out)

    def test_credentials_saved_in_one_write(self):
        with mock.patch.object(usersettings, "save_settings", wraps=usersettings.save_settings) as save, \
                mock.patch.object(usersettings, "save_setting", side_effect=AssertionError("one key at a time")):
            code, _ = self.run_it(["me"], ["s3cret"])
        self.assertEqual(code, 0)
        save.assert_called_once()

    def test_all_blank_says_nothing_changed(self):
        saved = {"screenscraper_user": "me"}
        code, out = self.run_it([""], [""], saved)
        self.assertEqual(code, 0)
        self.assertNotIn("Saved", out)
        self.assertIn("Nothing changed", out)

    def test_ctrl_c_saves_nothing(self):
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=["me"]), \
                mock.patch.object(getpass, "getpass", side_effect=KeyboardInterrupt), \
                mock.patch("sys.stdout", out), mock.patch("sys.stderr", out):
            code = scrape_online.set_credentials()
        self.assertEqual(code, 130)
        self.assertFalse(os.path.exists(self.path))
        self.assertIn("not saved", out.getvalue())

    def test_eof_saves_nothing_more(self):
        with mock.patch("builtins.input", side_effect=EOFError), mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                scrape_online.set_credentials()
        self.assertFalse(os.path.exists(self.path))


class Completion(unittest.TestCase):
    def test_lists_scrape_and_flags(self):
        text = script_for("bash")
        commands_line = re.search(r'-eq 1 \].*?compgen -W "([^"]*)"', text).group(1).split()
        self.assertIn("scrape", commands_line)
        self.assertIn('scrape) COMPREPLY=($(compgen -W "match"', text)
        for word in ("--retry", "--skip-media", "--set-credentials"):
            self.assertIn(word, text)


if __name__ == "__main__":
    unittest.main()
