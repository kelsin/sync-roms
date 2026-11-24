import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import cardfs, spruce_wifi, usersettings  # noqa: E402

HEADER = "ctrl_interface=/var/run/wpa_supplicant\nupdate_config=1\n\n"
VALEFOR = '\nnetwork={\n    ssid="Valefor"\n    psk="cakeordeath"\n}\n'
HOME = '\nnetwork={\n    ssid="Home"\n    psk="device-pw"\n}\n'
SHOWN = "Saves/spruce/wpa_supplicant.conf"


class Install(helpers.CardDir):
    def setUp(self):
        super().setUp()
        self.path = self.cp("Saves", "spruce", "wpa_supplicant.conf")

    def put(self, text):
        helpers.touch(self.path, text)

    def conf(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def run_install(self, networks=None, layout="spruce", dry_run=False):
        usersettings.save_settings({} if networks is None else {"wifi_networks": networks})
        out, self.err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(self.err):
            self.failures = spruce_wifi.install("c", layout, self.card, dry_run)
        self.out = out.getvalue()
        return self.out

    def test_entries_lists_unchanged_too(self):
        self.put(HEADER + VALEFOR + '\nnetwork={\n    ssid="Home"\n    psk="old"\n}\n')
        usersettings.save_settings({"wifi_networks": [{"ssid": "Valefor", "psk": "cakeordeath"}, {"ssid": "Home", "psk": "device-pw"},
                                                      {"ssid": "Cafe", "psk": "newsecret"}]})
        found = spruce_wifi.entries(self.card)
        self.assertEqual([(e.key, e.old, e.new, e.secret) for e in found],
                         [("network Valefor", "present", "present", False), ("network Home", "different", "present", False),
                          ("network Cafe", None, "present", False)])
        self.assertEqual({e.where for e in found}, {SHOWN})
        self.assertNotIn("device-pw", repr(found))

    def test_entries_warn_when_the_file_would_be_replaced(self):
        self.put("garbage")
        usersettings.save_settings({"wifi_networks": [{"ssid": "Valefor", "psk": "cakeordeath"}]})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            found = spruce_wifi.entries(self.card)
        self.assertIn(f"{SHOWN} couldn't be parsed; it would be replaced", err.getvalue())
        self.assertIsNone(found[0].old)

    def test_other_layouts_are_untouched(self):
        self.assertEqual(self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}], layout="onion"), "")
        self.assertEqual(self.snapshot(), [])
        self.assertEqual(self.failures, 0)

    def test_no_setting_writes_nothing(self):
        for networks in (None, []):
            with self.subTest(networks=networks):
                self.assertEqual(self.run_install(networks), "")
                self.assertEqual(self.err.getvalue(), "")
                self.assertFalse(os.path.exists(self.path))

    def test_fresh_card_gets_the_header_and_block(self):
        out = self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}])
        self.assertEqual(self.failures, 0)
        self.assertEqual(self.conf(), HEADER + VALEFOR)
        self.assertEqual(out, f"📶 Adding the Valefor WiFi network → {SHOWN}\n")

    def test_keeps_networks_added_on_the_device(self):
        self.put(HEADER + HOME)
        self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}])
        self.assertEqual(self.conf(), HEADER + HOME + VALEFOR)

    def test_up_to_date_writes_nothing(self):
        self.put(HEADER + "network={\n\tssid=\"Valefor\"\n\tpsk=\"cakeordeath\"\n}\n" + HOME)
        before = os.stat(self.path).st_mtime_ns
        out = self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}])
        self.assertIn("📶 The Valefor WiFi network is already on the card", out)
        self.assertNotIn("Adding", out)
        self.assertNotIn("Updating", out)
        self.assertEqual(self.err.getvalue(), "")
        self.assertEqual(os.stat(self.path).st_mtime_ns, before)

    def test_mix_prints_a_line_per_network(self):
        self.put(HEADER + HOME)
        out = self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}, {"ssid": "Home", "psk": "device-pw"}])
        self.assertIn(f"📶 Adding the Valefor WiFi network → {SHOWN}", out)
        self.assertIn("📶 The Home WiFi network is already on the card", out)
        self.assertEqual(self.conf(), HEADER + HOME + VALEFOR)
        out = self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}, {"ssid": "Cafe"}], dry_run=True)
        self.assertIn("The Valefor WiFi network is already on the card", out)
        self.assertIn("Dry run: would add the Cafe WiFi network", out)

    def test_changed_password_replaces_the_block(self):
        self.put(HEADER + '\nnetwork={\n    ssid="Valefor"\n    psk="old"\n}\n' + HOME)
        out = self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}])
        self.assertEqual(self.conf(), HEADER + HOME + VALEFOR)
        self.assertEqual(out, f"📶 Updating the Valefor WiFi network → {SHOWN}\n")

    def test_open_network(self):
        for network in ({"ssid": "Cafe"}, {"ssid": "Cafe", "psk": ""}):
            with self.subTest(network=network):
                if os.path.exists(self.path):
                    os.remove(self.path)
                self.run_install([network])
                self.assertEqual(self.conf(), HEADER + '\nnetwork={\n    ssid="Cafe"\n    key_mgmt=NONE\n}\n')

    def test_open_network_up_to_date_and_turned_secured(self):
        self.put(HEADER + '\nnetwork={\n    ssid="Cafe"\n    key_mgmt=NONE\n}\n')
        self.assertIn("The Cafe WiFi network is already on the card", self.run_install([{"ssid": "Cafe"}]))
        out = self.run_install([{"ssid": "Cafe", "psk": "password1"}])
        self.assertIn("Updating the Cafe WiFi network", out)
        self.assertEqual(self.conf(), HEADER + '\nnetwork={\n    ssid="Cafe"\n    psk="password1"\n}\n')

    def test_raw_hex_psk_is_written_unquoted(self):
        raw = "0123456789abcdef" * 4
        self.run_install([{"ssid": "Cafe", "psk": raw}])
        self.assertEqual(self.conf(), HEADER + f'\nnetwork={{\n    ssid="Cafe"\n    psk={raw}\n}}\n')
        self.assertIn("already on the card", self.run_install([{"ssid": "Cafe", "psk": raw}]))

    def test_invalid_psk_length_skips_the_network_and_keeps_its_block(self):
        self.put(HEADER + VALEFOR)
        for psk in ("short", "x" * 64, "x" * 65):
            with self.subTest(psk=psk):
                self.run_install([{"ssid": "Valefor", "psk": psk}, {"ssid": "Home", "psk": "device-pw"}])
                self.assertEqual(self.conf(), HEADER + VALEFOR + HOME)
                self.assertIn("Valefor", self.err.getvalue())
                self.assertNotIn(psk, self.err.getvalue() + self.out)
                self.assertEqual(self.failures, 0)
                self.put(HEADER + VALEFOR)

    def test_two_networks(self):
        out = self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}, {"ssid": "Home", "psk": "device-pw"}])
        self.assertEqual(self.conf(), HEADER + VALEFOR + HOME)
        self.assertIn("Adding the Valefor", out)
        self.assertIn("Adding the Home", out)

    def test_broken_file_is_kept_aside_and_replaced(self):
        for raw in ("   \n", "network={\n ssid=\"x\"\n}\n", HEADER + "network={\n ssid=\"x\"\n"):
            with self.subTest(raw=raw):
                self.put(raw)
                self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}])
                self.assertEqual(self.conf(), HEADER + VALEFOR)
                with open(self.path + ".broken", encoding="utf-8") as f:
                    self.assertEqual(f.read(), raw)
                self.assertIn("couldn't be parsed", self.err.getvalue())

    def test_dry_run_writes_nothing(self):
        out = self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}], dry_run=True)
        self.assertIn(f"Dry run: would add the Valefor WiFi network to {SHOWN}", out)
        self.assertFalse(os.path.exists(self.path))
        self.put(HEADER + '\nnetwork={\n    ssid="Valefor"\n    psk="old"\n}\n')
        out = self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}], dry_run=True)
        self.assertIn("would update the Valefor WiFi network", out)
        self.put("garbage")
        self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}], dry_run=True)
        self.assertEqual(self.conf(), "garbage")
        self.assertFalse(os.path.exists(self.path + ".broken"))

    def test_password_is_never_shown(self):
        self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}])
        self.assertNotIn("cakeordeath", self.out + self.err.getvalue())
        self.run_install([{"ssid": "Valefor", "psk": "newsecret"}], dry_run=True)
        self.assertNotIn("newsecret", self.out + self.err.getvalue())

    def test_malformed_entries_are_warned_about_and_skipped(self):
        self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}, "x", {"ssid": ""}, {"psk": "p"}, {"ssid": "A", "psk": 3}])
        self.assertEqual(self.failures, 0)
        self.assertEqual(self.conf(), HEADER + VALEFOR)
        self.assertEqual(self.err.getvalue().count("wifi_networks"), 1)
        self.run_install({"ssid": "Valefor"})
        self.assertIn("wifi_networks", self.err.getvalue())
        self.assertEqual(self.failures, 0)

    def test_write_error_is_a_failure(self):
        with mock.patch.object(cardfs, "write_text", side_effect=OSError("read-only")):
            self.run_install([{"ssid": "Valefor", "psk": "cakeordeath"}])
        self.assertEqual(self.failures, 1)
        self.assertIn("read-only", self.err.getvalue())


if __name__ == "__main__":
    unittest.main()
