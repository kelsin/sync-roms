import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import update_setup_guide  # noqa: E402


class SetupGuideTest(unittest.TestCase):
    def test_device_list_matches_devices_json(self):
        with open(update_setup_guide.GUIDE) as f:
            html = f.read()
        self.assertEqual(update_setup_guide.embedded(html), update_setup_guide.devices_json(),
                         "run tools/update_setup_guide.py")

    def test_device_systems_match_device_systems_json(self):
        with open(update_setup_guide.GUIDE) as f:
            html = f.read()
        self.assertEqual(update_setup_guide.embedded(html, update_setup_guide.SYSTEMS_BLOCK),
                         update_setup_guide.systems_json(), "run tools/update_setup_guide.py")

    def test_guide_knows_nextui_layout_on_linux(self):
        with open(update_setup_guide.GUIDE) as f:
            html = f.read()
        self.assertIn('nextui: "NextUI"', html)
        platform_of = html.split("function platformOf", 1)[1].split("\n}\n", 1)[0]
        self.assertNotIn("nextui", platform_of)  # falls through to the "linux" default
        self.assertTrue(platform_of.rstrip().endswith('return "linux";'))

    def test_every_layout_is_known_and_hotkeys_cover_their_layouts(self):
        import json
        import re
        with open(update_setup_guide.GUIDE) as f:
            html = f.read()

        def keys(name):
            block = html.split(f"const {name} = {{", 1)[1].split("\n};", 1)[0]
            return set(re.findall(r"^  (\w+): ", block, re.M))

        with open(os.path.join(os.path.dirname(update_setup_guide.GUIDE), "layouts.json")) as f:
            layouts = set(json.load(f))
        self.assertLessEqual(layouts, keys("LAYOUTS"))
        hotkey = set(re.findall(r"(\w+): \"", html.split("const HOTKEY = {", 1)[1].split("};", 1)[0]))
        self.assertEqual(hotkey, keys("HOTKEY_LAYOUT"))
        # The Hotkeys section indexes both tables by layout, so it must be limited to layouts they have.
        hotkeys = html.split('id: "hotkeys",', 1)[1].split("items:", 1)[0]
        self.assertIn("when: { layout: Object.keys(HOTKEY_LAYOUT) }", hotkeys)

    def test_cores_section_matches_spruce_syncthing(self):
        import json
        with open(update_setup_guide.GUIDE) as f:
            html = f.read()
        with open(os.path.join(os.path.dirname(update_setup_guide.GUIDE), "syncthing.json")) as f:
            cores = json.load(f)["cores"]
        section = html.split('id: "retroarch-cores",', 1)[1].split('\n  {\n    id: "', 1)[0]
        for core in set(cores.values()):
            self.assertIn(f"<code>{core}</code>", section)
        self.assertIn("jkx7j-mnlfo", html)
        self.assertIn("w5nqg-xmpq6", html)

    def test_guide_command_opens_a_copy_with_your_cards(self):
        import json
        import re
        from unittest import mock
        from sync_roms import commands, store
        store.write_cards({"Main": {"device": "trimui-brick-pro", "layout": "spruce"},
                           "Friend": {"device": "trimui-brick-pro", "layout": "spruce", "guest": True}})
        with mock.patch("webbrowser.open", return_value=True) as opened:
            self.assertEqual(commands.run(["guide"]), 0)
        url = opened.call_args[0][0]
        self.assertTrue(url.startswith("file://") and url.endswith("/cache/setup-guide.html"))
        with open(os.path.join(store.cache_dir(), "setup-guide.html")) as f:
            html = f.read()
        cards = json.loads(re.search(r'id="cards-data">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(cards, [{"name": "Main", "device": "trimui-brick-pro", "layout": "spruce"}])

    def test_packaged_page_holds_no_cards(self):
        with open(update_setup_guide.GUIDE) as f:
            self.assertIn('id="cards-data">[]</script>', f.read())


if __name__ == "__main__":
    unittest.main()
