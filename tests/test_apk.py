import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
from sync_roms import apk, store  # noqa: E402


def _chunk(kind, header, body):
    return struct.pack("<HHI", kind, header, header + len(body)) + body


def _string(text, utf8):
    if utf8:
        data = text.encode()
        return bytes([len(text), len(data)]) + data + b"\0"
    return struct.pack("<H", len(text)) + text.encode("utf-16-le") + b"\0\0"


def manifest_bytes(package="com.example.app", version=42, utf8=False):
    """A minimal binary AndroidManifest.xml: a string pool, a resource map and one <manifest package versionCode> element."""
    strings = ["manifest", "package", "versionCode", package]
    blobs, offsets, at = [], [], 0
    for text in strings:
        blob = _string(text, utf8)
        offsets.append(at)
        blobs.append(blob)
        at += len(blob)
    packed = b"".join(blobs)
    packed += b"\0" * (-len(packed) % 4)
    pool_header = struct.pack("<IIIII", len(strings), 0, 0x100 if utf8 else 0, 28 + 4 * len(strings), 0)
    body = pool_header + struct.pack(f"<{len(strings)}I", *offsets) + packed
    pool = struct.pack("<HHI", 1, 28, 8 + len(body)) + body
    resource_map = _chunk(0x180, 8, struct.pack("<III", 0, 0, 0x0101021B))
    attrs = (struct.pack("<iiiHBBI", -1, 1, 3, 8, 0, 0x03, 3)
             + struct.pack("<iiiHBBI", -1, 2, -1, 8, 0, 0x10, version))
    start = struct.pack("<HHI", 0x102, 16, 36 + len(attrs)) + struct.pack("<II", 1, 0xFFFFFFFF) \
        + struct.pack("<iiHHHHHH", -1, 0, 20, 20, 2, 0, 0, 0) + attrs
    content = pool + resource_map + start
    return struct.pack("<HHI", 3, 8, 8 + len(content)) + content


class Manifest(unittest.TestCase):
    def test_reads_package_and_version(self):
        for utf8 in (False, True):
            self.assertEqual(apk.manifest(manifest_bytes(utf8=utf8)), ("com.example.app", 42))

    def test_garbage(self):
        for data in (b"", b"hello world, not xml", manifest_bytes()[:40], b"\x03\x00\x08\x00\x08\x00\x00\x00"):
            with self.assertRaises(ValueError):
                apk.manifest(data)


class ApksData(unittest.TestCase):
    def test_shape(self):
        data = store.repo_json("android-apks")
        self.assertIsInstance(data["note"], str)
        tiers = {t["id"] for t in store.repo_json("device-systems")["tiers"]}
        systems = {s["bucket"] for s in store.repo_json("systems")}
        for rule in data["apks"]:
            self.assertEqual(set(rule) - {"prefix", "never", "tier", "systems", "dualscreen"}, set())
            self.assertIn(rule.get("tier", "switch"), tiers)
            self.assertTrue(set(rule.get("systems", [])) <= systems)
