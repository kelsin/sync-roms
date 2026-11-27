import contextlib
import io
import json
import os
import shlex
import subprocess
import tarfile
import unittest
from unittest import mock

import helpers
from sync_roms import config_push

DIR = "/home/deck/.sync-roms"


def tar_of(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def untar(data):
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        return {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}


class Ssh:
    """A fake `subprocess.run` for ssh: answers the data-folder query, then the fetch with `device` files, and records sends."""

    def __init__(self, device=None, data_dir=DIR, fail=False):
        self.device, self.data_dir, self.fail = device or {}, data_dir, fail
        self.calls, self.sent = [], None

    def __call__(self, argv, input=None, **kw):
        self.calls.append(argv)
        if self.fail:
            raise subprocess.CalledProcessError(255, argv, b"", b"ssh: connect to host deck port 22: Connection refused")
        script = argv[-1]
        if "XDG_DATA_HOME" in script:
            out = self.data_dir.encode()
        elif input is None:
            out = tar_of(self.device)
        else:
            self.sent = untar(input)
            out = b""
        return subprocess.CompletedProcess(argv, 0, out, b"")


class Push(helpers.DataDir):
    def setUp(self):
        super().setUp()
        os.makedirs(self.path("collections"))

    def mac(self, settings, collections=()):
        self.write_json("settings.json", settings)
        for name, data in dict(collections).items():
            with open(self.path(f"collections/{name}"), "wb") as f:
                f.write(data)

    def push(self, ssh, dry_run=False):
        out = io.StringIO()
        with mock.patch.object(subprocess, "run", ssh), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                code = config_push.push("deck@steamdeck", dry_run)
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def test_merge_keeps_device_storage(self):
        self.assertEqual(config_push.merge({"root": "/Volumes/roms", "ra_mode": "Casual"}, {"bucket": "b", "ra_mode": "Hardcore", "old": 1}),
                         {"bucket": "b", "ra_mode": "Casual"})

    def test_never_sent_not_in_tar(self):
        self.mac({k: "mac" for k in config_push.NEVER_SENT} | {"ra_mode": "Casual"})
        ssh = Ssh()
        self.assertEqual(self.push(ssh)[0], 0)
        sent = json.loads(ssh.sent["settings.json"])
        self.assertEqual(sent, {"ra_mode": "Casual"})

    def test_changes_hide_values(self):
        self.mac({"ra_password": "new-secret-pw"})
        code, out = self.push(Ssh({"settings.json": json.dumps({"ra_password": "old-secret-pw"}).encode()}))
        self.assertEqual(code, 0)
        self.assertIn("changed ra_password", out)
        self.assertNotIn("secret", out)
        self.assertEqual(config_push.changes({"a": 1, "b": 1}, {"b": 2, "c": 3}), ["added c", "changed b", "removed a"])

    def test_collections_matched(self):
        self.mac({}, {"a.json": b'{"new": 1}', "c.json": b"{}"})
        ssh = Ssh({"collections/a.json": b'{"old": 1}', "collections/b.json": b"{}"})
        code, out = self.push(ssh)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(ssh.sent), ["collections/a.json", "collections/c.json", "settings.json"])
        self.assertEqual(ssh.sent["collections/a.json"], b'{"new": 1}')
        for line in ("changed collection a", "added collection c", "removed collection b"):
            self.assertIn(line, out)

    def test_first_push_no_device_settings(self):
        self.mac({"ra_mode": "Casual", "root": "/Volumes/roms"})
        ssh = Ssh()
        code, out = self.push(ssh)
        self.assertEqual(code, 0)
        self.assertIn("added ra_mode", out)
        self.assertEqual(json.loads(ssh.sent["settings.json"]), {"ra_mode": "Casual"})

    def test_nothing_to_change(self):
        self.mac({"ra_mode": "Casual"}, {"a.json": b"{}"})
        ssh = Ssh({"settings.json": b'{"ra_mode": "Casual", "bucket": "b"}', "collections/a.json": b"{}"})
        code, out = self.push(ssh)
        self.assertEqual(code, 0)
        self.assertIn("Nothing to change", out)
        self.assertIsNone(ssh.sent)

    def test_unparseable_device_settings_exit_3_nothing_sent(self):
        self.mac({"ra_mode": "Casual"})
        for bad in (b"{not json", b"[1]"):
            with self.subTest(bad=bad):
                ssh = Ssh({"settings.json": bad})
                self.assertEqual(self.push(ssh)[0], 3)
                self.assertIsNone(ssh.sent)

    def test_ssh_failure_exit_1(self):
        self.mac({"ra_mode": "Casual"})
        code, out = self.push(Ssh(fail=True))
        self.assertEqual(code, 1)
        self.assertIn("Can't reach deck@steamdeck over SSH", out)
        self.assertIn("Connection refused", out)

    def test_dry_run_sends_nothing(self):
        self.mac({"ra_mode": "Casual"})
        ssh = Ssh()
        code, out = self.push(ssh, dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("added ra_mode", out)
        self.assertIsNone(ssh.sent)
        self.assertEqual(len(ssh.calls), 2)

    def test_remote_paths_quoted(self):
        folder = "/run/media/deck/My SD/.sync-roms"
        self.mac({"ra_mode": "Casual"})
        ssh = Ssh(data_dir=folder)
        self.assertEqual(self.push(ssh)[0], 0)
        for argv in ssh.calls[1:]:
            script = argv[-1]
            self.assertIn(shlex.quote(folder), script)
            self.assertNotIn(folder, script.replace(shlex.quote(folder), ""))

    def test_ssh_batch_mode(self):
        self.mac({"ra_mode": "Casual"})
        ssh = Ssh()
        self.push(ssh)
        self.assertEqual(len(ssh.calls), 3)
        for argv in ssh.calls:
            self.assertEqual(argv[0], "ssh")
            self.assertIn(["-o", "BatchMode=yes"], [argv[i:i + 2] for i in range(len(argv))])
            self.assertIn(["-o", "ConnectTimeout=10"], [argv[i:i + 2] for i in range(len(argv))])
            self.assertIn("deck@steamdeck", argv)

    def test_send_keeps_old_settings_as_bak(self):
        self.mac({"ra_mode": "Casual"})
        ssh = Ssh()
        self.assertEqual(self.push(ssh)[0], 0)
        script = ssh.calls[-1][-1]
        backup = 'cp -p settings.json "$tmp/bak"; chmod 600 "$tmp/bak"; mv -f "$tmp/bak" settings.json.bak'
        self.assertIn(f"if [ -f settings.json ]; then {backup}; fi", script)
        self.assertLess(script.index(backup), script.index('mv -f "$tmp/settings.json" settings.json'))

    def test_remote_dir_mirrors_data_dir(self):
        ssh = Ssh(data_dir="/x/sync-roms")
        with mock.patch.object(subprocess, "run", ssh):
            self.assertEqual(config_push.remote_dir("deck@steamdeck"), "/x/sync-roms")
        script = ssh.calls[0][-1]
        self.assertIn("$XDG_DATA_HOME", script)
        self.assertIn("/sync-roms", script)
        self.assertIn("/.sync-roms", script)


class PushCommand(helpers.Cmd):
    def test_routes_with_dry_run(self):
        with mock.patch.object(config_push, "push", return_value=0) as push:
            self.assertEqual(self.run_cmd("config", "push", "deck@steamdeck", "--dry-run")[0], 0)
        push.assert_called_once_with("deck@steamdeck", True)

    def test_needs_one_host(self):
        for argv in (("config", "push"), ("config", "push", "a@b", "extra"), ("config", "push", "-oProxyCommand=x")):
            with self.subTest(argv=argv), mock.patch.object(config_push, "push") as push:
                self.assertEqual(self.run_cmd(*argv)[0], 2)
                push.assert_not_called()


if __name__ == "__main__":
    unittest.main()
