import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401
from helpers import MANIFEST, SYSTEM  # noqa: E402
from sync_roms import cli, inventory, picker, runtime, spruce_themes, store, ui, usersettings  # noqa: E402

PREFIX = runtime.SPRUCE_THEMES_PREFIX
LAYOUTS = {"spruce": {"label": "Spruce", "roms_dir": "Roms", "bios_dir": "BIOS"},
           "onion": {"label": "Onion", "roms_dir": "Roms", "bios_dir": "BIOS", "themes_dir": "Themes"}}


class SyncThemes(helpers.StorageDir):
    """cli.sync() on card "card" (self.card) against a storage folder holding gba/Game.zip and themes A, B and C."""

    def setUp(self):
        super().setUp()
        inventory.reset()
        self.addCleanup(inventory.reset)
        self.card = os.path.join(self.tmp.name, "card")
        os.makedirs(self.card)
        self.put("gba/Game.zip", b"x" * 5)
        for name in "ABC":
            self.put(f"{PREFIX}{name}/config.json", b'{"name": "%s"}' % name.encode())
            self.put(f"{PREFIX}{name}/icons/a.png", b"png")
        self.settings = {"root": self.root, "spruce_themes": ["A"]}
        self.choose = mock.Mock(return_value="y")
        self.pick = mock.Mock(return_value=None)
        self.save_settings = mock.Mock()

    def system_file(self, theme="X"):
        path = os.path.join(self.card, "Saves", "miyoo-system.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"theme": theme, "vol": 5}, f)
        return path

    def card_theme(self, name, size=3):
        path = os.path.join(self.card, "Themes", name, "big.bin")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"x" * size)

    def on_card(self):
        folder = os.path.join(self.card, "Themes")
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def saved(self):
        return store.load_cards().get("card") or {}

    def sync(self, yes=True, dry_run=False, terminal=True, layout="spruce", free=10**9, extra=()):
        argv = ["sync-roms", self.card] + (["--yes"] if yes else []) + (["--dry-run"] if dry_run else []) + list(extra)
        manifest = {**MANIFEST, "layouts": LAYOUTS, "systems": [{**SYSTEM, "folders": {"spruce": "GBA", "onion": "GBA"}}]}
        with contextlib.ExitStack() as st:
            for target, kw in (
                    (sys, {"argv": argv}),
                    (usersettings, {"ensure_bucket": lambda: None, "load_settings": lambda: dict(self.settings),
                                    "save_settings": self.save_settings}),
                    (store, {"load_manifest": lambda names=(): manifest}),
                    (picker, {"saved_setup": lambda *a: (None, layout)}),
                    (cli, {"free_space": lambda path: free}),
                    (cli.clean, {"eject": lambda: None, "_clean_root": None}),
                    (cli.surprise, {"run_surprise": lambda *a, **k: [], "fill_surprises": lambda *a, **k: []}),
                    (ui, {"has_terminal": lambda: terminal, "choose": self.choose, "_input": mock.Mock(side_effect=EOFError)}),
                    (spruce_themes, {"pick": self.pick})):
                for name, value in kw.items():
                    st.enter_context(mock.patch.object(target, name, value))
            self.out = st.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.err = st.enter_context(contextlib.redirect_stderr(io.StringIO()))
            try:
                code = cli.sync()
            except SystemExit as e:
                code = e.code
            finally:
                ui.ASSUME_YES = False
                self.clean_root = cli.clean._clean_root
        return code

    def test_spruce_sync_copies_default_and_current(self):
        store.update_card("card", spruce_theme="B")
        system = self.system_file()
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        self.assertEqual(self.on_card(), ["A", "B"])
        self.assertTrue(os.path.isfile(os.path.join(self.card, "Themes", "A", "icons", "a.png")))
        self.assertEqual(self.saved().get("spruce_themes_installed"), ["A", "B"])
        with open(system) as f:
            self.assertEqual(json.load(f), {"theme": "B", "vol": 5})

    def test_one_theme_syncs_only_the_current_theme(self):
        store.update_card("card", spruce_theme="B", one_theme=True, spruce_themes_installed=["A"])
        self.card_theme("A")
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        self.assertEqual(self.on_card(), ["B"])
        self.assertEqual(self.saved().get("spruce_themes_installed"), ["B"])

    def test_one_theme_without_a_theme_asks_and_saves(self):
        store.update_card("card", one_theme=True)
        picked = mock.Mock(return_value="C")
        with mock.patch.object(spruce_themes, "pick_one", picked):
            self.assertEqual(self.sync(yes=False), 0, self.err.getvalue())
        picked.assert_called_once_with("🎨 Spruce theme (card)", None)
        self.assertEqual(self.saved().get("spruce_theme"), "C")
        self.assertEqual(self.on_card(), ["C"])

    def test_one_theme_without_a_theme_and_yes_syncs_no_themes(self):
        store.update_card("card", one_theme=True)
        picked = mock.Mock()
        with mock.patch.object(spruce_themes, "pick_one", picked):
            self.assertEqual(self.sync(), 0, self.err.getvalue())
        picked.assert_not_called()
        self.assertEqual(self.on_card(), [])
        self.assertIn("One theme only is on", self.out.getvalue())

    def test_t_override_not_saved(self):
        store.update_card("card", spruce_theme="B")
        self.choose.side_effect = ["t", "y"]
        self.pick.return_value = ["A", "C"]
        self.assertEqual(self.sync(yes=False), 0, self.err.getvalue())
        self.pick.assert_called_once_with("🎨 Themes for this sync only", ["A"], locked="B")
        self.assertEqual(self.choose.call_count, 2)
        self.assertEqual(self.choose.call_args.args[1:], ("ynt", "y", "t: themes for this sync"))
        self.assertEqual(self.on_card(), ["A", "B", "C"])
        self.save_settings.assert_not_called()
        self.assertEqual(self.settings["spruce_themes"], ["A"])

    def test_t_esc_asks_again_unchanged(self):
        self.choose.side_effect = ["t", "y"]
        self.assertEqual(self.sync(yes=False), 0, self.err.getvalue())
        self.assertEqual(self.choose.call_args_list[0], self.choose.call_args_list[1])
        self.assertEqual(self.on_card(), ["A"])

    def test_question_asked_when_nothing_to_download(self):
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        self.choose.return_value = "n"
        self.assertEqual(self.sync(yes=False), 0, self.err.getvalue())
        self.assertEqual(self.choose.call_args.args, ("Nothing to download. Continue?", "ynt", "y", "t: themes for this sync"))
        self.assertIn("Cancelled", self.out.getvalue())

    def test_yes_uses_default_list(self):
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        self.choose.assert_not_called()
        self.pick.assert_not_called()
        self.assertEqual(self.on_card(), ["A"])

    def test_removal_after_answer(self):
        store.update_card("card", spruce_themes_installed=["C"])
        self.card_theme("C")
        self.choose.return_value = "n"
        self.assertEqual(self.sync(yes=False), 0, self.err.getvalue())
        self.assertEqual(self.on_card(), ["C"])
        self.assertIn("Themes to remove: 1", self.out.getvalue())
        self.choose.return_value = "y"
        self.assertEqual(self.sync(yes=False), 0, self.err.getvalue())
        self.assertEqual(self.on_card(), ["A"])
        self.assertEqual(self.saved().get("spruce_themes_installed"), ["A"])

    def test_t_keeps_a_theme_from_removal(self):
        store.update_card("card", spruce_themes_installed=["C"])
        self.card_theme("C")
        self.choose.side_effect = ["t", "y"]
        self.pick.return_value = ["A", "C"]
        self.assertEqual(self.sync(yes=False), 0, self.err.getvalue())
        self.assertEqual(self.on_card(), ["A", "C"])
        self.assertEqual(self.saved().get("spruce_themes_installed"), ["A", "C"])

    def test_failed_removal_stays_recorded(self):
        store.update_card("card", spruce_themes_installed=["C"])
        self.card_theme("C")
        with mock.patch.object(spruce_themes.shutil, "rmtree", side_effect=OSError("busy")):
            self.assertEqual(self.sync(), 1)
        self.assertEqual(self.on_card(), ["A", "C"])
        self.assertEqual(self.saved().get("spruce_themes_installed"), ["A", "C"])

    def test_free_space_counts_removed_themes(self):
        store.update_card("card", spruce_themes_installed=["C"])
        self.card_theme("C", size=10**6)
        self.assertEqual(self.sync(free=1000), 0, self.err.getvalue())
        self.assertEqual(self.on_card(), ["A"])

    def resized(self, name, folder="icons_640x480"):
        path = os.path.join(self.card, "Themes", name, folder, "a.png")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"old")
        return os.path.dirname(path)

    def resized_config(self, name, file="config_640x480.json"):
        path = os.path.join(self.card, "Themes", name, file)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"{}")
        return path

    def test_updated_theme_loses_pyui_resized_copy(self):
        icons, skin = self.resized("A"), self.resized("A", "skin_640x480")
        config, bg = self.resized_config("A"), self.resized("A", "bg_640x480")
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        for path in (icons, skin, config):
            self.assertFalse(os.path.exists(path), path)
        self.assertTrue(os.path.isdir(bg))
        self.assertEqual(self.out.getvalue().count("Cleared the 640x480 copy PyUI made of the Spruce theme A"), 1)

    def test_other_size_copy_is_cleared_alone(self):
        config = self.resized_config("A", "config_720x480.json")
        skin, icons = self.resized("A", "skin_720x480"), self.resized("A", "icons_720x480")
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        for path in (config, skin, icons):
            self.assertFalse(os.path.exists(path), path)
        self.assertIn("Cleared the 720x480 copy PyUI made of the Spruce theme A", self.out.getvalue())

    def test_unchanged_theme_keeps_pyui_resized_copy(self):
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        icons, config = self.resized("A"), self.resized_config("A")
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        self.assertTrue(os.path.isdir(icons))
        self.assertTrue(os.path.isfile(config))

    def test_resized_copies_storage_ships_are_kept(self):
        self.put(f"{PREFIX}A/icons_640x480/a.png", b"new")
        self.put(f"{PREFIX}A/config_720x480.json", b"{}")
        self.put(f"{PREFIX}A/skin_720x480/a.png", b"new")
        inventory.reset()
        icons = self.resized("A")
        config, skin = self.resized_config("A", "config_720x480.json"), self.resized("A", "skin_720x480")
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        for path in (icons, config, skin):
            self.assertTrue(os.path.exists(path), path)

    def test_underscore_skin_and_bg_folders_are_kept(self):
        custom, bg = self.resized("A", "skin_640_480"), self.resized("A", "bg_640x480")
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        self.assertTrue(os.path.isdir(custom))
        self.assertTrue(os.path.isdir(bg))

    def test_dry_run_keeps_pyui_resized_copy(self):
        icons = self.resized("A")
        self.assertEqual(self.sync(dry_run=True), 0, self.err.getvalue())
        self.assertTrue(os.path.isdir(icons))
        self.assertIn("would clear the 640x480 copy PyUI made of the Spruce theme A", self.out.getvalue())

    def test_dry_run_never_asks(self):
        store.update_card("card", spruce_theme="B", spruce_themes_installed=["C"])
        self.card_theme("C")
        system = self.system_file()
        self.assertEqual(self.sync(yes=False, dry_run=True), 0, self.err.getvalue())
        self.choose.assert_not_called()
        self.pick.assert_not_called()
        self.assertEqual(self.on_card(), ["C"])
        out = self.out.getvalue()
        self.assertIn("would remove the Spruce theme C", out)
        self.assertIn(f"{PREFIX}A/config.json", out)
        self.assertIn("would select the Spruce theme B", out)
        with open(system) as f:
            self.assertEqual(json.load(f)["theme"], "X")

    def test_t_themes_read_from_storage_past_the_mirror(self):
        mirror = os.path.join(self.tmp.name, "mirror")
        for key in ("gba/Game.zip", f"{PREFIX}A/config.json", f"{PREFIX}A/icons/a.png"):
            os.makedirs(os.path.dirname(os.path.join(mirror, key)), exist_ok=True)
            with open(os.path.join(self.root, key), "rb") as src, open(os.path.join(mirror, key), "wb") as dst:
                dst.write(src.read())
        self.choose.side_effect = ["t", "y"]
        self.pick.return_value = ["A", "C"]
        with mock.patch.object(runtime, "_mirror_root", mirror):
            self.assertEqual(self.sync(yes=False), 0, self.err.getvalue())
        self.assertTrue(os.path.isfile(os.path.join(self.card, "Themes", "C", "icons", "a.png")), self.out.getvalue() + self.err.getvalue())

    def test_one_theme_picked_at_sync_time_is_read_past_the_mirror(self):
        mirror = os.path.join(self.tmp.name, "mirror")
        for key in ("gba/Game.zip", f"{PREFIX}A/config.json", f"{PREFIX}A/icons/a.png"):
            os.makedirs(os.path.dirname(os.path.join(mirror, key)), exist_ok=True)
            with open(os.path.join(self.root, key), "rb") as src, open(os.path.join(mirror, key), "wb") as dst:
                dst.write(src.read())
        store.update_card("card", one_theme=True)
        with mock.patch.object(runtime, "_mirror_root", mirror), \
                mock.patch.object(spruce_themes, "pick_one", return_value="C"):
            self.assertEqual(self.sync(yes=False), 0, self.err.getvalue())
        self.assertTrue(os.path.isfile(os.path.join(self.card, "Themes", "C", "icons", "a.png")), self.out.getvalue() + self.err.getvalue())

    def test_dry_run_json_lists_theme_removals(self):
        store.update_card("card", spruce_themes_installed=["C"])
        self.card_theme("C")
        with mock.patch.object(ui, "emit_json") as emit:
            self.assertEqual(self.sync(dry_run=True, extra=["--json"]), 0, self.err.getvalue())
        self.assertEqual(emit.call_args.args[0]["theme_remove"], ["C"])

    def test_removal_alone_finalizes_card(self):
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        store.update_card("card", spruce_themes_installed=["A", "C"])
        self.card_theme("C")
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        self.assertEqual(self.on_card(), ["A"])
        self.assertEqual(self.clean_root, self.card)

    def test_selection_alone_finalizes_card(self):
        store.update_card("card", spruce_theme="A")
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        self.system_file()
        self.assertEqual(self.sync(), 0, self.err.getvalue())
        self.assertEqual(self.clean_root, self.card)

    def test_onion_themes_unchanged(self):
        self.put(f"{runtime.THEMES_PREFIX}X/config.json", b"{}")
        self.assertEqual(self.sync(layout="onion"), 0, self.err.getvalue())
        self.assertEqual(self.on_card(), ["X"])
        self.assertNotIn("spruce_themes_installed", self.saved())


class OptionsThemeTodo(helpers.StorageDir):
    """spruce_themes.todo on a theme T whose storage folder has options/manifest.json: the device renders its colours."""

    FILES = {"options/manifest.json": b"{}", "options/templates/skin/bar.png.tpl": b"tpl",
             "options/variants/a/icons/x.png": b"vx", "options/applied.json": b"{}",
             "skin/bar.png": b"bar", "icons/x.png": b"ix", "config.json": b'{"c": 1}', "igm.json": b'{"i": 1}',
             "icons/plain.png": b"plain"}

    def setUp(self):
        super().setUp()
        self.card = os.path.join(self.tmp.name, "card")
        self.rels = dict(self.FILES)
        for rel, data in self.rels.items():
            self.put(f"{PREFIX}T/{rel}", data)
            self.on_card(rel, data)

    def on_card(self, rel, data):
        path = os.path.join(self.card, "Themes", "T", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def jobs(self):
        return [(f"{PREFIX}T/{rel}", os.path.join(self.card, "Themes", "T", rel), len(data))
                for rel, data in self.rels.items()]

    def todo_rels(self):
        return {key[len(PREFIX + "T/"):] for key, _, _ in spruce_themes.todo(self.jobs())}

    def test_generated_set(self):
        self.assertEqual(spruce_themes.generated(set(self.rels)),
                         {"icons/x.png", "skin/bar.png", "config.json", "igm.json", "options/applied.json"})
        self.assertEqual(spruce_themes.generated(set(self.rels) - {"options/manifest.json"}), set())

    def test_options_theme_keeps_generated_files(self):
        self.on_card("skin/bar.png", b"rendered!")
        self.on_card("config.json", b'{"c": 2}')
        self.on_card("options/applied.json", b'{"x": 1}')
        self.on_card("icons/plain.png", b"xx")
        self.assertEqual(self.todo_rels(), {"icons/plain.png"})

    def test_options_change_refreshes_everything(self):
        self.on_card("options/templates/skin/bar.png.tpl", b"older")
        self.on_card("skin/bar.png", b"rendered!")
        self.on_card("config.json", b'{"c": 2}')
        self.on_card("options/applied.json", b'{"x": 1}')
        self.assertEqual(self.todo_rels(), {"options/templates/skin/bar.png.tpl", "skin/bar.png", "config.json",
                                            "options/applied.json"})

    def test_missing_generated_file_is_copied(self):
        os.remove(os.path.join(self.card, "Themes", "T", "skin", "bar.png"))
        self.assertEqual(self.todo_rels(), {"skin/bar.png"})

    def test_selected_json_never_touched(self):
        self.on_card("options/selected.json", b'{"s": 1}')
        self.on_card("options/templates/skin/bar.png.tpl", b"older")
        self.assertNotIn("options/selected.json", self.todo_rels())
        self.assertTrue(os.path.exists(os.path.join(self.card, "Themes", "T", "options", "selected.json")))

    def test_theme_without_manifest_unchanged(self):
        del self.rels["options/manifest.json"]
        self.on_card("config.json", b'{"c": 2}')
        self.on_card("skin/bar.png", b"rendered!")
        self.assertEqual(self.todo_rels(), {"config.json", "skin/bar.png"})


if __name__ == "__main__":
    unittest.main()
