import contextlib
import io
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import adb, android_access, applied  # noqa: E402

PKG = "com.example.app"


class Access(unittest.TestCase):
    def setUp(self):
        self.shells = []
        self.whitelist, self.appops, self.sdk, self.dumpsys = "", "MANAGE_EXTERNAL_STORAGE: default", "30", ""
        self.enterContext(mock.patch.object(adb, "shell", self.shell))

    def shell(self, serial, *words, check=True):
        self.shells.append(words)
        if words[:3] == ("dumpsys", "deviceidle", "whitelist") and len(words) == 3:
            return self.whitelist
        if words[0] == "getprop":
            return self.sdk + "\n"
        if words[0] == "appops" and words[1] == "get":
            return self.appops
        if words[:2] == ("dumpsys", "package"):
            return self.dumpsys
        return ""

    def test_entries_android_11(self):
        result = android_access.entries("S", PKG, "App")
        self.assertEqual([(e.where, e.key, e.old, e.new) for e, _ in result],
                         [("App", "battery optimization", "on", "exempt"), ("App", "all files access", "default", "allow")])
        self.assertEqual([c for _, c in result], [[["dumpsys", "deviceidle", "whitelist", f"+{PKG}"]],
                                                  [["appops", "set", PKG, "MANAGE_EXTERNAL_STORAGE", "allow"]]])

    def test_entries_read_current_state(self):
        self.whitelist, self.appops = f"user,{PKG},10123", "Uid mode: MANAGE_EXTERNAL_STORAGE: allow\nMANAGE_EXTERNAL_STORAGE: default"
        result = android_access.entries("S", PKG, "App")
        self.assertEqual([applied.changed(e) for e, _ in result], [False, False])

    def test_entries_android_10(self):
        self.sdk = "29"
        result = android_access.entries("S", PKG, "App")
        self.assertEqual(result[1][0].key, "storage permission")
        self.assertEqual([c[3] for c in result[1][1]],
                         ["android.permission.READ_EXTERNAL_STORAGE", "android.permission.WRITE_EXTERNAL_STORAGE"])

    def test_apply_runs_only_changed(self):
        self.whitelist = f"user,{PKG},10123"
        result = android_access.entries("S", PKG, "App")
        self.shells.clear()
        android_access.apply("S", result)
        self.assertEqual(self.shells, [("appops", "set", PKG, "MANAGE_EXTERNAL_STORAGE", "allow")])
