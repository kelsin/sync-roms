import contextlib
import io
import json
import os
import unittest

import helpers
from sync_roms import commands, spruce_emu, spruce_syncthing, store, usersettings


class Data(unittest.TestCase):
    def test_shape(self):
        d = spruce_syncthing.data()
        self.assertTrue(isinstance(d["note"], str) and d["note"])
        systems = {s["bucket"]: s for s in store.repo_json("systems")}
        folders = {}
        for system, core in d["cores"].items():
            self.assertIn(system, systems)
            self.assertTrue(isinstance(core, str) and core)
            folders.setdefault(systems[system]["folders"].get("spruce"), set()).add(core)
        for folder, cores in folders.items():
            self.assertEqual(len(cores), 1, folder)
        sections = store.repo_json("spruce-settings")["sections"]
        for section, keys in d["spruce"]["settings"].items():
            for key, value in keys.items():
                self.assertIn(key, sections.get(section, []))
                self.assertIsInstance(value, str)
        for core in d["cores"].values():
            self.assertIn(core, d["esde_labels"])
        for value in d["retroarch"].values():
            self.assertIsInstance(value, str)


class Setting(helpers.DataDir):
    ENABLE = ("Network Settings", "enableSyncthing", "True")

    def test_on_by_default(self):
        self.assertTrue(spruce_syncthing.enabled())
        usersettings.save_settings({"spruce_syncthing": False})
        self.assertFalse(spruce_syncthing.enabled())
        usersettings.save_settings({"spruce_syncthing": True})
        self.assertTrue(spruce_syncthing.enabled())

    def test_forced_settings_skip_syncthing_without_wifi(self):
        store.write_cards({"c": {"device": "miyoo-mini", "layout": "spruce"}})
        self.assertNotIn(self.ENABLE, spruce_syncthing.forced_settings("c"))
        store.write_cards({"c": {"device": "anbernic-rg-sp", "layout": "spruce"}})
        self.assertIn(self.ENABLE, spruce_syncthing.forced_settings("c"))
        usersettings.save_settings({"spruce_syncthing": False})
        self.assertEqual(spruce_syncthing.forced_settings("c"), [])

    def test_config_set_takes_it(self):
        self.assertIs(commands.config_value("spruce_syncthing", "false"), False)


class Card(helpers.CardDir):
    FIELD = "spruce_emu"

    def setUp(self):
        super().setUp()
        store.write_cards({"c": {"device": "anbernic-rg-sp", "layout": "spruce"}})

    def put(self, rel, text):
        path = self.cp(*rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return path

    def read(self, rel):
        with open(self.cp(*rel.split("/")), encoding="utf-8", newline="") as f:
            return f.read()

    def run_sync(self, layout="spruce", dry_run=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = spruce_syncthing.run("c", layout, self.card, dry_run)
        self.assertEqual(code, 0)
        return out.getvalue()

    def emu(self, **extra):
        config = {"menuOptions": {"Emulator_64": {"options": ["mednafen_supafaust", "snes9x"], "selected": "mednafen_supafaust"},
                                  "Emulator_32": {"options": ["snes9x2010"], "selected": "snes9x2010"}}, **extra}
        return json.dumps(config, indent=2) + "\n"

    CFG = 'autosave_interval = "0"\nsort_savefiles_enable="true"\nother = "1"\n'

    def test_sets_the_core_in_every_entry_that_offers_it(self):
        self.put("Emu/SFC/config.json", self.emu(ignoreList=["x.zip"]))
        out = self.run_sync()
        text = self.read("Emu/SFC/config.json")
        data = json.loads(text)
        self.assertEqual(data["menuOptions"]["Emulator_64"]["selected"], "snes9x")
        self.assertEqual(data["menuOptions"]["Emulator_32"]["selected"], "snes9x2010")
        self.assertEqual(data["ignoreList"], ["x.zip"])
        self.assertIn('\n  "menuOptions"', text)
        self.assertTrue(text.endswith("\n"))
        self.assertIn("Emu/SFC: snes9x", out)

    def test_entries_lists_unchanged_too(self):
        self.put("Emu/SFC/config.json", self.emu())
        self.put("Saves/ra-configs/retroarch-A.cfg", 'autosave_interval = "10"\nother = "1"\n')
        found = {(e.where, e.key): e for e in spruce_syncthing.entries("c", self.card)}
        core = found[("Emu/SFC/config.json", "core")]
        self.assertEqual((core.old, core.new), ("mednafen_supafaust", "snes9x"))
        same = found[("Saves/ra-configs/retroarch-A.cfg", "autosave_interval")]
        self.assertEqual((same.old, same.new), ("10", "10"))
        added = found[("Saves/ra-configs/retroarch-A.cfg", "savestates_in_content_dir")]
        self.assertEqual((added.old, added.new), (None, "false"))
        self.assertFalse(any(e.secret for e in found.values()))

    def test_entries_empty_when_off(self):
        usersettings.save_settings({"spruce_syncthing": False})
        self.put("Emu/SFC/config.json", self.emu())
        self.assertEqual(spruce_syncthing.entries("c", self.card), [])

    def entries_err(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            found = spruce_syncthing.entries("c", self.card)
        return found, err.getvalue()

    def test_entries_warn_like_run(self):
        self.put("Emu/SFC/config.json", "{nope")
        path = self.cp("Saves", "ra-configs", "retroarch-A.cfg")
        os.makedirs(os.path.dirname(path))
        with open(path, "wb") as f:
            f.write(b"\xff\xfe = bad")
        found, err = self.entries_err()
        self.assertEqual(found, [])
        self.assertIn("Emu/SFC/config.json can't be read; its core left as it is", err)
        self.assertIn("Saves/ra-configs/retroarch-A.cfg can't be read; its save settings left as they are", err)

    def test_entries_warn_without_a_cfg(self):
        self.assertIn("Saves/ra-configs has no retroarch-*.cfg yet", self.entries_err()[1])

    def test_missing_emu_config_is_skipped_quietly(self):
        self.put("Saves/ra-configs/retroarch-A.cfg", self.CFG)
        self.assertNotIn("Emu/", self.run_sync())
        self.assertFalse(os.path.exists(self.cp("Emu")))

    def test_unreadable_emu_config_warns(self):
        self.put("Saves/ra-configs/retroarch-A.cfg", self.CFG)
        self.put("Emu/SFC/config.json", "{nope")
        self.assertIn("Emu/SFC/config.json can't be read; its core left as it is", self.run_sync())
        self.assertEqual(self.read("Emu/SFC/config.json"), "{nope")

    def test_non_utf8_emu_config_warns(self):
        self.put("Saves/ra-configs/retroarch-A.cfg", self.CFG)
        path = self.cp("Emu", "SFC", "config.json")
        os.makedirs(os.path.dirname(path))
        with open(path, "wb") as f:
            f.write(b"\xff\xfe{}")
        self.assertIn("Emu/SFC/config.json can't be read; its core left as it is", self.run_sync())

    def test_retroarch_cfg_keys_replaced_and_appended(self):
        self.put("Saves/ra-configs/retroarch-Anbernic.cfg", self.CFG)
        self.run_sync()
        lines = self.read("Saves/ra-configs/retroarch-Anbernic.cfg").splitlines()
        self.assertEqual(lines.count('autosave_interval = "10"'), 1)
        self.assertNotIn('autosave_interval = "0"', lines)
        self.assertIn('sort_savefiles_enable="true"', lines)
        self.assertEqual(lines.count('savestates_in_content_dir = "false"'), 1)
        self.assertIn('other = "1"', lines)

    def test_crlf_and_no_trailing_newline_kept(self):
        self.put("Saves/ra-configs/retroarch-A.cfg", 'autosave_interval = "0"\r\nother = "1"')
        self.run_sync()
        text = self.read("Saves/ra-configs/retroarch-A.cfg")
        self.assertTrue(text.startswith('autosave_interval = "10"\r\nother = "1"\r\n'))
        self.assertTrue(text.endswith('\r\n'))
        self.assertNotIn("\n", text.replace("\r\n", ""))

    def test_unreadable_cfg_warns(self):
        path = self.cp("Saves", "ra-configs", "retroarch-A.cfg")
        os.makedirs(os.path.dirname(path))
        with open(path, "wb") as f:
            f.write(b"\xff\xfe = bad")
        self.assertIn("Saves/ra-configs/retroarch-A.cfg can't be read; its save settings left as they are", self.run_sync())
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"\xff\xfe = bad")

    def test_no_cfg_warns(self):
        self.assertIn("Saves/ra-configs has no retroarch-*.cfg yet", self.run_sync())

    def test_second_run_writes_and_prints_nothing(self):
        self.put("Emu/SFC/config.json", self.emu())
        self.put("Saves/ra-configs/retroarch-A.cfg", self.CFG)
        self.assertIn("Syncthing", self.run_sync())
        before = {rel: self.read(rel) for rel in ("Emu/SFC/config.json", "Saves/ra-configs/retroarch-A.cfg")}
        self.assertEqual(self.run_sync(), "")
        self.assertEqual(before, {rel: self.read(rel) for rel in before})

    def test_off_leaves_the_card_identical(self):
        usersettings.save_settings({"spruce_syncthing": False})
        self.put("Emu/SFC/config.json", self.emu())
        self.put("Saves/ra-configs/retroarch-A.cfg", self.CFG)
        before = self.snapshot(), self.read("Emu/SFC/config.json"), self.read("Saves/ra-configs/retroarch-A.cfg")
        self.assertEqual(self.run_sync(), "")
        self.assertEqual(before, (self.snapshot(), self.read("Emu/SFC/config.json"), self.read("Saves/ra-configs/retroarch-A.cfg")))

    def test_other_layouts_untouched(self):
        self.put("Saves/ra-configs/retroarch-A.cfg", self.CFG)
        self.assertEqual(self.run_sync("muos"), "")
        self.assertEqual(self.read("Saves/ra-configs/retroarch-A.cfg"), self.CFG)

    def test_dry_run_writes_nothing_and_lists(self):
        self.put("Emu/SFC/config.json", self.emu())
        self.put("Saves/ra-configs/retroarch-A.cfg", self.CFG)
        out = self.run_sync(dry_run=True)
        self.assertIn("would set for Syncthing", out)
        self.assertIn("Emu/SFC: snes9x", out)
        self.assertIn("retroarch-A.cfg: autosave_interval = 10", out)
        self.assertEqual(self.read("Saves/ra-configs/retroarch-A.cfg"), self.CFG)
        self.assertEqual(self.read("Emu/SFC/config.json"), self.emu())

    def test_emu_ignore_list_and_core_both_kept_in_one_sync(self):
        # cli.py runs spruce_emu_step (apply) before stage_spruce (this run) in a real sync
        self.put("Emu/SFC/config.json", self.emu())
        plan = spruce_emu.plan(self.card, {"SFC": ["bios.zip"]}, {})
        spruce_emu.apply(plan)
        self.run_sync()
        data = json.loads(self.read("Emu/SFC/config.json"))
        self.assertEqual(data["ignoreList"], ["bios.zip"])
        self.assertEqual(data["menuOptions"]["Emulator_64"]["selected"], "snes9x")


if __name__ == "__main__":
    unittest.main()
