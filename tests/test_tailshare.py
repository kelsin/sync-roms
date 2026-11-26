import contextlib
import io
import json
import os
import signal
import socket
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import cli, collections_page, commands, store, tailshare  # noqa: E402

LINK = "https://box.tail1.ts.net/collections/"
STATUS = {"Self": {"DNSName": "box.tail1.ts.net."}}
PORT = tailshare.DEFAULT_PORT
TARGET = f"http://127.0.0.1:{PORT}"
SERVE = ["tailscale", "serve", "--bg", "--yes", "--https=443", "--set-path", "/collections", TARGET]


def serving(mount="/collections", port=PORT, key="box.tail1.ts.net:443"):
    return {"Web": {key: {"Handlers": {mount: {"Proxy": f"http://127.0.0.1:{port}"}}}}}


SERVING = serving()


def completed(out="", code=0, err=""):
    return subprocess.CompletedProcess([], code, out, err)


class Tailscale(helpers.DataDir):
    def setUp(self):
        super().setUp()
        self.serve_status = {}
        self.calls = []
        self.enterContext(mock.patch.object(tailshare.shutil, "which", lambda n: "/bin/" + n))
        self.enterContext(mock.patch.object(tailshare.subprocess, "run", self.run_cmd))
        self.html = "page"
        self.enterContext(mock.patch.object(collections_page, "render", lambda: self.html))
        self.writes = []
        real_write = collections_page.store.write_text

        def write_text(path, text, **kw):
            if path.endswith("index.html"):
                self.writes.append(path)
            return real_write(path, text, **kw)
        self.enterContext(mock.patch.object(collections_page.store, "write_text", write_text))
        self.page = os.path.join(tailshare.SHARE_DIR(), "index.html")
        self.alive, self.listening, self.killed, self.popens = set(), set(), [], []
        self.enterContext(mock.patch.object(tailshare.subprocess, "Popen", self.popen))
        self.enterContext(mock.patch.object(tailshare.os, "kill", self.kill))
        self.enterContext(mock.patch.object(tailshare, "_accepts", lambda port, timeout=1: port in self.listening))
        self.enterContext(mock.patch.object(tailshare, "_free_port", lambda: PORT))
        self.enterContext(mock.patch.object(tailshare.time, "sleep", lambda s: None))

    def popen(self, argv, **kw):
        self.popens.append((argv, kw))
        self.alive.add(4321)
        self.listening.add(int(argv[-1]))
        return mock.Mock(pid=4321, poll=lambda: None)

    def kill(self, pid, sig):
        if pid not in self.alive:
            raise ProcessLookupError(pid)
        if sig:
            self.killed.append((pid, sig))

    def running(self, pid=99, port=PORT):
        """A server from an earlier share: its state file, pid and port."""
        store.write_json(tailshare.STATE_FILE(), {"pid": pid, "port": port})
        self.alive.add(pid)
        self.listening.add(port)

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
        self.assertIn(SERVE, self.argvs())
        [(argv, kw)] = self.popens
        self.assertEqual(argv, [sys.executable, "-I", "-m", "http.server", "--bind", "127.0.0.1", "--directory",
                                tailshare.SHARE_DIR(), str(PORT)])
        self.assertEqual(kw, {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                              "stderr": subprocess.DEVNULL, "start_new_session": True,
                              "cwd": tailshare.SHARE_DIR()})
        self.assertEqual(self.read("share-server.json"), {"pid": 4321, "port": PORT})

    def test_share_rebuilds_an_out_of_date_page_even_when_already_shared(self):
        os.makedirs(tailshare.SHARE_DIR())
        with open(self.page, "w") as f:
            f.write("old")
        self.running()
        self.serve_status = SERVING
        self.assertEqual(tailshare.share(), (LINK, True, False))
        self.assertEqual(self.writes, [self.page])

    def test_share_keeps_existing_page_server_and_serve(self):
        os.makedirs(tailshare.SHARE_DIR())
        with open(self.page, "w") as f:
            f.write("page")
        self.running()
        self.serve_status = SERVING
        self.assertEqual(tailshare.share(), (LINK, False, False))
        self.assertEqual(self.writes, [])
        self.assertEqual(self.popens, [])
        self.assertFalse([a for a in self.argvs() if "--bg" in a or "off" in a])

    def test_trailing_slash_mount_counts(self):
        self.running()
        self.serve_status = serving("/collections/")
        self.assertEqual(tailshare.share()[2], False)
        self.assertFalse([a for a in self.argvs() if "--bg" in a])

    def test_running_server_is_served(self):
        self.running(port=9001)
        self.assertEqual(tailshare.share()[2], True)
        self.assertEqual(self.popens, [])
        self.assertIn(SERVE[:-1] + ["http://127.0.0.1:9001"], self.argvs())

    def test_dead_pid_restarts(self):
        self.running()
        self.alive.discard(99)
        self.serve_status = SERVING
        self.assertEqual(tailshare.share(), (LINK, True, True))
        self.assertEqual(len(self.popens), 1)
        self.assertEqual(self.read("share-server.json"), {"pid": 4321, "port": PORT})

    def test_closed_port_restarts(self):
        self.running()
        self.listening.discard(PORT)
        tailshare.share()
        self.assertEqual(len(self.popens), 1)

    def test_bad_state_file_restarts(self):
        for text in ("not json", "[]", '{"pid": "1", "port": 2}', '{"pid": 1}'):
            with self.subTest(text=text):
                self.popens.clear()
                with open(tailshare.STATE_FILE(), "w") as f:
                    f.write(text)
                tailshare.share()
                self.assertEqual(len(self.popens), 1)

    def test_taken_port_picks_another(self):
        with mock.patch.object(tailshare, "_free_port", lambda: 50123):
            tailshare.share()
        self.assertEqual(self.popens[0][0][-1], "50123")
        self.assertIn(SERVE[:-1] + ["http://127.0.0.1:50123"], self.argvs())
        self.assertEqual(self.read("share-server.json")["port"], 50123)

    def test_old_port_turned_off_then_served(self):
        self.serve_status = serving("/collections/", port=9001)
        tailshare.share()
        argvs = [a for a in self.argvs() if a[:3] != ["tailscale", "serve", "status"] and a[1] == "serve"]
        self.assertEqual(argvs, [["tailscale", "serve", "--https=443", "--set-path", "/collections/", "off"], SERVE])

    def test_server_that_never_listens_fails(self):
        def popen(argv, **kw):
            return mock.Mock(pid=4321, poll=lambda: None)
        clock = iter(range(0, 100))
        err = io.StringIO()
        with mock.patch.object(tailshare.subprocess, "Popen", popen), \
                mock.patch.object(tailshare.time, "monotonic", lambda: next(clock)), \
                contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            tailshare.share()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("The local page server didn't start", err.getvalue())

    def test_serves_only_share_folder(self):
        tailshare.share()
        argv = self.popens[0][0]
        self.assertEqual(argv[argv.index("--directory") + 1], tailshare.SHARE_DIR())
        self.assertNotEqual(tailshare.SHARE_DIR(), store.data_dir())

    def test_state_file_outside_share_dir(self):
        state, share = os.path.realpath(tailshare.STATE_FILE()), os.path.realpath(tailshare.SHARE_DIR())
        self.assertEqual(state, os.path.join(os.path.realpath(store.data_dir()), "share-server.json"))
        self.assertFalse(state.startswith(share + os.sep))

    def test_calls_have_no_stdin_and_a_timeout(self):
        tailshare.share()
        for argv, kw in self.calls:
            self.assertEqual(kw["stdin"], subprocess.DEVNULL)
            self.assertEqual(kw["timeout"], 30 if "--bg" in argv else 60)

    def test_serve_not_enabled_fails_with_url(self):
        url = "https://login.tailscale.com/f/serve?node=abc123"
        out = f"Serve is not enabled on your tailnet.\nTo enable, visit:\n\n         {url}\n"
        for result in (completed(out), completed(code=1, err=out), subprocess.TimeoutExpired(SERVE, 30, output=out)):
            def run(argv, **kw):
                if "--bg" not in argv:
                    return self.run_cmd(argv, **kw)
                if isinstance(result, Exception):
                    raise result
                return result
            err = io.StringIO()
            with self.subTest(result=result), mock.patch.object(tailshare.subprocess, "run", run), \
                    contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                tailshare.share()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn(f"Tailscale Serve isn't enabled on your tailnet. Enable it at {url}, then run this again",
                          err.getvalue())

    def test_missing_tailscale_fails(self):
        with mock.patch.object(tailshare.shutil, "which", lambda n: None), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            tailshare.share()
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.popens, [])

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
        for out in ("not json", "[]", '{"Web": null}', '{"Web": {"h:443": 5}}', '{"Web": {"h:443": {"Handlers": []}}}', '{"Web": []}',
                    json.dumps(serving(key="h:80")), json.dumps(serving(mount="/other"))):
            with self.subTest(out=out), mock.patch.object(tailshare.subprocess, "run", self.with_serve(out)):
                self.assertIsNone(tailshare.serving())

    def test_serving_finds_handler(self):
        with mock.patch.object(tailshare.subprocess, "run", self.with_serve(json.dumps(serving("/collections/")))):
            self.assertEqual(tailshare.serving(), ("box.tail1.ts.net:443", "/collections/", TARGET))

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
    def test_unshare_when_nothing_running(self):
        self.assertFalse(tailshare.unshare())
        self.assertFalse([a for a in self.argvs() if "off" in a])
        self.assertEqual(self.killed, [])

    def test_unshare_turns_off_found_mount_and_stops_server(self):
        self.running()
        self.serve_status = serving("/collections/")
        self.assertTrue(tailshare.unshare())
        self.assertIn(["tailscale", "serve", "--https=443", "--set-path", "/collections/", "off"], self.argvs())
        self.assertFalse([a for a in self.argvs() if "reset" in a])
        self.assertEqual(self.killed, [(99, signal.SIGTERM)])
        self.assertFalse(os.path.exists(tailshare.STATE_FILE()))

    def test_unshare_server_only(self):
        self.running()
        self.assertTrue(tailshare.unshare())
        self.assertFalse([a for a in self.argvs() if "off" in a])
        self.assertEqual(self.killed, [(99, signal.SIGTERM)])

    def test_unshare_stale_state_kills_nothing(self):
        self.running()
        self.alive.discard(99)
        self.assertFalse(tailshare.unshare())
        self.assertEqual(self.killed, [])
        self.assertFalse(os.path.exists(tailshare.STATE_FILE()))

    def test_unshare_recycled_pid_not_killed(self):
        """A pid alive but not listening on the port (after a restart, another process) is never signalled."""
        self.running()
        self.listening.discard(PORT)
        self.assertFalse(tailshare.unshare())
        self.assertEqual(self.killed, [])


class FreePort(unittest.TestCase):
    def test_default_port_when_free_else_another(self):
        with socket.socket() as held:
            try:
                held.bind(("127.0.0.1", tailshare.DEFAULT_PORT))
            except OSError:
                pass  # already taken by something else: the same case
            port = tailshare._free_port()
        self.assertNotEqual(port, tailshare.DEFAULT_PORT)
        self.assertGreater(port, 0)


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
        self.assertIn("Rebuilt /p/index.html", out)
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
        self.assertEqual(commands.second_words()["collections"], ["edit", "page", "retitle", "share", "unshare"])
        self.assertEqual(cli.SUBCOMMANDS["collections"][0], "edit|page|retitle|share|unshare")


if __name__ == "__main__":
    unittest.main()
