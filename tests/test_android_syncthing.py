import io
import os
import sys
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import android, android_syncthing, applied  # noqa: E402

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
        self.assertEqual([e.old for e in entries], [None, None, None])
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
                  "folders": [folder("ra-saves", android.DEFAULT_SAVES, [SID]),
                              folder("ra-states", android.DEFAULT_STATES, [SID])]}
        entries, calls, warns = plan(config)
        self.assertEqual((calls, warns), ([], []))
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(not applied.changed(e) for e in entries))


if __name__ == "__main__":
    unittest.main()
