import contextlib
import io
import os
import stat
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import raofflineproxy, store  # noqa: E402

V = "v3.1.0-alpha1"


def make_zip(root, extra=None, symlink=None, launch=True):
    members = {f"{root}/app/main.py": b"py", f"{root}/data/": None, **(extra or {})}
    if launch:
        members[f"{root}/launch.sh"] = b"#!/bin/sh"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            if data is None:
                z.writestr(name, b"")
                continue
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o755 if name.endswith("launch.sh") else 0o644) << 16
            z.writestr(info, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = 0o120777 << 16
            z.writestr(info, "target")
    return buf.getvalue()


LAYOUTS = {
    "onion": (f"os/onion/RAOfflineProxy-Onion-{V}.zip", "App/RAOfflineProxy", "App/RAOfflineProxy"),
    "allium": (f"os/allium/RAOfflineProxy-Allium-{V}.zip", "Apps/RAOfflineProxy.pak", "Apps/RAOfflineProxy.pak"),
    "muos": (f"os/muOS/RAOfflineProxy-muOS-{V}.muxapp", "RAOfflineProxy", "MUOS/application/RAOfflineProxy"),
}
KNULLI = f"os/knulli/RAOfflineProxy-Knulli-{V}-Install.sh"
SCRIPT = os.path.join("roms", "tools", "RAOfflineProxy Install.sh")
ROCKNIX = f"os/rocknix/RAOfflineProxy-Rocknix-{V}-Install.sh"
PORTS_SCRIPT = os.path.join("roms", "ports", "RAOfflineProxy Install.sh")


class Install(helpers.CardDir):
    FIELD = "raofflineproxy_app"

    def setUp(self):
        super().setUp()
        store.update_card("c", layout="onion")

    def run_install(self, layout, dry_run=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.failures = raofflineproxy.install("c", layout, self.card, dry_run)
        return out.getvalue()

    def test_each_zip_layout_installs_at_its_folder(self):
        for layout, (key, root, dest) in LAYOUTS.items():
            with self.subTest(layout):
                self.put(key, make_zip(root))
                self.run_install(layout)
                self.assertEqual(self.failures, 0)
                self.assertTrue(os.path.isfile(self.cp(*dest.split("/"), "app", "main.py")))
                self.assertTrue(os.stat(self.cp(*dest.split("/"), "launch.sh")).st_mode & stat.S_IXUSR)
                self.assertFalse(os.stat(self.cp(*dest.split("/"), "app", "main.py")).st_mode & stat.S_IXUSR)
                self.assertEqual(self.recorded(), os.path.basename(key))

    def test_knulli_copies_the_install_script(self):
        self.put(KNULLI, b"#!/bin/sh\necho hi")
        self.run_install("knulli")
        self.assertEqual(self.failures, 0)
        with open(self.cp(SCRIPT), "rb") as f:
            self.assertEqual(f.read(), b"#!/bin/sh\necho hi")
        self.assertTrue(os.stat(self.cp(SCRIPT)).st_mode & stat.S_IXUSR)
        self.assertEqual(self.recorded(), os.path.basename(KNULLI))

    def test_knulli_is_once_per_name_without_a_presence_check(self):
        self.put(KNULLI, b"x")
        self.run_install("knulli")
        os.remove(self.cp(SCRIPT))  # the script deletes itself after running
        self.run_install("knulli")
        self.assertFalse(os.path.exists(self.cp(SCRIPT)))
        self.put(KNULLI.replace("alpha1", "alpha2"), b"y")
        self.run_install("knulli")
        self.assertTrue(os.path.exists(self.cp(SCRIPT)))

    def test_rocknix_copies_the_install_script_to_ports_once_per_name(self):
        self.put(ROCKNIX, b"#!/bin/sh\necho hi")
        self.run_install("rocknix")
        self.assertEqual(self.failures, 0)
        with open(self.cp(PORTS_SCRIPT), "rb") as f:
            self.assertEqual(f.read(), b"#!/bin/sh\necho hi")
        self.assertTrue(os.stat(self.cp(PORTS_SCRIPT)).st_mode & stat.S_IXUSR)
        self.assertEqual(self.recorded(), os.path.basename(ROCKNIX))
        os.remove(self.cp(PORTS_SCRIPT))  # the script deletes itself after running
        self.run_install("rocknix")
        self.assertFalse(os.path.exists(self.cp(PORTS_SCRIPT)))
        self.put(ROCKNIX.replace("alpha1", "alpha2"), b"y")
        self.run_install("rocknix")
        self.assertTrue(os.path.exists(self.cp(PORTS_SCRIPT)))

    def test_rocknix_prefix_is_listed(self):
        self.assertIn("os/rocknix/", raofflineproxy.prefixes())

    def test_other_layouts_get_nothing(self):
        self.put(LAYOUTS["onion"][0], make_zip("App/RAOfflineProxy"))
        for layout in ("spruce", "emudeck", "nextui", "esde"):
            self.run_install(layout)
        self.assertEqual(self.snapshot(), [])

    def test_newest_version_by_number(self):
        for v in ("v3.2.0", "v3.10.0", "v3.9.0"):
            self.put(f"os/onion/RAOfflineProxy-Onion-{v}.zip", make_zip("App/RAOfflineProxy"))
        self.put("os/onion/Surprise-v9.0.0.zip")
        self.run_install("onion")
        self.assertEqual(self.recorded(), "RAOfflineProxy-Onion-v3.10.0.zip")

    def test_recorded_and_present_skips_but_missing_launch_reinstalls(self):
        key, root, dest = LAYOUTS["allium"]
        self.put(key, make_zip(root))
        self.run_install("allium")
        launch = self.cp(*dest.split("/"), "launch.sh")
        open(self.cp(*dest.split("/"), "marker"), "w").close()
        with open(launch, "w") as f:
            f.write("mine")
        self.run_install("allium")
        with open(launch) as f:
            self.assertEqual(f.read(), "mine")
        os.remove(launch)
        self.run_install("allium")
        self.assertTrue(os.path.isfile(launch))

    def test_new_name_reinstalls_and_keeps_user_files(self):
        key, root, dest = LAYOUTS["onion"]
        self.put(key, make_zip(root))
        self.run_install("onion")
        app = self.cp(*dest.split("/"))
        os.makedirs(os.path.join(app, "config"))
        with open(os.path.join(app, "config", "login.json"), "w") as f:
            f.write("secret")
        with open(os.path.join(app, "app", "main.py"), "w") as f:
            f.write("old")
        self.put("os/onion/RAOfflineProxy-Onion-v3.2.0.zip", make_zip(root, {f"{root}/app/main.py": b"new"}))
        self.run_install("onion")
        with open(os.path.join(app, "config", "login.json")) as f:
            self.assertEqual(f.read(), "secret")
        with open(os.path.join(app, "app", "main.py"), "rb") as f:
            self.assertEqual(f.read(), b"new")
        self.assertEqual(self.recorded(), "RAOfflineProxy-Onion-v3.2.0.zip")

    def test_off_installs_nothing(self):
        store.update_card("c", raofflineproxy=False)
        self.put(LAYOUTS["onion"][0], make_zip("App/RAOfflineProxy"))
        self.put(KNULLI)
        self.run_install("onion")
        self.run_install("knulli")
        self.assertEqual(self.snapshot(), [])
        self.assertIsNone(self.recorded())

    def test_unsafe_zips_are_rejected(self):
        key, root, dest = LAYOUTS["onion"]
        for label, data in {"escape": make_zip(root, {"../evil": b"x"}),
                            "outside": make_zip(root, {"Other/x": b"x"}),
                            "symlink": make_zip(root, symlink=f"{root}/link"),
                            "no launch": make_zip(root, launch=False),
                            "not a zip": b"nope"}.items():
            with self.subTest(label):
                self.put(key, data)
                with contextlib.redirect_stderr(io.StringIO()):
                    self.run_install("onion")
                self.assertEqual(self.failures, 1)
                self.assertEqual(self.snapshot(), [])
                self.assertIsNone(self.recorded())

    def test_dry_run_writes_nothing(self):
        self.put(LAYOUTS["onion"][0], make_zip("App/RAOfflineProxy"))
        out = self.run_install("onion", dry_run=True)
        self.assertIn("would install RAOfflineProxy", out)
        self.assertEqual(self.snapshot(), [])
        self.assertIsNone(self.recorded())


if __name__ == "__main__":
    unittest.main()
