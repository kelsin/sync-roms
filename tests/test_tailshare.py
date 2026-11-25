import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import cli, collections_page, commands, store, tailshare  # noqa: E402

LINK = "https://box.tail1.ts.net/collections/"
STATUS = {"Self": {"DNSName": "box.tail1.ts.net."}}
SERVING = {"Web": {"box.tail1.ts.net:443": {"Handlers": {"/collections": {"Path": "x"}}}}}


def completed(out="", code=0, err=""):
    return subprocess.CompletedProcess([], code, out, err)


class Tailscale(helpers.DataDir):
    def setUp(self):
        super().setUp()
        self.serve_status = {}
        self.calls = []
        self.enterContext(mock.patch.object(tailshare.shutil, "which", lambda n: "/bin/" + n))
        self.enterContext(mock.patch.object(tailshare.subprocess, "run", self.run_cmd))
        self.enterContext(mock.patch.object(collections_page, "write_page", self.write_page))
        self.writes = []
        self.page = os.path.join(tailshare.SHARE_DIR(), "index.html")

    def write_page(self, path):
        self.writes.append(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("page")

    def run_cmd(self, argv, **kw):
        self.calls.append((argv, kw))
        if argv[:3] == ["tailscale", "serve", "status"]:
            return completed(json.dumps(self.serve_status) if self.serve_status else "")
        if argv[:2] == ["tailscale", "status"]:
            return completed(json.dumps(STATUS))
        return completed()

    def argvs(self):
        return [c[0] for c in self.calls]


class Share(Tailscale):
    def test_share_writes_and_serves(self):
        self.assertEqual(tailshare.share(), (LINK, True, True))
        self.assertEqual(self.writes, [self.page])
        self.assertEqual(self.page, os.path.join(self.tmp.name, "share", "collections", "index.html"))
        self.assertIn(["tailscale", "serve", "--bg", "--set-path", "/collections", tailshare.SHARE_DIR()], self.argvs())

    def test_share_keeps_existing_page_and_serve(self):
        os.makedirs(tailshare.SHARE_DIR())
        open(self.page, "w").close()
        self.serve_status = SERVING
        self.assertEqual(tailshare.share(), (LINK, False, False))
        self.assertEqual(self.writes, [])
        self.assertFalse([a for a in self.argvs() if "--bg" in a])

    def test_serves_only_share_folder(self):
        tailshare.share()
        served = [a[-1] for a in self.argvs() if "--bg" in a]
        self.assertEqual(served, [tailshare.SHARE_DIR()])
        self.assertNotEqual(served[0], store.data_dir())

    def test_calls_have_no_stdin_and_a_timeout(self):
        tailshare.share()
        for _, kw in self.calls:
            self.assertEqual(kw["stdin"], subprocess.DEVNULL)
            self.assertEqual(kw["timeout"], 60)

    def test_missing_tailscale_fails(self):
        with mock.patch.object(tailshare.shutil, "which", lambda n: None), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            tailshare.share()
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(self.calls, [])

    def test_serve_error_surfaces(self):
        def run(argv, **kw):
            return completed(code=1, err="HTTPS not enabled\n") if "--bg" in argv else self.run_cmd(argv, **kw)
        err = io.StringIO()
        with mock.patch.object(tailshare.subprocess, "run", run), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as cm:
            tailshare.share()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("HTTPS not enabled", err.getvalue())

    def test_no_dns_name_fails(self):
        def run(argv, **kw):
            return completed("{}") if argv[:2] == ["tailscale", "status"] else self.run_cmd(argv, **kw)
        err = io.StringIO()
        with mock.patch.object(tailshare.subprocess, "run", run), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as cm:
            tailshare.share()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("tailnet name", err.getvalue())


class Robust(Tailscale):
    def fails(self, run, fn=tailshare.share, text=None):
        err = io.StringIO()
        with mock.patch.object(tailshare.subprocess, "run", run), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as cm:
            fn()
        self.assertEqual(cm.exception.code, 1)
        if text:
            self.assertIn(text, err.getvalue())

    def with_serve(self, out):
        return lambda argv, **kw: completed(out) if argv[:3] == ["tailscale", "serve", "status"] else self.run_cmd(argv, **kw)

    def test_timeout(self):
        def run(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 60)
        self.fails(run, text="didn't answer within 60 s")

    def test_oserror(self):
        def run(argv, **kw):
            raise OSError("boom")
        self.fails(run, text="couldn't run tailscale: boom")

    def test_serve_status_bad_json_is_not_serving(self):
        for out in ("not json", "[]", '{"Web": null}', '{"Web": {"h:443": 5}}', '{"Web": {"h:443": {"Handlers": []}}}', '{"Web": []}'):
            with self.subTest(out=out), mock.patch.object(tailshare.subprocess, "run", self.with_serve(out)):
                self.assertFalse(tailshare.serving())

    def test_status_bad_json_fails_cleanly(self):
        for out in ("not json", "[]", '{"Self": null}', '{"Self": 5}', '{"Self": {}}'):
            run = lambda argv, **kw: completed(out) if argv[:2] == ["tailscale", "status"] else self.run_cmd(argv, **kw)
            with self.subTest(out=out):
                self.fails(run, text="Couldn't read this machine's tailnet name")

    def test_nonzero_exit_names_subcommand(self):
        self.fails(lambda argv, **kw: completed(code=1, err="nope"), text="tailscale serve failed: nope")
        def run(argv, **kw):
            return completed(code=1, err="down") if argv[:2] == ["tailscale", "status"] else self.run_cmd(argv, **kw)
        self.fails(run, text="tailscale status failed: down")


class Unshare(Tailscale):
    def test_unshare_when_not_serving(self):
        self.assertFalse(tailshare.unshare())
        self.assertFalse([a for a in self.argvs() if "off" in a])

    def test_unshare_only_turns_off_its_path(self):
        self.serve_status = SERVING
        self.assertTrue(tailshare.unshare())
        self.assertIn(["tailscale", "serve", "--https=443", "--set-path", "/collections", "off"], self.argvs())
        self.assertFalse([a for a in self.argvs() if "reset" in a])


class Clipboard(unittest.TestCase):
    def test_clipboard(self):
        with mock.patch.object(tailshare.shutil, "which", lambda n: "/bin/pbcopy" if n == "pbcopy" else None), \
                mock.patch.object(tailshare.subprocess, "run", return_value=completed()) as run:
            self.assertTrue(tailshare.copy_to_clipboard(LINK))
        self.assertEqual(run.call_args.args[0], ["pbcopy"])
        self.assertEqual(run.call_args.kwargs["input"], LINK)

    def test_first_found_only(self):
        with mock.patch.object(tailshare.shutil, "which", lambda n: "/bin/" + n), \
                mock.patch.object(tailshare.subprocess, "run", return_value=completed()) as run:
            tailshare.copy_to_clipboard("x")
        run.assert_called_once()

    def test_xclip_selection(self):
        with mock.patch.object(tailshare.shutil, "which", lambda n: "/bin/xclip" if n == "xclip" else None), \
                mock.patch.object(tailshare.subprocess, "run", return_value=completed()) as run:
            tailshare.copy_to_clipboard("x")
        self.assertEqual(run.call_args.args[0], ["xclip", "-selection", "clipboard"])

    def test_none_found(self):
        with mock.patch.object(tailshare.shutil, "which", lambda n: None), \
                mock.patch.object(tailshare.subprocess, "run") as run:
            self.assertFalse(tailshare.copy_to_clipboard("x"))
        run.assert_not_called()

    def test_failure_is_false(self):
        with mock.patch.object(tailshare.shutil, "which", lambda n: "/bin/pbcopy"), \
                mock.patch.object(tailshare.subprocess, "run", return_value=completed(code=1)):
            self.assertFalse(tailshare.copy_to_clipboard("x"))


class Commands(unittest.TestCase):
    def run_cmd(self, argv, **patches):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = commands.run(argv)
        return code, out.getvalue()

    def test_share_command_copies_link(self):
        with mock.patch.object(tailshare, "share", return_value=(LINK, True, True)), \
                mock.patch.object(tailshare, "copy_to_clipboard", return_value=True), \
                mock.patch.object(collections_page, "DEFAULT_PATH", lambda: "/p/index.html"):
            code, out = self.run_cmd(["collections", "share"])
        self.assertEqual(code, 0)
        self.assertIn("Built /p/index.html", out)
        self.assertIn(f"Sharing at {LINK} 📋", out.splitlines()[-1])

    def test_share_command_already_shared_no_clipboard(self):
        with mock.patch.object(tailshare, "share", return_value=(LINK, False, False)), \
                mock.patch.object(tailshare, "copy_to_clipboard", return_value=False):
            code, out = self.run_cmd(["collections", "share"])
        self.assertEqual(out.strip(), f"Already shared at {LINK}")

    def test_unshare_command(self):
        with mock.patch.object(tailshare, "unshare", return_value=True):
            self.assertIn("Stopped sharing the collections page.", self.run_cmd(["collections", "unshare"])[1])
        with mock.patch.object(tailshare, "unshare", return_value=False):
            self.assertIn("The collections page isn't shared.", self.run_cmd(["collections", "unshare"])[1])

    def test_dry_run_refused(self):
        for word in ("share", "unshare"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                commands.run(["collections", word, "--dry-run"])

    def test_wiring(self):
        self.assertEqual(commands.second_words()["collections"], ["edit", "page", "share", "unshare"])
        self.assertEqual(cli.SUBCOMMANDS["collections"][0], "edit|page|share|unshare")


if __name__ == "__main__":
    unittest.main()
