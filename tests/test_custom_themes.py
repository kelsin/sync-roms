import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (imports isolate first)
from PIL import Image  # noqa: E402

from sync_roms import commands, custom_themes, downloads, inventory, runtime, s3, ui, upload, usersettings  # noqa: E402
from sync_roms.custom_themes import palettes  # noqa: E402
from sync_roms.custom_themes.pixel import build as pixel_build  # noqa: E402
from sync_roms.custom_themes.pixel import ids as pixel_ids  # noqa: E402

GRUVBOX = palettes.get("Gruvbox")
PAL = [GRUVBOX]
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

    def test_registry_styles(self):
        self.assertEqual(custom_themes.styles(), ["Pixel Consoles", "Pixel Controllers", "ToTK - James"])
        for style, module in custom_themes.STYLES.items():
            self.assertEqual(module.BASE, "ToTK" if style == "ToTK - James" else "SPRUCE")

    def test_build_overlays_base(self):
        make_base(self.base)
        module = custom_themes.STYLES["Pixel Consoles"]
        dest = module.build(self.base, os.path.join(self.tmp.name, "out"), GRUVBOX)
        self.assertEqual(dest, os.path.join(self.tmp.name, "out", "Pixel Consoles - Gruvbox"))
        with Image.open(os.path.join(dest, "skin", "background.png")) as im:
            self.assertEqual(set(im.convert("RGBA").get_flattened_data()), {(0, 0, 0, 255)})
        with Image.open(os.path.join(dest, "icons", "sel", "gba.png")) as im:
            self.assertIsNotNone(im.convert("RGBA").getbbox())
        with open(os.path.join(dest, "config.json")) as f:
            config = json.load(f)
        self.assertEqual(config["name"], "Pixel Consoles - Gruvbox")
        self.assertEqual(config["screensaver"]["bgColor"], "#000000")
        self.assertEqual(config["extra"], 1)
        with Image.open(os.path.join(dest, "icons_720x540", "gba.png")) as im:
            self.assertEqual(im.size, (134, 146))

    def test_every_spruce_icon_id_is_drawn(self):
        for kind in ("CONSOLES", "CONTROLLERS"):
            self.assertLessEqual(set(pixel_ids.IDS), set(pixel_build.systems(kind)), kind)

    def test_build_is_deterministic(self):
        make_base(self.base)
        module = custom_themes.STYLES["Pixel Controllers"]
        a = module.build(self.base, os.path.join(self.tmp.name, "a"), GRUVBOX)
        b = module.build(self.base, os.path.join(self.tmp.name, "b"), GRUVBOX)
        self.assertEqual(hashes(a), hashes(b))

    def test_files_missing_in_base_are_skipped(self):
        make_base(self.base)
        os.remove(os.path.join(self.base, "skin", "bg-title.png"))
        os.remove(os.path.join(self.base, "skin", "background.png"))
        dest = custom_themes.STYLES["Pixel Consoles"].build(self.base, os.path.join(self.tmp.name, "out"), GRUVBOX)
        self.assertFalse(os.path.exists(os.path.join(dest, "skin", "bg-title.png")))

    def test_icon_folders_missing_in_base_are_created(self):
        os.makedirs(self.base)
        dest = custom_themes.STYLES["Pixel Controllers"].build(self.base, os.path.join(self.tmp.name, "out"), GRUVBOX)
        self.assertTrue(os.path.exists(os.path.join(dest, "icons", "sel", "gba.png")))

    def test_app_icons_missing_in_base_are_drawn(self):
        make_base(self.base, ssh=False)
        dest = custom_themes.STYLES["Pixel Consoles"].build(self.base, os.path.join(self.tmp.name, "out"), GRUVBOX)
        for name in ("SSH", "cheevos", "moonlight", "songo"):
            with Image.open(os.path.join(dest, "icons", "app", f"{name}.png")) as im:
                self.assertEqual(im.size, (70, 70), name)
                self.assertIsNotNone(im.convert("RGBA").getbbox(), name)

    def test_other_icons_missing_in_base_are_skipped(self):
        make_base(self.base)
        dest = custom_themes.STYLES["Pixel Consoles"].build(self.base, os.path.join(self.tmp.name, "out"), GRUVBOX)
        self.assertFalse(os.path.exists(os.path.join(dest, "skin", "ic-cheevos-mark.png")))

    def test_collections_shown_by_default(self):
        make_base(self.base)
        dest = custom_themes.STYLES["Pixel Controllers"].build(self.base, os.path.join(self.tmp.name, "out"), GRUVBOX)
        with open(os.path.join(dest, "config.json")) as f:
            self.assertIs(json.load(f)["collectionsEnabled"], True)


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
            commands.run(["themes", "build", "--palette", "Gruvbox", "--out", os.path.join(self.tmp.name, "out")])
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
                commands.run(["themes", "build", "--palette", "Gruvbox"])
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("gone", "".join(c.args[0] for c in err.write.call_args_list))

    def test_build_command_writes_to_out(self):
        make_base(os.path.join(self.root, "os", "spruceos", "themes", "SPRUCE"))
        out = os.path.join(self.tmp.name, "out")
        self.assertEqual(commands.run(["themes", "build", "Pixel Consoles", "--palette", "Gruvbox", "--out", out]), 0)
        self.assertTrue(os.path.exists(os.path.join(out, "Pixel Consoles - Gruvbox", "config.json")))
        self.assertFalse(os.path.exists(os.path.join(out, "Pixel Controllers - Gruvbox")))

    def test_build_command_unknown_name(self):
        with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr") as err:
            commands.run(["themes", "build", "Nope", "--palette", "Gruvbox"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("Pixel Consoles", "".join(c.args[0] for c in err.write.call_args_list))

    def test_build_command_base_missing(self):
        with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr") as err:
            commands.run(["themes", "build", "--palette", "Gruvbox", "--out", os.path.join(self.tmp.name, "out")])
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("themes update", "".join(c.args[0] for c in err.write.call_args_list))


P = "os/spruceos/themes/Pixel Consoles - Gruvbox/"


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
        return {"Pixel Consoles - Gruvbox": {"files": files}}

    def plan(self, listing, state, downloaded=()):
        return custom_themes.plan_publish("Pixel Consoles - Gruvbox", self.tmp.name, listing, state, set(downloaded))

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
        plan = self.plan({P + "a.png": 3, "os/spruceos/themes/Pixel Consoles - Gruvbox 2/x.png": 1}, self.state())
        self.assertEqual(plan.stale, [])

    def test_downloaded_is_skipped(self):
        plan = self.plan({P + "a.png": 3}, {}, downloaded={"Pixel Consoles - Gruvbox"})
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


C = "os/spruceos/themes/Pixel Controllers - Gruvbox/"


def snapshot(root):
    """{relative path: bytes} of every file under root."""
    out = {}
    for dirpath, _, files in os.walk(root):
        for file in files:
            p = os.path.join(dirpath, file)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = f.read()
    return out


class Publish(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(usersettings, "apply_settings"))
        self.out = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(mock.patch.object(ui, "ASSUME_YES", True))
        make_base(os.path.join(self.root, "os", "spruceos", "themes", "SPRUCE"))
        make_base(os.path.join(self.root, "os", "spruceos", "themes", "ToTK"))

    def manifest(self):
        return self.read_json(runtime.CUSTOM_THEMES_STATE)

    def stored(self, prefix):
        return {k[len(prefix):] for k in snapshot(self.root) if (k.replace(os.sep, "/")).startswith(prefix)}

    def recorder(self):
        calls, real = [], upload.run_uploads

        def run(jobs, quiet=False):
            calls.append(sorted(j[0] for j in jobs))
            return real(jobs, quiet)
        return calls, run

    def test_first_publish_uploads_and_writes_manifest(self):
        self.assertEqual(custom_themes.publish(None, PAL), 0)
        built = os.path.join(self.data, "cache", "themes", "build")
        for name, prefix in (("Pixel Consoles - Gruvbox", P), ("Pixel Controllers - Gruvbox", C)):
            tree_ = custom_themes.manifest.hash_tree(os.path.join(built, name))
            self.assertEqual(self.stored(prefix), set(tree_))
            self.assertEqual(self.manifest()[name]["files"], {rel: list(v) for rel, v in tree_.items()})

    def test_second_publish_uploads_nothing(self):
        custom_themes.publish(None, PAL)
        calls, run = self.recorder()
        with mock.patch.object(upload, "run_uploads", run), mock.patch.object(s3, "delete_keys") as delete:
            self.assertEqual(custom_themes.publish(None, PAL), 0)
        self.assertEqual(calls, [])
        delete.assert_not_called()
        self.assertIn("Nothing to upload", self.out.getvalue())

    def test_changed_file_uploads_only_that_file(self):
        custom_themes.publish(["Pixel Consoles"], PAL)
        calls, run = self.recorder()

        def preview(dest, kind, palette):
            Image.new("RGBA", (640, 480), (1, 2, 3, 255)).save(os.path.join(dest, "preview.png"))
        with mock.patch.object(pixel_build, "preview", preview), mock.patch.object(upload, "run_uploads", run):
            self.assertEqual(custom_themes.publish(["Pixel Consoles"], PAL), 0)
        self.assertEqual(calls, [[P + "preview.png"]])
        digest = custom_themes.manifest.hash_tree(os.path.join(self.data, "cache", "themes", "build", "Pixel Consoles - Gruvbox"))["preview.png"]
        self.assertEqual(self.manifest()["Pixel Consoles - Gruvbox"]["files"]["preview.png"], list(digest))

    def test_stale_files_deleted_and_manifest_updated(self):
        custom_themes.publish(["Pixel Consoles"], PAL)
        self.put(P + "old.png")
        sibling = self.put("os/spruceos/themes/Pixel Consoles - Gruvbox 2/old.png")
        custom_themes.manifest.update(lambda d: d["Pixel Consoles - Gruvbox"]["files"].update({"old.png": ["x" * 64, 3]}))
        self.assertEqual(custom_themes.publish(["Pixel Consoles"], PAL), 0)
        self.assertFalse(os.path.exists(os.path.join(self.root, P, "old.png")))
        self.assertTrue(os.path.exists(sibling))
        self.assertNotIn("old.png", self.manifest()["Pixel Consoles - Gruvbox"]["files"])

    def test_adopts_existing_unmanifested_folder(self):
        self.put(P + "config.json", b"{}")
        self.put(P + "extra/hand-made.png")
        self.assertEqual(custom_themes.publish(["Pixel Consoles"], PAL), 0)
        self.assertIn("dopting", self.out.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.root, P, "extra", "hand-made.png")))
        built = custom_themes.manifest.hash_tree(os.path.join(self.data, "cache", "themes", "build", "Pixel Consoles - Gruvbox"))
        self.assertEqual(self.stored(P), set(built))
        with open(os.path.join(self.root, P, "config.json"), "rb") as f:
            self.assertNotEqual(f.read(), b"{}")
        self.assertEqual(set(self.manifest()["Pixel Consoles - Gruvbox"]["files"]), set(built))

    def test_downloaded_theme_name_is_skipped(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({"x.7z": {"folder": "Pixel Consoles - Gruvbox"}}).encode())
        mine = self.put(P + "config.json", b"theirs")
        self.assertEqual(custom_themes.publish(None, PAL), 1)
        with open(mine, "rb") as f:
            self.assertEqual(f.read(), b"theirs")
        self.assertEqual(self.stored(P), {"config.json"})
        self.assertNotIn("Pixel Consoles - Gruvbox", self.manifest())
        self.assertIn("Pixel Controllers - Gruvbox", self.manifest())

    def test_dry_run_writes_nothing(self):
        custom_themes.publish(["Pixel Consoles"], PAL)
        self.put(P + "old.png")
        before = snapshot(self.root)
        self.assertEqual(custom_themes.publish(None, PAL, dry_run=True), 0)
        self.assertEqual(snapshot(self.root), before)
        self.assertIn("Dry run", self.out.getvalue())

    def test_failed_upload_keeps_old_manifest_entry(self):
        custom_themes.manifest.update(lambda d: d.update({"Pixel Consoles - Gruvbox": {"files": {"preview.png": ["old", 1]}}}))
        failing = P + "preview.png"
        real = upload.run_uploads

        def run(jobs, quiet=False):
            real([j for j in jobs if j[0] != failing])
            return 1
        with mock.patch.object(upload, "run_uploads", run):
            self.assertEqual(custom_themes.publish(["Pixel Consoles"], PAL), 1)
        files = self.manifest()["Pixel Consoles - Gruvbox"]["files"]
        self.assertEqual(files["preview.png"], ["old", 1])
        built = custom_themes.manifest.hash_tree(os.path.join(self.data, "cache", "themes", "build", "Pixel Consoles - Gruvbox"))
        self.assertEqual(files["config.json"], list(built["config.json"]))
        self.assertEqual(set(files), set(built))

    def test_failed_upload_of_changed_same_size_file_keeps_old_entry(self):
        custom_themes.publish(["Pixel Consoles"], PAL)
        old = self.manifest()["Pixel Consoles - Gruvbox"]["files"]["config.json"]
        custom_themes.manifest.update(lambda d: d["Pixel Consoles - Gruvbox"]["files"].update({"config.json": ["0" * 64, old[1]]}))
        with mock.patch.object(upload, "run_uploads", return_value=1):
            self.assertEqual(custom_themes.publish(["Pixel Consoles"], PAL), 1)
        self.assertEqual(self.manifest()["Pixel Consoles - Gruvbox"]["files"]["config.json"], ["0" * 64, old[1]])

    def test_base_missing_changes_nothing(self):
        os.rename(os.path.join(self.root, "os", "spruceos", "themes", "SPRUCE"), os.path.join(self.tmp.name, "moved"))
        shutil.rmtree(os.path.join(self.root, "os", "spruceos", "themes", "ToTK"))
        with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr") as err:
            commands.run(["themes", "publish", "--palette", "Gruvbox", "--yes"])
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("themes update", "".join(c.args[0] for c in err.write.call_args_list))
        self.assertEqual(snapshot(self.root), {})

    def test_unmounted_share(self):
        gone = os.path.join(self.tmp.name, "gone")
        with mock.patch.object(runtime, "ROOT", gone):
            with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr") as err:
                commands.run(["themes", "publish", "--palette", "Gruvbox", "--yes"])
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("gone", "".join(c.args[0] for c in err.write.call_args_list))
        self.assertFalse(os.path.exists(gone))

    def test_malformed_manifest_exits_3(self):
        self.put(runtime.CUSTOM_THEMES_STATE, b"{nope")
        with self.assertRaises(SystemExit) as raised, mock.patch("sys.stderr") as err:
            commands.run(["themes", "publish", "--palette", "Gruvbox", "--yes"])
        self.assertEqual(raised.exception.code, 3)
        self.assertIn("custom-themes.json", "".join(c.args[0] for c in err.write.call_args_list))

    def test_interrupt_leaves_manifest_consistent(self):
        with mock.patch.object(upload, "run_uploads", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                custom_themes.publish(["Pixel Consoles"], PAL)
        self.assertEqual(self.manifest().get("Pixel Consoles - Gruvbox", {}).get("files", {}), {})

    def test_stale_file_gone_behind_the_cache_is_not_deleted(self):
        inventory.update()
        custom_themes.publish(["Pixel Consoles"], PAL)
        old = self.put(P + "old.png")
        inventory.update()
        os.remove(old)
        self.out.seek(0)
        self.out.truncate()
        self.assertEqual(custom_themes.publish(["Pixel Consoles"], PAL), 0)
        out = self.out.getvalue()
        self.assertNotIn("couldn't delete", out)
        self.assertNotIn(P + "old.png", out)
        self.assertIn("Nothing to upload", out)

    def test_malformed_manifest_entries_are_ignored(self):
        spruce = os.path.join(self.root, "os", "spruceos", "themes", "SPRUCE", "config.json")
        with open(spruce, "rb") as f:
            before = f.read()
        self.put(runtime.CUSTOM_THEMES_STATE, json.dumps({
            "Pixel Consoles - Gruvbox": {"files": {"../SPRUCE/config.json": ["0" * 64, 1], "a//b.png": ["0" * 64, 1], "x.png": "bad"}},
            "Pixel Controllers - Gruvbox": {"files": []}, "Other": "nope"}).encode())
        inventory.update()
        self.assertEqual(custom_themes.publish(None, PAL), 0)
        with open(spruce, "rb") as f:
            self.assertEqual(f.read(), before)
        files = self.manifest()["Pixel Consoles - Gruvbox"]["files"]
        self.assertFalse(any(".." in rel or "//" in rel for rel in files))
        self.assertNotIn("x.png", files)

    def test_cancelled_with_skipped_theme_exits_1(self):
        self.put(runtime.SPRUCE_THEMES_STATE, json.dumps({"x.7z": {"folder": "Pixel Consoles - Gruvbox"}}).encode())
        with mock.patch.object(ui, "ASSUME_YES", False), mock.patch.object(ui, "has_terminal", return_value=True), \
                mock.patch.object(ui, "confirm", return_value=False):
            self.assertEqual(custom_themes.publish(None, PAL), 1)
        self.assertEqual(self.stored(C), set())

    def test_command_cancelled_without_yes(self):
        with mock.patch.object(ui, "ASSUME_YES", False), mock.patch.object(ui, "has_terminal", return_value=True), \
                mock.patch.object(ui, "confirm", return_value=False) as ask:
            self.assertEqual(commands.run(["themes", "publish", "--palette", "Gruvbox"]), 0)
        ask.assert_called_once()
        self.assertIs(ask.call_args.kwargs["default"], False)  # Enter uploads nothing
        self.assertEqual(self.stored(P), set())

    def test_enter_uploads_nothing(self):
        with mock.patch.object(ui, "ASSUME_YES", False), mock.patch.object(ui, "has_terminal", return_value=True), \
                mock.patch.object(ui, "_input", lambda prompt: ""):
            self.assertEqual(custom_themes.publish(None, PAL), 0)
        self.assertEqual(self.stored(P), set())

    def test_no_terminal_without_yes_exits_2(self):
        with mock.patch.object(ui, "ASSUME_YES", False), mock.patch.object(ui, "has_terminal", return_value=False), \
                self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()) as err:
            custom_themes.publish(None, PAL)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("Pass --yes to publish without a terminal to confirm on", err.getvalue())
        self.assertEqual(self.stored(P), set())


class PaletteFree(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(usersettings, "apply_settings"))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        for base in ("SPRUCE", "ToTK"):
            make_base(os.path.join(self.root, "os", "spruceos", "themes", base))
        self.out = os.path.join(self.tmp.name, "out")

    def test_needs_palettes(self):
        self.assertFalse(custom_themes.needs_palettes(["ToTK - James"]))
        self.assertTrue(custom_themes.needs_palettes(None))
        self.assertTrue(custom_themes.needs_palettes(["Pixel Consoles"]))

    def test_build_without_palettes(self):
        built = custom_themes.build(["ToTK - James"], [], self.out)
        self.assertEqual(built, {"ToTK - James": os.path.join(self.out, "ToTK - James")})
        with self.assertRaises(ValueError):
            custom_themes.build(["Pixel Consoles"], [], self.out)

    def test_all_styles_build_totk_once(self):
        from sync_roms.custom_themes import totk_james
        with mock.patch.object(totk_james, "build", wraps=totk_james.build) as build:
            built = custom_themes.build(None, [GRUVBOX, palettes.get("Candy")], self.out)
        self.assertEqual(sorted(built), [
            "Pixel Consoles - Candy", "Pixel Consoles - Gruvbox",
            "Pixel Controllers - Candy", "Pixel Controllers - Gruvbox", "ToTK - James"])
        build.assert_called_once()

    def test_palette_flag_ignored_for_totk(self):
        self.assertEqual(commands.run(["themes", "build", "--palette", "Gruvbox", "ToTK - James", "--out", self.out]), 0)
        self.assertEqual(os.listdir(self.out), ["ToTK - James"])

    def test_command_without_saved_palettes_builds(self):
        with mock.patch.object(ui, "ASSUME_YES", True), mock.patch.object(ui, "has_terminal", return_value=False):
            self.assertEqual(commands.run(["themes", "build", "ToTK - James", "--out", self.out]), 0)
        self.assertEqual(os.listdir(self.out), ["ToTK - James"])

    def test_command_with_terminal_skips_picker(self):
        from sync_roms.custom_themes import palette_picker
        with mock.patch.object(ui, "ASSUME_YES", False), mock.patch.object(ui, "has_terminal", return_value=True), \
                mock.patch.object(palette_picker, "pick") as pick:
            self.assertEqual(commands.run(["themes", "build", "ToTK - James", "--out", self.out]), 0)
        pick.assert_not_called()


if __name__ == "__main__":
    unittest.main()
