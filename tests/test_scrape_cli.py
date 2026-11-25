import contextlib
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from realdir_guard import RealDataDirGuard  # noqa: E402
from sync_roms import cli, commands, scrape_online, screenscraper, store, usersettings  # noqa: E402
from helpers import DataDir, Isolated, script_for  # noqa: E402


class ScrapeRun(Isolated):
    """Runs `sync-roms scrape ...` with storage and every scrape command mocked, recording which ran and with what."""

    def run_scrape(self, *argv):
        from sync_roms import scrape_art, scrape_files, scrape_review
        seen = {}

        def record(name, code=0):
            return lambda args=None: seen.update(fn=name, args=args) or code
        code, out, err = self.sync(list(argv), {"bucket": "b"},
                                   p=(commands, "prepare_storage", mock.Mock()),
                                   s=(scrape_online, "scrape_command", record("scrape")),
                                   m=(scrape_online, "match_command", record("match")),
                                   mi=(scrape_online, "missing_command", record("missing")),
                                   c=(scrape_online, "set_credentials", record("set_credentials")),
                                   r=(scrape_review, "review_command", record("review")),
                                   a=(scrape_art, "art_command", record("art")),
                                   cl=(scrape_files, "clean_scrapes", record("clean")))
        return code, seen.get("fn"), seen.get("args"), err

    def ran(self, *argv):
        code, fn, args, err = self.run_scrape(*argv)
        self.assertEqual((code, err), (0, ""))
        return fn, args

    def refused(self, *argv, message=None):
        code, fn, _, err = self.run_scrape(*argv)
        self.assertEqual(code, 2, err)
        self.assertIsNone(fn, f"{argv} ran {fn}")
        if message:
            self.assertIn(message, err)
        return err


class Forms(ScrapeRun):
    def test_scrape_forms(self):
        for argv, fn, system in ((["scrape"], "scrape", None), (["scrape", "gba"], "scrape", "gba"),
                                 (["scrape", "--system", "gba"], "scrape", "gba"), (["scrape", "missing", "gba"], "missing", "gba"),
                                 (["scrape", "missing", "--system", "gba"], "missing", "gba"), (["scrape", "missing"], "missing", None),
                                 (["scrape", "review", "nds"], "review", "nds"), (["scrape", "review"], "review", None),
                                 (["scrape", "art", "--system", "gba"], "art", "gba"), (["scrape", "art", "gba"], "art", "gba")):
            with self.subTest(argv=argv):
                ran, args = self.ran(*argv)
                self.assertEqual((ran, args.system), (fn, system))
        self.assertEqual(self.ran("scrape", "art", "gba", "--for", "spruce")[1].target, "spruce")
        self.assertEqual(self.ran("scrape", "art", "--for", "spruce", "gba")[1].system, "gba")
        self.assertEqual(self.ran("scrape", "art")[1].target, "both")

    def test_scrape_flags(self):
        _, args = self.ran("scrape", "--system", "gba", "--retry", "-n", "--skip-media", "covers, manuals", "--all", "--fill-media")
        self.assertEqual((args.system, args.retry, args.dry_run, args.skip_media, args.all, args.fill_media),
                         ("gba", True, True, ["covers", "manuals"], True, True))
        _, args = self.ran("scrape", "art", "gba", "--for", "spruce", "--dry-run")
        self.assertEqual((args.system, args.target, args.dry_run), ("gba", "spruce", True))
        _, args = self.ran("scrape", "art", "--replace", "--workers", "4")
        self.assertEqual((args.replace, args.workers, args.target), (True, 4, "both"))
        _, args = self.ran("scrape", "missing", "gb", "--all")
        self.assertTrue(args.all)
        _, args = self.ran("-n", "scrape", "art")
        self.assertTrue(args.dry_run)

    def test_scrape_two_systems_fails(self):
        for argv, name in ((["scrape", "gba", "--system", "nes"], "scrape"), (["scrape", "missing", "gb", "--system", "nes"], "scrape missing"),
                           (["scrape", "art", "gb", "--system", "nes"], "scrape art")):
            with self.subTest(argv=argv):
                self.refused(*argv, message=f"`{name}` takes one system: `{name} SYSTEM` or `{name} --system SYSTEM`")

    def test_scrape_match(self):
        fn, args = self.ran("scrape", "match", "gba", "a.zip", "Metroid")
        self.assertEqual((fn, args.system, args.rom, args.game, args.translated), ("match", "gba", "a.zip", "Metroid", False))
        _, args = self.ran("scrape", "match", "-n", "gba", "a b.zip", "Metroid Fusion")
        self.assertEqual((args.system, args.rom, args.game, args.dry_run), ("gba", "a b.zip", "Metroid Fusion", True))
        for argv in (["scrape", "match", "gba", "a.zip", "7", "--translated"], ["scrape", "match", "--translated", "gba", "a.zip", "7"]):
            with self.subTest(argv=argv):
                _, args = self.ran(*argv)
                self.assertEqual((args.system, args.rom, args.game, args.translated), ("gba", "a.zip", "7", True))
        _, args = self.ran("scrape", "match", "gba", "a.zip", "7", "--skip-media", "covers")
        self.assertEqual(args.skip_media, ["covers"])
        self.assertEqual(self.ran("scrape", "match", "gba", "Disc 1/a.cue", "1")[1].rom, "Disc 1/a.cue")  # a ROM may be in a subfolder

    def test_scrape_match_dash_values(self):
        for argv, want in ((["scrape", "match", "gba", "-odd.zip", "-5"], ("gba", "-odd.zip", "-5")),
                           (["scrape", "match", "gba", "a.zip", "-1"], ("gba", "a.zip", "-1")),
                           (["scrape", "match", "gba", "-x.zip", "-Foo", "-n"], ("gba", "-x.zip", "-Foo")),
                           (["scrape", "match", "-n", "gba", "-x.zip", "-Foo"], ("gba", "-x.zip", "-Foo"))):
            with self.subTest(argv=argv):
                _, args = self.ran(*argv)
                self.assertEqual((args.system, args.rom, args.game), want)

    def test_scrape_match_needs_three_values(self):
        err = self.refused("scrape", "match", "gba")
        self.assertIn("the following arguments are required: ROM, GAME", err)
        self.assertIn("Try 'sync-roms scrape --help'.", err)

    def test_scrape_clean(self):
        fn, args = self.ran("scrape", "clean", "-n")
        self.assertEqual((fn, args.dry_run), ("clean", True))
        self.assertEqual(self.ran("scrape", "clean", "-y")[0], "clean")
        self.refused("scrape", "clean", "/some/dir", message="unrecognized arguments: /some/dir")
        self.enterContext(contextlib.chdir(self.enterContext(tempfile.TemporaryDirectory())))  # no `clean` folder to sync
        self.refused("clean", "scrapes", message="clean isn't a command or a folder")
        self.refused("clean", "scrapes", "-n")

    def test_set_credentials_alone(self):
        self.assertEqual(self.ran("scrape", "--set-credentials")[0], "set_credentials")
        for argv in (["scrape", "--set-credentials", "--retry"], ["scrape", "--set-credentials", "--all"],
                     ["scrape", "--set-credentials", "--dry-run"], ["scrape", "gba", "--set-credentials"],
                     ["scrape", "--set-credentials", "--system", "gba"], ["scrape", "--set-credentials", "--skip-media", "covers"]):
            with self.subTest(argv=argv):
                self.refused(*argv, message="--set-credentials only goes with `scrape`, on its own")

    def test_set_credentials_needs_no_storage(self):
        prepare = mock.Mock()
        ran = mock.Mock(return_value=0)
        code, _, _ = self.sync(["scrape", "--set-credentials"], p=(commands, "prepare_storage", prepare),
                               c=(scrape_online, "set_credentials", ran))
        self.assertEqual(code, 0)
        ran.assert_called_once()
        prepare.assert_not_called()

    def test_scrape_reads_storage_first(self):
        prepare = mock.Mock()
        code, _, _ = self.sync(["scrape", "gba"], p=(commands, "prepare_storage", prepare), s=(scrape_online, "scrape_command", lambda a: 0))
        self.assertEqual(code, 0)
        prepare.assert_called_once()

    def test_refusals(self):
        for argv in (["scrape", "review", "--retry"], ["scrape", "missing", "--retry"], ["scrape", "match", "--retry", "gba", "a.zip", "1"],
                     ["scrape", "match", "--system", "gba", "gba", "a.zip", "1"], ["scrape", "--for", "onion"],
                     ["scrape", "missing", "--workers", "2"], ["scrape", "art", "--for", "bogus"], ["scrape", "art", "--workers", "0"],
                     ["scrape", "review", "--system", "gb"], ["scrape", "--replace"], ["scrape", "-a"], ["scrape", "--json"],
                     ["--retry"], ["--skip-media", "covers"], ["--set-credentials"], ["--all"], ["--system", "gba"]):
            with self.subTest(argv=argv):
                self.refused(*argv)
        with self.assertRaises(SystemExit) as cm, mock.patch("sys.stderr", io.StringIO()):
            commands.run(["diff", "--retry"])
        self.assertEqual(cm.exception.code, 2)

    def test_dry_run_has_no_effect_on_missing_and_review(self):
        for argv, name in ((["scrape", "missing", "--dry-run"], "scrape missing"), (["scrape", "review", "-n"], "scrape review"),
                           (["-n", "scrape", "review", "gba"], "scrape review")):
            with self.subTest(argv=argv):
                self.refused(*argv, message=f"--dry-run has no effect on `{name}`")

    def test_translated_only_applies_to_scrape_match(self):
        for argv in (["--translated"], ["scrape", "--translated"], ["scrape", "review", "--translated"],
                     ["scrape", "missing", "--translated"]):
            with self.subTest(argv=argv):
                self.refused(*argv, message="unrecognized arguments: --translated")
        with self.assertRaises(SystemExit) as cm, mock.patch("sys.stderr", io.StringIO()) as err:
            commands.run(["upload", "roms", "--translated"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("unrecognized arguments: --translated", err.getvalue())

    def test_a_path_given_as_the_system_is_refused(self):
        for argv in (["scrape", "/Volumes/SD"], ["scrape", "--system", "a/b"], ["scrape", "missing", "/Volumes/SD"],
                     ["scrape", "missing", "--system", "/Volumes/SD"], ["scrape", "review", "/Volumes/SD"],
                     ["scrape", "art", "/Volumes/SD"], ["scrape", "match", "/Volumes/SD", "a.zip", "1"]):
            with self.subTest(argv=argv):
                self.refused(*argv, message="expects a system id")

    def test_skip_media_validated(self):
        err = self.refused("scrape", "--skip-media", "covers,bogus")
        self.assertIn("bogus", err)
        self.assertIn("manuals", err)
        self.assertIn("custom", self.refused("scrape", "--skip-media", "custom"))
        self.assertIn("bogus", self.refused("scrape", "match", "gba", "a.zip", "1", "--skip-media", "bogus"))

    def test_help_explains_dry_run_and_replace(self):
        text = cli.help_text("scrape")
        self.assertNotIn("custom", text)
        self.assertIn("--dry-run", text)
        self.assertIn("replacing", text)
        self.assertIn("sync-roms scrape clean", text)

    def test_help_for_scrape_subcommands_is_the_scrape_topic(self):
        for argv in (["scrape", "--help"], ["scrape", "art", "-h"], ["scrape", "clean", "--help"], ["help", "scrape"]):
            with self.subTest(argv=argv):
                code, out, err = self.sync(argv)
                self.assertEqual((code, err), (0, ""))
                self.assertIn("sync-roms scrape clean", out)


class SetCredentials(RealDataDirGuard):
    def setUp(self):
        super().setUp()
        self.dir = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(store, "data_dir", lambda: self.dir))
        self.path = os.path.join(self.dir, "settings.json")
        self.quota = mock.Mock(return_value=screenscraper.Quota(2, 123, 20000))
        # no request leaves the test
        self.client_class = self.enterContext(mock.patch.object(screenscraper, "Client", return_value=mock.Mock(quota=self.quota)))

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
        code, out = self.run_it(["scraper-user"], ["s3cret-pw"])
        self.assertEqual(code, 0)
        with open(self.path) as f:
            saved = json.load(f)
        self.assertEqual(saved, {"screenscraper_user": "scraper-user", "screenscraper_password": "s3cret-pw"})
        for value in saved.values():
            self.assertNotIn(value, out)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_checks_the_saved_login_and_reports_the_quota(self):
        code, out = self.run_it(["scraper-user"], ["s3cret-pw"])
        self.assertEqual(code, 0)
        self.client_class.assert_called_once()
        self.assertEqual(self.client_class.call_args[0][:2], ("scraper-user", "s3cret-pw"))
        self.quota.assert_called_once_with()
        self.assertIn("123/20000 requests used today, 2 thread(s)", out)

    def test_refused_login_says_saved_but_refused_and_fails(self):
        self.quota.side_effect = screenscraper.Refused("ScreenScraper refused the login (HTTP 403); check it with "
                                                       "`sync-roms scrape --set-credentials`")
        code, out = self.run_it(["me"], ["pw"])
        self.assertEqual(code, 1)
        self.assertTrue(os.path.exists(self.path))
        self.assertIn("Credentials saved, but ScreenScraper refused the check", out)
        self.assertIn("refused the login (HTTP 403)", out)

    def test_check_that_could_not_be_made_says_so(self):
        for error, words in ((screenscraper.Transient("ScreenScraper request failed (URLError)"), "URLError"),
                             (screenscraper.Transient("ScreenScraper request failed (HTTP 502)"), "HTTP 502"),
                             (screenscraper.QuotaExceeded("ScreenScraper quota exceeded (HTTP 430)"), "quota exceeded")):
            self.quota.side_effect = error
            with self.subTest(words=words):
                code, out = self.run_it(["me"], ["pw"])
                self.assertEqual(code, 0)
                self.assertIn("Credentials saved, but the login couldn't be checked", out)
                self.assertIn(words, out)
                self.assertNotIn("refused", out)
        self.quota.side_effect, self.quota.return_value = None, None
        code, out = self.run_it(["me"], ["pw"])
        self.assertIn("no account details", out)

    def test_blank_keeps_existing(self):
        saved = {"screenscraper_user": "old-user", "screenscraper_password": "s3cret-pw"}
        code, out = self.run_it(["new-user"], [""], saved)
        self.assertEqual(code, 0)
        with open(self.path) as f:
            now = json.load(f)
        self.assertEqual(now, dict(saved, screenscraper_user="new-user"))
        for value in list(saved.values()) + ["new-user"]:
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

    def test_ctrl_c_during_the_login_check_keeps_what_was_saved(self):
        self.quota.side_effect = KeyboardInterrupt
        code, out = self.run_it(["me"], ["pw"])
        self.assertEqual(code, 130)
        self.assertTrue(os.path.exists(self.path))
        self.assertIn("👋 Credentials saved; the login wasn't checked", out)

    def test_eof_saves_nothing_more(self):
        with mock.patch("builtins.input", side_effect=EOFError), mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                scrape_online.set_credentials()
        self.assertFalse(os.path.exists(self.path))


class PickSystems(DataDir):
    def test_scrape_without_all_sees_the_games_of_every_card(self):
        self.write_json("cards.json", {"c": {"device": "full", "layout": "esde",
                                             "games": {"gba": [{"title": "A", "bucket": "gba/A.zip"}]}}})
        by = {s["bucket"]: s for s in scrape_online._pick_systems(None)}
        self.assertEqual([g["bucket"] for g in by["gba"]["games"]], ["gba/A.zip"])
        self.assertEqual([s["bucket"] for s in scrape_online._pick_systems("gba")], ["gba"])


class Completion(unittest.TestCase):
    def test_lists_scrape_and_flags(self):
        text = script_for("bash")
        commands_line = re.search(r'-eq 1 \].*?compgen -W "([^"]*)"', text).group(1).split()
        self.assertIn("scrape", commands_line)
        self.assertIn('scrape) COMPREPLY=($(compgen -W "match review missing art clean"', text)
        for word in ("--retry", "--all", "--skip-media", "--set-credentials", "--translated"):
            self.assertIn(word, text)


if __name__ == "__main__":
    unittest.main()
