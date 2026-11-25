import contextlib
import hashlib
import io
import os
import unittest
from unittest import mock

import helpers
from sync_roms import github, portmaster_catalog, portmaster_store, usersettings

META = "scrapes/ports/metadata.json"
DATA = {"u-celeste": b"celeste-v1", "u-2048": b"2048-v1", "u-mono": b"mono-rt", "u-celeste2": b"celeste-v2"}


def md5(data):
    return hashlib.md5(data).hexdigest()


def catalog(celeste_url="u-celeste"):
    return {
        "ports": {
            "celeste.zip": {"name": "celeste.zip", "items": ["Celeste.sh", "celeste/"],
                            "attr": {"title": "Celeste", "rtr": False, "inst": "Copy your game files.",
                                     "runtime": ["mono-6.12.0.122-aarch64.squashfs", "frt.armhf.squashfs"],
                                     "arch": ["aarch64"]},
                            "source": {"url": celeste_url, "md5": md5(DATA[celeste_url]), "size": len(DATA[celeste_url])}},
            "2048.zip": {"name": "2048.zip", "items": ["2048.sh", "2048"], "attr": {"title": "2048", "rtr": True, "runtime": None},
                         "source": {"url": "u-2048", "md5": md5(DATA["u-2048"]), "size": len(DATA["u-2048"])}},
        },
        "utils": {"mono-6.12.0.122-aarch64.squashfs": {"name": "mono-6.12.0.122-aarch64.squashfs", "url": "u-mono",
                                                       "md5": md5(DATA["u-mono"]), "size": len(DATA["u-mono"])}},
    }


class Download(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.catalog = catalog()
        self.fetched = []
        self.enterContext(mock.patch.object(usersettings, "ensure_bucket"))
        self.enterContext(mock.patch.object(portmaster_catalog, "load", side_effect=lambda **kw: self.catalog))
        self.enterContext(mock.patch.object(github, "download", side_effect=self.fake_download))

    def fake_download(self, url, path, callback=None):
        self.fetched.append(url)
        with open(path, "wb") as f:
            f.write(DATA.get(url, b"garbage"))

    def run_download(self, names, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = portmaster_store.download(names, **kw)
        return code, out.getvalue(), err.getvalue()

    def stored(self, key):
        path = os.path.join(self.root, key)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def test_download_puts_zip_runtime_and_metadata(self):
        code, _, err = self.run_download(["celeste"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.stored("ports/celeste.zip"), DATA["u-celeste"])
        self.assertEqual(self.stored("os/portmaster/runtimes/mono-6.12.0.122-aarch64.squashfs"), DATA["u-mono"])
        self.assertEqual(self.read_json(META), {"celeste.zip": {"name": "Celeste", "portmaster": {
            "folder": "celeste", "items": ["Celeste.sh", "celeste/"], "rtr": False, "inst": "Copy your game files.",
            "runtime": ["mono-6.12.0.122-aarch64.squashfs"], "md5": md5(DATA["u-celeste"]), "size": len(DATA["u-celeste"])}}})

    def test_runtime_already_in_storage_is_not_downloaded(self):
        self.put("os/portmaster/runtimes/mono-6.12.0.122-aarch64.squashfs", b"old")
        self.assertEqual(self.run_download(["celeste.zip"])[0], 0)
        self.assertEqual(self.fetched, ["u-celeste"])

    def test_download_skips_zip_already_in_storage(self):
        self.put("ports/celeste.zip", b"by hand")
        code, out, _ = self.run_download(["celeste"])
        self.assertEqual(code, 0)
        self.assertEqual(self.fetched, [])
        self.assertEqual(self.stored("ports/celeste.zip"), b"by hand")
        self.assertIn("celeste.zip", out)

    def test_update_replaces_only_changed_md5(self):
        self.assertEqual(self.run_download(["celeste", "2048"])[0], 0)
        self.catalog = catalog("u-celeste2")
        self.fetched.clear()
        self.assertEqual(self.run_download(["celeste", "2048"], update=True)[0], 0)
        self.assertEqual(self.fetched, ["u-celeste2"])
        self.assertEqual(self.stored("ports/celeste.zip"), DATA["u-celeste2"])
        self.assertEqual(self.read_json(META)["celeste.zip"]["portmaster"]["md5"], md5(DATA["u-celeste2"]))

    def test_update_without_names_updates_all_outdated(self):
        self.assertEqual(self.run_download(["celeste", "2048"])[0], 0)
        self.put("ports/unknown.zip", b"not in the catalogue")
        self.catalog = catalog("u-celeste2")
        self.fetched.clear()
        self.assertEqual(self.run_download([], update=True)[0], 0)
        self.assertEqual(self.fetched, ["u-celeste2"])

    def test_md5_mismatch_uploads_nothing_and_exits_1(self):
        self.catalog["ports"]["celeste.zip"]["source"]["md5"] = "0" * 32
        code, _, err = self.run_download(["celeste"])
        self.assertEqual(code, 1)
        self.assertIn("md5", err)
        self.assertIsNone(self.stored("ports/celeste.zip"))
        self.assertIsNone(self.stored("os/portmaster/runtimes/mono-6.12.0.122-aarch64.squashfs"))
        self.assertIsNone(self.stored(META))

    def test_http_error_warns_and_exits_1(self):
        with mock.patch.object(github, "download", side_effect=OSError("boom")):
            code, _, err = self.run_download(["2048"])
        self.assertEqual(code, 1)
        self.assertIn("boom", err)
        self.assertIsNone(self.stored("ports/2048.zip"))

    def test_unknown_name_warns_and_others_continue(self):
        code, _, err = self.run_download(["nope", "2048"])
        self.assertEqual(code, 1)
        self.assertIn("nope", err)
        self.assertEqual(self.stored("ports/2048.zip"), DATA["u-2048"])

    def test_metadata_keeps_existing_name(self):
        self.put(META, b'{"2048.zip": {"name": "Twenty Forty-Eight", "genre": "x"}}')
        self.assertEqual(self.run_download(["2048"])[0], 0)
        entry = self.read_json(META)["2048.zip"]
        self.assertEqual((entry["name"], entry["genre"], entry["portmaster"]["folder"]), ("Twenty Forty-Eight", "x", "2048"))

    def test_remind_outdated_lists_titles(self):
        self.assertEqual(self.run_download(["celeste", "2048"])[0], 0)
        self.catalog = catalog("u-celeste2")
        _, out, _ = self.run_download(["2048"])
        self.assertIn("1 ports in storage have newer versions: Celeste. Run sync-roms ports download --update", out)
        self.assertEqual(portmaster_store.outdated(self.catalog), ["celeste.zip"])

    def test_missing_metadata_counts_as_outdated(self):
        self.put("ports/2048.zip", b"by hand")
        self.assertEqual(portmaster_store.outdated(self.catalog), ["2048.zip"])

    def test_dry_run_writes_nothing(self):
        code, out, _ = self.run_download(["celeste"], dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual(self.fetched, [])
        self.assertIn("celeste.zip", out)
        self.assertEqual(os.listdir(self.root), [])

    def test_no_catalogue_exits_1(self):
        self.catalog = None
        self.assertEqual(self.run_download(["celeste"])[0], 1)

    def test_cli_passes_flags(self):
        with mock.patch.object(portmaster_store, "download", return_value=0) as download:
            code, _, _ = helpers.Cmd.run_cmd(self, "ports", "download", "celeste", "--update", "--refresh", "-n")
        self.assertEqual(code, 0)
        download.assert_called_once_with(["celeste"], update=True, refresh=True, dry_run=True)


if __name__ == "__main__":
    unittest.main()
