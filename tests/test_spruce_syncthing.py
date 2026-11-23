import unittest

import helpers
from sync_roms import commands, spruce_syncthing, store, usersettings


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


if __name__ == "__main__":
    unittest.main()
