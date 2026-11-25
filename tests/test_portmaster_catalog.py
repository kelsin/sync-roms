import contextlib
import io
import json
import os
import time
import unittest
from unittest import mock

import helpers
from sync_roms import portmaster_catalog as pc

CATALOG = {
    "ports": {
        "celeste.zip": {"name": "celeste.zip", "attr": {"title": "Celeste", "desc": "A climbing platformer.", "genres": ["platformer"],
                                                        "rtr": False, "runtime": "mono-6.12.0.122-aarch64.squashfs", "arch": ["aarch64"]}},
        "2048.zip": {"name": "2048.zip", "attr": {"title": "2048", "desc": "Slide tiles.", "genres": ["puzzle"], "rtr": True, "runtime": None}},
        "armonly.zip": {"name": "armonly.zip", "attr": {"title": "Arm Only", "desc": "x", "genres": [], "rtr": True, "arch": ["armhf"]}},
    },
    "utils": {
        "mono-6.12.0.122-aarch64.squashfs": {"name": "mono-6.12.0.122-aarch64.squashfs", "md5": "a", "size": 1, "url": "u1"},
        "frt_3.5.2.armhf.squashfs": {"name": "frt_3.5.2.armhf.squashfs", "md5": "b", "size": 2, "url": "u2"},
    },
}


class Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self.data).encode()


class CatalogTests(helpers.DataDir):
    def cache(self, age=0):
        os.makedirs(os.path.dirname(pc.path()), exist_ok=True)
        with open(pc.path(), "w") as f:
            json.dump(CATALOG, f)
        then = time.time() - age
        os.utime(pc.path(), (then, then))

    def test_ports_drops_non_aarch64(self):
        self.assertEqual(sorted(pc.ports(CATALOG)), ["2048.zip", "celeste.zip"])

    def test_search_matches_all_words_in_title_genre_desc(self):
        self.assertEqual([e["zip"] for e in pc.search(CATALOG, "climbing PLATFORMER celeste")], ["celeste.zip"])
        self.assertEqual([e["zip"] for e in pc.search(CATALOG, "")], ["2048.zip", "celeste.zip"])
        self.assertEqual(pc.search(CATALOG, "celeste puzzle"), [])

    def test_search_needs_data_filter(self):
        self.assertEqual([e["zip"] for e in pc.search(CATALOG, "", needs_data=True)], ["celeste.zip"])
        self.assertEqual([e["zip"] for e in pc.search(CATALOG, "", needs_data=False)], ["2048.zip"])

    def test_resolve_accepts_bare_name(self):
        self.assertEqual(pc.resolve(CATALOG, "Celeste"), "celeste.zip")
        self.assertEqual(pc.resolve(CATALOG, "celeste.ZIP"), "celeste.zip")
        self.assertIsNone(pc.resolve(CATALOG, "armonly"))

    def test_runtimes_drops_other_arches(self):
        self.assertEqual(pc.runtimes(CATALOG["ports"]["celeste.zip"]), ["mono-6.12.0.122-aarch64.squashfs"])
        self.assertEqual(pc.runtimes(CATALOG["ports"]["2048.zip"]), [])
        self.assertEqual(pc.runtimes({"attr": {"runtime": ["frt_3.5.2.armhf.squashfs", "a.squashfs"]}}), ["a.squashfs"])
        self.assertEqual(pc.runtime_source(CATALOG, "frt_3.5.2.armhf.squashfs")["md5"], "b")
        self.assertIsNone(pc.runtime_source(CATALOG, "nope"))

    def test_load_uses_fresh_cache_without_fetching(self):
        self.cache()
        with mock.patch.object(pc.github, "get", side_effect=AssertionError("fetched")):
            self.assertEqual(pc.load(), CATALOG)

    def test_load_refetches_stale_cache(self):
        self.cache(age=2 * 86400)
        new = {"ports": {}, "utils": {}}
        with mock.patch.object(pc.github, "get", return_value=Response(new)) as get:
            self.assertEqual(pc.load(), new)
        get.assert_called_once_with(pc.URL)
        with open(pc.path()) as f:
            self.assertEqual(json.load(f), new)

    def test_load_refresh_refetches_fresh_cache(self):
        self.cache()
        with mock.patch.object(pc.github, "get", return_value=Response({"ports": {}})) as get:
            pc.load(refresh=True)
        get.assert_called_once()

    def test_load_falls_back_to_cache_on_error(self):
        self.cache(age=2 * 86400)
        err = io.StringIO()
        with mock.patch.object(pc.github, "get", side_effect=OSError("down")), contextlib.redirect_stderr(err):
            self.assertEqual(pc.load(), CATALOG)
        self.assertIn("down", err.getvalue())

    def test_load_without_fetch_returns_none_when_no_cache(self):
        with mock.patch.object(pc.github, "get", side_effect=AssertionError("fetched")):
            self.assertIsNone(pc.load(fetch=False))
        self.cache(age=5 * 86400)
        with mock.patch.object(pc.github, "get", side_effect=AssertionError("fetched")):
            self.assertEqual(pc.load(fetch=False), CATALOG)


if __name__ == "__main__":
    unittest.main()
