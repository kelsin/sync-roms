import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import knulli_conf, usersettings  # noqa: E402

RA = "global.retroachievements"
KEY = "a" * 32


class Pure(unittest.TestCase):
    def test_parse_skips_comments_and_keeps_equals(self):
        self.assertEqual(knulli_conf.parse("#a=1\nb = x=y\r\nc=\n"), {"b": "x=y", "c": ""})

    def test_merge_replaces_appends_and_keeps_comments(self):
        old = "#global.retroachievements=0\nfoo=1\nglobal.retroachievements.username=old\n"
        self.assertEqual(knulli_conf.merge(old, {f"{RA}.username": "me", RA: "1"}),
                         "#global.retroachievements=0\nfoo=1\nglobal.retroachievements.username=me\nglobal.retroachievements=1\n")

    def test_merge_updates_every_duplicate(self):
        self.assertEqual(knulli_conf.merge("k=a\nx=1\nk=a\n", {"k": "b"}), "k=b\nx=1\nk=b\n")

    def test_merge_adds_newline_before_append(self):
        self.assertEqual(knulli_conf.merge("foo=1", {"k": "b"}), "foo=1\nk=b\n")


class Install(helpers.CardDir):
    def setUp(self):
        super().setUp()
        self.path = self.cp("system", "knulli.conf")

    def put(self, text, newline="\n"):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)

    def content(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def run_install(self, layout="knulli", dry_run=False, **settings):
        usersettings.save_settings(settings)
        out, self.err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(self.err):
            self.failures = knulli_conf.install("c", layout, self.card, dry_run)
        return out.getvalue()

    def values(self, **settings):
        usersettings.save_settings(settings)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.err = err
            return knulli_conf.ra_values()

    def test_ra_modes(self):
        self.assertEqual(self.values(ra_mode="Disabled"), {RA: "0"})
        for mode in ("Casual", "Softcore"):
            self.assertEqual(self.values(ra_mode=mode), {RA: "1", f"{RA}.hardcore": "0"})
        self.assertEqual(self.values(ra_mode="Hardcore"), {RA: "1", f"{RA}.hardcore": "1"})
        self.assertEqual(self.values(ra_mode="Manual", ra_username="me"), {f"{RA}.username": "me"})

    def test_api_key(self):
        self.assertEqual(self.values(ra_api_key=KEY), {f"{RA}.webapikey": KEY})
        self.assertEqual(self.values(ra_api_key="short"), {})
        self.assertIn("ra_api_key", self.err.getvalue())

    def test_install_writes_and_hides_secrets(self):
        self.put("foo=1\n")
        out = self.run_install(ra_password="a=b#c")
        self.assertIn("global.retroachievements.password=a=b#c", self.content().split("\n"))
        self.assertIn("(hidden)", out)
        self.assertNotIn("a=b#c", out + self.err.getvalue())

    def test_install_twice_writes_nothing_second_time(self):
        self.put("foo=1\n")
        self.run_install(ra_mode="Hardcore", ra_username="me")
        before = os.stat(self.path).st_mtime_ns
        self.assertEqual(self.run_install(ra_mode="Hardcore", ra_username="me"), "")
        self.assertEqual(os.stat(self.path).st_mtime_ns, before)

    def test_crlf_file_is_idempotent(self):
        self.put(f"{RA}=1\r\n{RA}.hardcore=0\r\n", newline="")
        usersettings.save_settings({"ra_mode": "Casual"})
        found = knulli_conf.entries(self.card)
        ra = [e for e in found if e.key.startswith(RA)]
        self.assertEqual(len(ra), 2)
        self.assertFalse(any(e.old != e.new for e in ra))

    def test_missing_file_warns_and_creates_nothing(self):
        self.assertEqual(self.run_install(ra_mode="Hardcore"), "")
        self.assertIn("system/knulli.conf is missing", self.err.getvalue())
        self.assertEqual(self.failures, 0)
        self.assertFalse(os.path.exists(self.cp("system")))

    def test_other_layout_does_nothing(self):
        self.assertEqual(self.run_install(layout="spruce", ra_mode="Hardcore"), "")
        self.assertEqual(self.failures, 0)
        self.assertEqual(self.err.getvalue(), "")
        self.assertFalse(os.path.exists(self.cp("system")))

    def test_dry_run_does_not_write(self):
        self.put("foo=1\n")
        out = self.run_install(dry_run=True, ra_mode="Hardcore")
        self.assertIn("would set", out)
        self.assertEqual(self.content(), "foo=1\n")

    def test_hotkeys_written(self):
        self.put("")
        self.run_install()
        self.assertEqual(self.content(), "\n".join(f"{k}={v}" for k, v in knulli_conf.hotkey_values().items()) + "\n")
        self.assertEqual(self.content().split("\n")[:-1], [
            "global.hotkey_b=x", "global.hotkey_y=pagedown", "global.hotkey_x=pageup", "global.hotkey_down=left",
            "global.hotkey_up=right", "global.hotkey_right=r2", "global.toggle_fast_forward=1"])

    def test_wifi_fills_slots_in_order(self):
        self.put("foo=1\n")
        self.run_install(wifi_networks=[{"ssid": "A", "psk": "password-a"}, {"ssid": "B"}])
        lines = self.content().split("\n")
        for line in ("wifi.ssid=A", "wifi.key=password-a", "wifi2.ssid=B", "wifi2.key="):
            self.assertIn(line, lines)
        self.assertNotIn("wifi3.ssid", self.content())

    def test_wifi_unset_or_empty_writes_nothing(self):
        for settings in ({}, {"wifi_networks": []}):
            usersettings.save_settings(settings)
            self.assertEqual(knulli_conf.wifi_values({"wifi.ssid": "Home"}), {})

    def test_wifi_keeps_device_networks_after_yours(self):
        self.put("wifi.ssid=Home\nwifi.key=hhhhhhhh\n")
        self.run_install(wifi_networks=[{"ssid": "A", "psk": "password-a"}])
        lines = self.content().split("\n")
        for line in ("wifi.ssid=A", "wifi.key=password-a", "wifi2.ssid=Home", "wifi2.key=hhhhhhhh"):
            self.assertIn(line, lines)

    def test_wifi_same_ssid_takes_your_key(self):
        self.put("wifi.ssid=A\nwifi.key=oldoldold\n")
        self.run_install(wifi_networks=[{"ssid": "A", "psk": "new-password"}])
        self.assertEqual(self.content().split("\n")[:2], ["wifi.ssid=A", "wifi.key=new-password"])

    def test_wifi_more_than_three_warns(self):
        self.put("wifi.ssid=Home\nwifi.key=hhhhhhhh\n")
        self.run_install(wifi_networks=[{"ssid": s} for s in "ABCD"])
        lines = self.content().split("\n")
        self.assertIn("wifi3.ssid=C", lines)
        self.assertNotIn("wifi4.ssid=D", lines)
        self.assertNotIn("Home", self.content())
        warning = self.err.getvalue()
        self.assertIn("D", warning)
        self.assertIn("Home", warning)

    def test_wifi_keys_hidden(self):
        self.put("foo=1\n")
        out = self.run_install(wifi_networks=[{"ssid": "A", "psk": "secret-pass"}])
        self.assertIn("(hidden)", out)
        self.assertNotIn("secret-pass", out + self.err.getvalue())


if __name__ == "__main__":
    unittest.main()
