import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402

from sync_roms import commands, custom_themes, downloads, runtime, usersettings  # noqa: E402

CONFIG = {"name": "SPRUCE", "author": "spruce", "description": "x", "screensaver": {"bgColor": "#282828"}, "extra": 1}


def png(path, size, color=(0, 0, 0, 0)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGBA", size, color).save(path)


def make_base(path, ssh=True):
    with open(os.path.join(_mk(path), "config.json"), "w") as f:
        json.dump(CONFIG, f)
    png(os.path.join(path, "skin", "background.png"), (640, 480), (40, 40, 40, 255))
    for name in ("app_loading_bg.png", "bg-gamelist.png", "bg-title.png", "tips-bar-bg.png", "menu-5line-bg.png", "menu-6line-bg.png"):
        png(os.path.join(path, "skin", name), (640, 480), (40, 40, 40, 255))
    for name in ("menu-5line-bg.png", "menu-6line-bg.png"):
        png(os.path.join(path, "skin_640_480", name), (640, 480), (40, 40, 40, 255))
    png(os.path.join(path, "icons", "gba.png"), (120, 130))
    png(os.path.join(path, "icons", "sel", "gba.png"), (120, 130))
    png(os.path.join(path, "icons_720x540", "gba.png"), (134, 146))
    if ssh:
        png(os.path.join(path, "icons", "app", "SSH.png"), (70, 70))


def _mk(path):
    os.makedirs(path, exist_ok=True)
    return path


def hashes(root):
    out = {}
    for dirpath, _, files in os.walk(root):
        for file in files:
            p = os.path.join(dirpath, file)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = hashlib.sha256(f.read()).hexdigest()
    return dict(sorted(out.items()))


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = os.path.join(self.tmp.name, "base")

    def test_registry_names(self):
        self.assertEqual(custom_themes.names(), ["Pixel Consoles", "Pixel Controllers"])
        for module in custom_themes.THEMES.values():
            self.assertEqual(module.BASE, "SPRUCE")

    def test_build_overlays_base(self):
        make_base(self.base)
        module = custom_themes.THEMES["Pixel Consoles"]
        dest = module.build(self.base, os.path.join(self.tmp.name, "out"))
        self.assertEqual(dest, os.path.join(self.tmp.name, "out", module.NAME))
        with Image.open(os.path.join(dest, "skin", "background.png")) as im:
            self.assertEqual(set(im.convert("RGBA").getdata()), {(0, 0, 0, 255)})
        with Image.open(os.path.join(dest, "icons", "sel", "gba.png")) as im:
            self.assertIsNotNone(im.convert("RGBA").getbbox())
        with open(os.path.join(dest, "config.json")) as f:
            config = json.load(f)
        self.assertEqual(config["name"], module.NAME)
        self.assertEqual(config["screensaver"]["bgColor"], "#000000")
        self.assertEqual(config["extra"], 1)
        with Image.open(os.path.join(dest, "icons_720x540", "gba.png")) as im:
            self.assertEqual(im.size, (134, 146))

    def test_build_is_deterministic(self):
        make_base(self.base)
        module = custom_themes.THEMES["Pixel Controllers"]
        a = module.build(self.base, os.path.join(self.tmp.name, "a"))
        b = module.build(self.base, os.path.join(self.tmp.name, "b"))
        self.assertEqual(hashes(a), hashes(b))

    def test_files_missing_in_base_are_skipped(self):
        make_base(self.base)
        os.remove(os.path.join(self.base, "skin", "bg-title.png"))
        os.remove(os.path.join(self.base, "skin", "background.png"))
        dest = custom_themes.THEMES["Pixel Consoles"].build(self.base, os.path.join(self.tmp.name, "out"))
        self.assertFalse(os.path.exists(os.path.join(dest, "skin", "bg-title.png")))

    def test_icon_folders_missing_in_base_are_created(self):
        os.makedirs(self.base)
        dest = custom_themes.THEMES["Pixel Controllers"].build(self.base, os.path.join(self.tmp.name, "out"))
        self.assertTrue(os.path.exists(os.path.join(dest, "icons", "sel", "gba.png")))

    def test_icons_missing_in_base_are_skipped(self):
        make_base(self.base, ssh=False)
        dest = custom_themes.THEMES["Pixel Consoles"].build(self.base, os.path.join(self.tmp.name, "out"))
        self.assertFalse(os.path.exists(os.path.join(dest, "icons", "app", "SSH.png")))


class Fetch(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(usersettings, "apply_settings"))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def test_fetch_base_copies_files(self):
        self.put("os/spruceos/themes/SPRUCE/config.json", b'{"a": 1}')
        self.put("os/spruceos/themes/SPRUCE/skin/background.png", b"png-bytes")
        folder = custom_themes.fetch_base("SPRUCE")
        with open(os.path.join(folder, "config.json"), "rb") as f:
            self.assertEqual(f.read(), b'{"a": 1}')
        with open(os.path.join(folder, "skin", "background.png"), "rb") as f:
            self.assertEqual(f.read(), b"png-bytes")

    def test_fetch_base_reuses_same_size(self):
        self.put("os/spruceos/themes/SPRUCE/config.json", b"{}")
        custom_themes.fetch_base("SPRUCE")
        with mock.patch.object(downloads, "run_downloads", wraps=downloads.run_downloads) as run:
            custom_themes.fetch_base("SPRUCE")
        self.assertEqual(run.call_args.args[0], [])

    def test_fetch_base_missing(self):
        self.put("os/spruceos/themes/Other/config.json", b"{}")
        with self.assertRaises(custom_themes.BaseMissing):
            custom_themes.fetch_base("SPRUCE")

    def test_fetch_base_unmounted(self):
        with mock.patch.object(runtime, "ROOT", os.path.join(self.tmp.name, "gone")):
            with self.assertRaises(FileNotFoundError):
                custom_themes.fetch_base("SPRUCE")

    def test_fetch_base_failed_download_stops(self):
        self.put("os/spruceos/themes/SPRUCE/config.json", b"{}")
        with mock.patch.object(downloads, "run_downloads", return_value=1):
            with self.assertRaisesRegex(custom_themes.DownloadFailed, "1 file"):
                custom_themes.fetch_base("SPRUCE")

    def test_build_command_failed_download_exits_1(self):
        make_base(os.path.join(self.root, "os", "spruceos", "themes", "SPRUCE"))
        with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr"), \
                mock.patch.object(downloads, "run_downloads", return_value=2):
            commands.run(["themes", "build", "--out", os.path.join(self.tmp.name, "out")])
        self.assertEqual(raised.exception.code, 1)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "out")))

    def test_fetch_base_prunes_files_gone_from_storage(self):
        old = self.put("os/spruceos/themes/SPRUCE/icons/old/a.png")
        self.put("os/spruceos/themes/SPRUCE/config.json", b"{}")
        folder = custom_themes.fetch_base("SPRUCE")
        self.assertTrue(os.path.exists(os.path.join(folder, "icons", "old", "a.png")))
        os.remove(old)
        custom_themes.fetch_base("SPRUCE")
        self.assertFalse(os.path.exists(os.path.join(folder, "icons")))
        self.assertTrue(os.path.exists(os.path.join(folder, "config.json")))

    def test_build_command_unmounted_storage_exits_1(self):
        with mock.patch.object(runtime, "ROOT", os.path.join(self.tmp.name, "gone")):
            with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr") as err:
                commands.run(["themes", "build"])
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("gone", "".join(c.args[0] for c in err.write.call_args_list))

    def test_build_command_writes_to_out(self):
        make_base(os.path.join(self.root, "os", "spruceos", "themes", "SPRUCE"))
        out = os.path.join(self.tmp.name, "out")
        self.assertEqual(commands.run(["themes", "build", "Pixel Consoles", "--out", out]), 0)
        self.assertTrue(os.path.exists(os.path.join(out, "Pixel Consoles", "config.json")))
        self.assertFalse(os.path.exists(os.path.join(out, "Pixel Controllers")))

    def test_build_command_unknown_name(self):
        with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr") as err:
            commands.run(["themes", "build", "Nope"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("Pixel Consoles", "".join(c.args[0] for c in err.write.call_args_list))

    def test_build_command_base_missing(self):
        with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr") as err:
            commands.run(["themes", "build", "--out", os.path.join(self.tmp.name, "out")])
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("themes update", "".join(c.args[0] for c in err.write.call_args_list))


P = "os/spruceos/themes/Pixel Consoles/"


def tree(root, files):
    for rel, data in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)


class PlanPublish(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tree(self.tmp.name, {"a.png": b"aaa", "d/b.png": b"bbb", "c.png": b"ccc"})
        self.h = custom_themes.manifest.hash_tree(self.tmp.name)

    def state(self, **over):
        files = {rel: list(v) for rel, v in self.h.items()}
        files.update(over)
        return {"Pixel Consoles": {"files": files}}

    def plan(self, listing, state, downloaded=()):
        return custom_themes.plan_publish("Pixel Consoles", self.tmp.name, listing, state, set(downloaded))

    def test_classifies(self):
        listing = {P + "a.png": 3, P + "d/b.png": 3, P + "old.png": 9}
        state = self.state(**{"a.png": ["0" * 64, 3]})  # same size, different hash
        plan = self.plan(listing, state)
        self.assertEqual((plan.new, plan.changed, plan.same, plan.stale, plan.adopt, plan.skipped),
                         (["c.png"], ["a.png"], ["d/b.png"], [P + "old.png"], False, None))

    def test_listed_size_differs(self):
        plan = self.plan({P + "a.png": 4, P + "d/b.png": 3, P + "c.png": 3}, self.state())
        self.assertEqual((plan.changed, plan.same), (["a.png"], ["c.png", "d/b.png"]))

    def test_adopts_existing_folder(self):
        plan = self.plan({P + "a.png": 3, P + "x.png": 1}, {})
        self.assertTrue(plan.adopt)
        self.assertEqual((plan.changed, plan.new, plan.same, plan.stale), (["a.png"], ["c.png", "d/b.png"], [], [P + "x.png"]))

    def test_new_folder_is_not_adopted(self):
        plan = self.plan({}, {})
        self.assertFalse(plan.adopt)
        self.assertEqual(plan.new, ["a.png", "c.png", "d/b.png"])

    def test_sibling_prefix_never_stale(self):
        plan = self.plan({P + "a.png": 3, "os/spruceos/themes/Pixel Consoles 2/x.png": 1}, self.state())
        self.assertEqual(plan.stale, [])

    def test_downloaded_is_skipped(self):
        plan = self.plan({P + "a.png": 3}, {}, downloaded={"Pixel Consoles"})
        self.assertTrue(plan.skipped)
        self.assertEqual((plan.new, plan.changed, plan.same, plan.stale), ([], [], [], []))


class Manifest(helpers.StorageDir):
    def test_read_missing(self):
        self.assertEqual(custom_themes.manifest.read(), {})

    def test_update_keeps_other_keys(self):
        m = custom_themes.manifest
        m.update(lambda d: d.update({"A": {"files": {"x": ["h", 1]}}, "B": {"files": {}}}))
        self.assertEqual(m.read()["A"]["files"], {"x": ["h", 1]})
        m.update(lambda d: d.__delitem__("A"))
        self.assertEqual(m.read(), {"B": {"files": {}}})
        with open(os.path.join(self.root, runtime.CUSTOM_THEMES_STATE)) as f:
            self.assertTrue(f.read().endswith("}\n"))

    def test_hash_tree_skips_junk(self):
        tmp = os.path.join(self.tmp.name, "t")
        tree(tmp, {"a.png": b"a", ".DS_Store": b"x", "d/._b": b"x", "d/b.png": b"b"})
        self.assertEqual(sorted(custom_themes.manifest.hash_tree(tmp)), ["a.png", "d/b.png"])


if __name__ == "__main__":
    unittest.main()
