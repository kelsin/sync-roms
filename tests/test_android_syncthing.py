import contextlib
import io
import itertools
import os
import sys
import unittest
import urllib.error
import zipfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import adb, android, android_syncthing, applied, spruce_syncthing  # noqa: E402

SID = "-".join(["AAAAAAA"] * 8)
SRV = {"id": SID, "address": "tcp://server:22000",
       "folders": [("saves", "ra-saves", "RetroArch saves", "/mnt/SDCARD/Saves/saves"),
                   ("states", "ra-states", "RetroArch states", "/mnt/SDCARD/Saves/states")]}
DD = {"compression": "metadata", "introducer": False}
DF = {"fsWatcherEnabled": True, "rescanIntervalS": 3600}


def export(config_xml="<configuration><gui><address>127.0.0.1:8385</address><apikey>abc</apikey></gui></configuration>",
           name="config.xml", flag=0):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if config_xml is not None:
            z.writestr(name, config_xml)
            z.infolist()[0].flag_bits |= flag  # the central directory, written on close, says it is encrypted
        else:
            z.writestr("other.txt", "x")
    return buf.getvalue()


SETTLED = {"ignorePerms": True, "maxConflicts": 0,
           "versioning": {"type": "simple", "params": {"keep": "5"}, "cleanupIntervalS": 3600, "fsPath": "", "fsType": "basic"}}


def plan(config):
    return android_syncthing.plan(config, SRV, DD, DF)


def folder(fid, path, devices=()):
    return {"id": fid, "path": path, "label": fid, "type": "sendreceive", "extra": 1,
            "devices": [{"deviceID": d} for d in devices]}


class ReadExport(unittest.TestCase):
    def test_read_export_key_and_port(self):
        self.assertEqual(android_syncthing.read_export(export()), ("abc", 8385))

    def test_read_export_default_port(self):
        xml = "<configuration><gui><apikey>abc</apikey></gui></configuration>"
        self.assertEqual(android_syncthing.read_export(export(xml)), ("abc", 8384))

    def test_read_export_ipv6_port(self):
        xml = "<configuration><gui><address>[::]:8384</address><apikey>k</apikey></gui></configuration>"
        self.assertEqual(android_syncthing.read_export(export(xml)), ("k", 8384))

    def test_read_export_not_zip(self):
        self.assertEqual(android_syncthing.read_export(b"nope"), "isn't a zip")

    def test_read_export_no_config(self):
        self.assertEqual(android_syncthing.read_export(export(None)), "has no config.xml")

    def test_read_export_bad_xml(self):
        self.assertEqual(android_syncthing.read_export(export("<a>")), "has a config.xml that can't be parsed")

    def test_read_export_no_key(self):
        xml = "<configuration><gui><address>x:1</address></gui></configuration>"
        self.assertEqual(android_syncthing.read_export(export(xml)), "has no API key")

    def test_read_export_encrypted(self):
        self.assertEqual(android_syncthing.read_export(export(flag=1)),
                         "is encrypted (export it without a backup password)")


class Plan(unittest.TestCase):
    def test_folder_paths(self):
        self.assertEqual(android_syncthing.folder_paths(SRV),
                         [("ra-saves", "RetroArch saves", android.DEFAULT_SAVES),
                          ("ra-states", "RetroArch states", android.DEFAULT_STATES)])

    def test_plan_empty_config_adds_device_and_folders(self):
        entries, calls, warns = plan({"devices": [], "folders": []})
        self.assertEqual(warns, [])
        self.assertEqual(len(entries), 9)
        self.assertEqual([e.new for e in entries if e.key == "folder ra-saves versioning"], ["simple, keep 5"])
        self.assertEqual(len(calls), 3)
        method, path, body = calls[0]
        self.assertEqual((method, path), ("PUT", f"/rest/config/devices/{SID}"))
        self.assertEqual(body["name"], "server")
        self.assertEqual(body["addresses"], ["tcp://server:22000"])
        self.assertEqual(body["compression"], "metadata")
        method, path, body = calls[1]
        self.assertEqual(path, "/rest/config/folders/ra-saves")
        self.assertEqual(body["type"], "sendreceive")
        self.assertEqual(body["path"], android.DEFAULT_SAVES)
        self.assertEqual(body["rescanIntervalS"], 3600)
        self.assertEqual(body["devices"], [{"deviceID": SID}])
        self.assertEqual(calls[2][2]["path"], android.DEFAULT_STATES)
        for key, value in SETTLED.items():
            self.assertEqual(body[key], value)

    def test_plan_existing_device_other_case_left(self):
        config = {"devices": [{"deviceID": SID.lower()}], "folders": []}
        entries, calls, _ = plan(config)
        self.assertFalse(applied.changed(entries[0]))
        self.assertEqual(len(calls), 2)

    def test_plan_folder_without_server_gets_it(self):
        config = {"devices": [{"deviceID": SID}],
                  "folders": [folder("ra-saves", android.DEFAULT_SAVES + "/", ["OTHER"])]}
        before = repr(config)
        entries, calls, _ = plan(config)
        self.assertEqual(repr(config), before)
        e = next(e for e in entries if e.key == "folder ra-saves")
        self.assertTrue(e.old.endswith("not shared with the server"))
        body = calls[0][2]
        self.assertEqual(calls[0][1], "/rest/config/folders/ra-saves")
        self.assertEqual(body["extra"], 1)
        self.assertEqual(body["devices"], [{"deviceID": "OTHER"}, {"deviceID": SID}])

    def test_plan_folder_at_other_path_warns(self):
        config = {"devices": [{"deviceID": SID}], "folders": [folder("ra-saves", "/elsewhere")]}
        entries, calls, warns = plan(config)
        self.assertEqual(warns, [f"Syncthing-Fork folder ra-saves is at /elsewhere, not {android.DEFAULT_SAVES}; left as it is"])
        self.assertNotIn("folder ra-saves", [e.key for e in entries])
        self.assertEqual([c[1] for c in calls], ["/rest/config/folders/ra-states"])

    def test_plan_other_folder_at_path_warns(self):
        config = {"devices": [{"deviceID": SID}], "folders": [folder("mine", android.DEFAULT_SAVES)]}
        entries, calls, warns = plan(config)
        self.assertEqual(warns, [f"Syncthing-Fork folder mine is already at {android.DEFAULT_SAVES}, so ra-saves isn't added there; left as it is"])
        self.assertNotIn("folder ra-saves", [e.key for e in entries])

    def test_plan_all_set_is_unchanged(self):
        config = {"devices": [{"deviceID": SID}],
                  "folders": [{**folder("ra-saves", android.DEFAULT_SAVES, [SID]), **SETTLED},
                              {**folder("ra-states", android.DEFAULT_STATES, [SID]), **SETTLED}]}
        entries, calls, warns = plan(config)
        self.assertEqual((calls, warns), ([], []))
        self.assertEqual(len(entries), 9)
        self.assertTrue(all(not applied.changed(e) for e in entries))

    def test_plan_shared_folder_gets_settings(self):
        config = {"devices": [{"deviceID": SID}], "folders": [folder("ra-saves", android.DEFAULT_SAVES, [SID])]}
        entries, calls, _ = plan(config)
        body = next(c[2] for c in calls if c[1] == "/rest/config/folders/ra-saves")
        for key, value in SETTLED.items():
            self.assertEqual(body[key], value)
        self.assertEqual(body["devices"], [{"deviceID": SID}])

    def test_plan_uses_given_paths(self):
        paths = {"saves": "/home/deck/s", "states": "/home/deck/t"}
        _, calls, _ = android_syncthing.plan({"devices": [], "folders": []}, SRV, DD, DF, paths=paths)
        body = next(c[2] for c in calls if c[1] == "/rest/config/folders/ra-saves")
        self.assertEqual(body["path"], "/home/deck/s")

    def test_plan_warning_names_where(self):
        config = {"devices": [], "folders": [folder("ra-saves", "/elsewhere")]}
        _, _, warns = android_syncthing.plan(config, SRV, DD, DF, where="Syncthing")
        self.assertTrue(warns[0].startswith("Syncthing folder ra-saves"))

    def test_plan_mod_time_window(self):
        _, calls, _ = android_syncthing.plan({"devices": [], "folders": []}, SRV, DD, DF, mod_time_window=2)
        body = next(c[2] for c in calls if c[1] == "/rest/config/folders/ra-saves")
        self.assertEqual(body["modTimeWindowS"], 2)
        config = {"devices": [{"deviceID": SID}],
                  "folders": [{**folder("ra-saves", android.DEFAULT_SAVES, [SID]), "modTimeWindowS": 0}]}
        entries, calls, _ = android_syncthing.plan(config, SRV, DD, DF, mod_time_window=2)
        body = next(c[2] for c in calls if c[1] == "/rest/config/folders/ra-saves")
        self.assertEqual(body["modTimeWindowS"], 2)
        self.assertTrue(any(e.key == "folder ra-saves modTimeWindowS" for e in entries))

    def test_api_http_scheme(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"{}"
        with mock.patch("urllib.request.urlopen", return_value=response) as opened:
            android_syncthing._api(1234, "k", "GET", "/rest/config", scheme="http")
        self.assertTrue(opened.call_args.args[0].full_url.startswith("http://127.0.0.1:"))
        self.assertNotIn("context", opened.call_args.kwargs)

    def test_configure_403_returns_none(self):
        error = urllib.error.HTTPError("u", 403, "Forbidden", {}, None)

        def api(port, key, method, path, body=None, scheme="https"):
            if path == "/rest/noauth/health":
                return None
            raise error
        err = io.StringIO()
        with mock.patch.object(android_syncthing, "_api", api), contextlib.redirect_stderr(err):
            self.assertIsNone(android_syncthing.configure(1, "secretkey", SRV, None, False))
        self.assertIn("refused", err.getvalue())
        self.assertNotIn("secretkey", err.getvalue())


class Apply(unittest.TestCase):
    """android_syncthing.apply with adb and the REST API mocked."""

    def setUp(self):
        self.out, self.err = io.StringIO(), io.StringIO()
        quiet = contextlib.ExitStack()
        quiet.enter_context(contextlib.redirect_stdout(self.out))
        quiet.enter_context(contextlib.redirect_stderr(self.err))
        self.addCleanup(quiet.close)
        self.shells, self.api_calls, self.removed = [], [], []
        self.sdk, self.packages = "30", f"package:{android_syncthing.PACKAGE}\npackage:other"
        self.whitelist, self.appops, self.dumpsys = "", "MANAGE_EXTERNAL_STORAGE: default", ""
        self.has_export, self.exported = True, export()
        self.srv, self.config, self.health, self.config_error = SRV, {"devices": [], "folders": []}, True, None
        for target, name, value in ((spruce_syncthing, "enabled", lambda: True),
                                    (spruce_syncthing, "server", lambda: self.srv),
                                    (adb, "shell", self.shell), (adb, "is_file", lambda s, p: self.has_export),
                                    (adb, "exec_out", lambda s, *w: self.exported),
                                    (adb, "forward", lambda s, port: 5555),
                                    (adb, "forward_remove", lambda s, port: self.removed.append(port)),
                                    (android_syncthing, "_api", self.api),
                                    (android_syncthing.time, "sleep", lambda t: None),
                                    (android_syncthing.time, "monotonic", itertools.count().__next__)):
            self.enterContext(mock.patch.object(target, name, value))

    def shell(self, serial, *words, check=True):
        self.shells.append(words)
        if words[:3] == ("pm", "list", "packages"):
            return self.packages
        if words[:3] == ("dumpsys", "deviceidle", "whitelist"):
            return self.whitelist
        if words[:2] == ("getprop", "ro.build.version.sdk"):
            return self.sdk + "\n"
        if words[:2] == ("appops", "get"):
            return self.appops
        if words[:2] == ("dumpsys", "package"):
            return self.dumpsys
        return ""

    def api(self, port, key, method, path, body=None, scheme="https"):
        self.api_calls.append((method, path, body))
        if path == "/rest/noauth/health":
            if not self.health:
                raise urllib.error.URLError("down")
            return {"status": "OK"}
        if self.config_error:
            raise self.config_error
        return {"/rest/config": self.config, "/rest/config/defaults/device": DD,
                "/rest/config/defaults/folder": DF}.get(path)

    def run_apply(self, dry_run=False):
        failed = []
        android_syncthing.apply("S", dry_run, failed)
        return failed

    def written(self):
        return [c for c in self.api_calls if c[0] != "GET"]

    def test_skips_when_syncthing_off(self):
        with mock.patch.object(spruce_syncthing, "enabled", lambda: False):
            self.assertEqual(self.run_apply(), [])
        self.assertEqual(self.shells, [])

    def test_not_installed_prints_hint(self):
        self.packages = "package:other"
        self.assertEqual(self.run_apply(), [])
        self.assertIn("Syncthing-Fork isn't installed: put its APK in os/android/APKs/ (config apply installs it) "
                      "or install it from F-Droid", self.out.getvalue())
        self.assertEqual(self.shells, [("pm", "list", "packages")])

    def test_access_entries_android_11(self):
        self.srv = None
        self.run_apply()
        pkg = android_syncthing.PACKAGE
        self.assertIn(("dumpsys", "deviceidle", "whitelist", f"+{pkg}"), self.shells)
        self.assertIn(("appops", "set", pkg, "MANAGE_EXTERNAL_STORAGE", "allow"), self.shells)
        self.assertIn("all files access = allow", self.out.getvalue())

    def test_access_entries_only_for_changed(self):
        self.srv = None
        pkg = android_syncthing.PACKAGE
        self.whitelist, self.appops = f"user,{pkg},10123", "MANAGE_EXTERNAL_STORAGE: allow"
        self.run_apply()
        self.assertFalse([w for w in self.shells if w[:2] == ("appops", "set") or w[:4] == ("dumpsys", "deviceidle", "whitelist", f"+{pkg}")])

    def test_access_entries_android_10(self):
        self.srv = None
        self.sdk = "29"
        self.run_apply()
        pkg = android_syncthing.PACKAGE
        self.assertIn(("pm", "grant", pkg, "android.permission.READ_EXTERNAL_STORAGE"), self.shells)
        self.assertIn(("pm", "grant", pkg, "android.permission.WRITE_EXTERNAL_STORAGE"), self.shells)
        self.assertFalse([w for w in self.shells if w[:2] == ("appops", "set")])
        self.assertIn("storage permission = granted", self.out.getvalue())

    def test_access_entries_android_10_already_granted(self):
        self.srv = None
        self.sdk = "29"
        self.dumpsys = "android.permission.WRITE_EXTERNAL_STORAGE: granted=true"
        self.run_apply()
        self.assertFalse([w for w in self.shells if w[:2] == ("pm", "grant")])

    def test_no_export_warns_without_failing(self):
        self.has_export = False
        self.assertEqual(self.run_apply(), [])
        self.assertIn("Syncthing-Fork has no export at /storage/emulated/0/backups/syncthing/config.zip", self.err.getvalue())
        self.assertEqual(self.api_calls, [])
        self.assertIn("all files access = allow", self.out.getvalue())

    def test_bad_export_warns_without_failing(self):
        self.exported = b"nope"
        self.assertEqual(self.run_apply(), [])
        self.assertIn("Syncthing-Fork's export isn't a zip; the server and folders aren't set", self.err.getvalue())

    def test_dry_run_never_launches_or_writes(self):
        self.health = False
        self.assertEqual(self.run_apply(True), [])
        self.assertFalse([w for w in self.shells if w[0] == "monkey"])
        self.assertEqual(self.written(), [])
        self.assertEqual([w for w in self.shells if w[:2] == ("appops", "set")], [])
        self.assertIn("Syncthing-Fork isn't running", self.out.getvalue())
        self.assertEqual(self.removed, [5555])

    def test_down_launches_app_then_warns(self):
        self.health = False
        self.assertEqual(self.run_apply(), [])
        self.assertTrue([w for w in self.shells if w[0] == "monkey"])
        self.assertIn("Syncthing-Fork isn't running", self.err.getvalue())

    def test_forward_removed_on_error(self):
        self.config_error = urllib.error.URLError("boom")
        self.assertEqual(self.run_apply(), ["Syncthing-Fork"])
        self.assertEqual(self.removed, [5555])

    def test_adb_error_fails(self):
        with mock.patch.object(adb, "exec_out", side_effect=adb.AdbError("lost")):
            self.assertEqual(self.run_apply(), ["Syncthing-Fork"])

    def test_rest_failure_still_shows_access_changes(self):
        self.config_error = urllib.error.URLError("boom")
        self.assertEqual(self.run_apply(), ["Syncthing-Fork"])
        self.assertIn("all files access = allow", self.out.getvalue())
        self.assertEqual(self.out.getvalue().count("all files access"), 1)

    def test_500_warns_and_fails(self):
        self.config_error = urllib.error.HTTPError("u", 500, "Server Error", {}, None)
        self.assertEqual(self.run_apply(), ["Syncthing-Fork"])
        self.assertIn("Syncthing-Fork:", self.err.getvalue())

    def test_403_warns_without_failing(self):
        self.config_error = urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
        self.assertEqual(self.run_apply(), [])
        self.assertIn("refused the export's API key", self.err.getvalue())
        self.assertEqual(self.removed, [5555])

    def test_real_run_sends_planned_calls(self):
        self.assertEqual(self.run_apply(), [])
        self.assertEqual([(m, p) for m, p, _ in self.written()],
                         [("PUT", f"/rest/config/devices/{SID}"), ("PUT", "/rest/config/folders/ra-saves"),
                          ("PUT", "/rest/config/folders/ra-states")])
        self.assertIn("device server", self.out.getvalue())
        self.assertEqual(self.removed, [5555])

    def test_dry_run_shows_plan_without_writing(self):
        self.assertEqual(self.run_apply(True), [])
        self.assertEqual(self.written(), [])
        self.assertIn("would set   device server", self.out.getvalue())

    def test_plan_warnings_are_printed(self):
        self.config = {"devices": [], "folders": [folder("ra-saves", "/elsewhere")]}
        self.run_apply()
        self.assertIn("ra-saves is at /elsewhere", self.err.getvalue())


if __name__ == "__main__":
    unittest.main()
