import contextlib
import io
import json
import os
import stat
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import inventory, onion_surprise, store  # noqa: E402

NAME = "Surprise-v0.1.0.zip"
GOOD = {"App/Surprise/config.json": b"{}", "App/Surprise/surprise": b"bin", "App/Surprise/launch.sh": b"#!/bin/sh",
        "App/Surprise/res/font.ttf": b"font"}


ICON = "Icons/Default/app/surprise.png"
# the member list of a real release zip from onion-surprise's package.sh, directory entries included
RELEASE = {"App/Surprise/": None, "App/Surprise/launch.sh": b"#!/bin/sh", "App/Surprise/res/": None,
           "App/Surprise/res/font-LICENSE.txt": b"ofl", "App/Surprise/res/font.ttf": b"font",
           "App/Surprise/config.json": b"{}", "App/Surprise/surprise": b"bin", "App/Surprise/surprise.png": b"png",
           "Icons/": None, "Icons/Default/": None, "Icons/Default/app/": None, ICON: b"icon"}


def app_zip(members, symlink=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            if data is None:
                z.mkdir(name.rstrip("/"))
                continue
            z.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (0o120777 << 16)
            z.writestr(info, "target")
    return buf.getvalue()


class Install(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.card = os.path.join(self.tmp.name, "card")
        os.makedirs(self.card)
        store.update_card("c", surprise=True)

    def cp(self, *parts):
        return os.path.join(self.card, *parts)

    def run_install(self, layout="onion", dry_run=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.failures = onion_surprise.install("c", layout, self.card, dry_run)
        return out.getvalue()

    def recorded(self):
        return (store.load_cards().get("c") or {}).get("surprise_app")

    def snapshot(self):
        return sorted(os.path.join(d, f) for d, _, fs in os.walk(self.card) for f in fs)

    def test_newest_zip_by_version(self):
        for n in ("v0.2.0", "v0.10.0", "v0.9.1", "eadef4e", "v1.0.0-dirty"):
            self.put(f"os/onion/Surprise-{n}.zip")
        listing = inventory.files("os/onion/", sizes=False)
        self.assertEqual(inventory.newest(listing, "os/onion/", onion_surprise.PATTERN), "os/onion/Surprise-v0.10.0.zip")

    def test_installs_and_records(self):
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        self.run_install()
        self.assertEqual(self.failures, 0)
        self.assertTrue(os.path.isfile(self.cp("App", "Surprise", "res", "font.ttf")))
        for f in ("surprise", "launch.sh"):
            self.assertTrue(os.stat(self.cp("App", "Surprise", f)).st_mode & 0o111)
        self.assertEqual(self.recorded(), NAME)
        self.assertFalse(os.path.exists(self.cp("App", ".Surprise.new")))

    def test_release_zip_installs_app_and_icon(self):
        icons = self.cp("Icons", "Default", "app")
        os.makedirs(icons)
        with open(os.path.join(icons, "other.png"), "wb") as f:
            f.write(b"keep")
        with open(os.path.join(icons, "surprise.png"), "wb") as f:
            f.write(b"old")
        self.put(f"os/onion/{NAME}", app_zip(RELEASE))
        self.run_install()
        self.assertEqual(self.failures, 0)
        self.assertEqual(self.recorded(), NAME)
        with open(self.cp(*ICON.split("/")), "rb") as f:
            self.assertEqual(f.read(), b"icon")
        with open(os.path.join(icons, "other.png"), "rb") as f:
            self.assertEqual(f.read(), b"keep")
        self.assertTrue(os.path.isfile(self.cp("App", "Surprise", "res", "font-LICENSE.txt")))
        self.assertFalse(os.path.exists(self.cp("App", "Surprise", "Icons")))

    def test_icon_creates_its_folders(self):
        self.put(f"os/onion/{NAME}", app_zip({**GOOD, ICON: b"icon"}))
        self.run_install()
        self.assertEqual(self.failures, 0)
        self.assertTrue(os.path.isfile(self.cp(*ICON.split("/"))))

    def test_only_top_level_scripts_are_executable(self):
        self.put(f"os/onion/{NAME}", app_zip({**GOOD, "App/Surprise/res/launch.sh": b"x", "App/Surprise/res/surprise": b"x"}))
        self.run_install()
        for f in ("launch.sh", "surprise"):
            self.assertFalse(os.stat(self.cp("App", "Surprise", "res", f)).st_mode & 0o111)

    def test_corrupt_zip_changes_nothing(self):
        os.makedirs(self.cp("App", "Surprise"))
        open(self.cp("App", "Surprise", "marker"), "w").close()
        store.update_card("c", surprise_app="Surprise-v0.0.1.zip")
        before = self.snapshot()
        self.put(f"os/onion/{NAME}", b"not a zip")
        with contextlib.redirect_stderr(io.StringIO()):
            self.run_install()
        self.assertEqual(self.failures, 1)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(sorted(os.listdir(self.cp("App"))), ["Surprise"])
        self.assertEqual(self.recorded(), "Surprise-v0.0.1.zip")

    def test_recorded_and_present_skips(self):
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        self.run_install()
        marker = self.cp("App", "Surprise", "marker")
        open(marker, "w").close()
        self.run_install()
        self.assertTrue(os.path.exists(marker))

    def test_recorded_but_missing_reinstalls(self):
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        store.update_card("c", surprise_app=NAME)
        self.run_install()
        self.assertTrue(os.path.isfile(self.cp("App", "Surprise", "surprise")))

    def test_newer_replaces_whole_folder(self):
        self.put("os/onion/Surprise-v0.0.9.zip", app_zip(GOOD))
        self.run_install()
        open(self.cp("App", "Surprise", "old.txt"), "w").close()
        os.remove(self.cp("App", "Surprise", "config.json"))
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        self.run_install()
        self.assertFalse(os.path.exists(self.cp("App", "Surprise", "old.txt")))
        self.assertTrue(os.path.isfile(self.cp("App", "Surprise", "config.json")))
        self.assertEqual(self.recorded(), NAME)

    def test_unsafe_zip_changes_nothing(self):
        cases = [({**GOOD, "App/Other/x": b"x"}, None), ({**GOOD, "App/Surprise/../../x": b"x"}, None),
                 ({**GOOD, "/abs/x": b"x"}, None), (GOOD, "App/Surprise/link"),
                 ({"App/Surprise/config.json": b"{}"}, None), ({**GOOD, "Icons/Default/app/other.png": b"x"}, None),
                 ({**GOOD, "Icons/x.png": b"x"}, None), ({**GOOD, "Icons/Default/app/surprise.png/": None}, None),
                 ({**GOOD, ICON: b"icon", "App/Other/x": b"x"}, None), ({**GOOD, ICON: b"icon"}, "App/Surprise/link"),
                 ({**GOOD, "Icons/Other/": None}, None)]
        os.makedirs(self.cp("App", "Surprise"))
        open(self.cp("App", "Surprise", "marker"), "w").close()
        store.update_card("c", surprise_app="Surprise-v0.0.1.zip")
        before = self.snapshot()
        for members, link in cases:
            with self.subTest(members=sorted(members), link=link):
                self.put(f"os/onion/{NAME}", app_zip(members, link))
                with contextlib.redirect_stderr(io.StringIO()):
                    self.run_install()
                self.assertEqual(self.failures, 1)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(sorted(os.listdir(self.cp("App"))), ["Surprise"])
                self.assertEqual(self.recorded(), "Surprise-v0.0.1.zip")

    def test_leftover_new_folder_removed(self):
        os.makedirs(self.cp("App", ".Surprise.new"))
        open(self.cp("App", ".Surprise.new", "junk"), "w").close()
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        self.run_install()
        self.assertFalse(os.path.exists(self.cp("App", ".Surprise.new")))
        self.assertTrue(os.path.isfile(self.cp("App", "Surprise", "surprise")))

    def test_not_onion_or_surprise_off(self):
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        self.run_install("knulli")
        self.assertEqual((self.failures, os.listdir(self.card)), (0, []))
        store.update_card("c", surprise=False)
        self.run_install()
        self.assertEqual((self.failures, os.listdir(self.card)), (0, []))

    def test_collections_off_installs_no_app(self):
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        store.update_card("c", custom_collections=False)
        self.run_install()
        self.assertEqual((self.failures, os.listdir(self.card)), (0, []))

    def test_dry_run(self):
        self.put(f"os/onion/{NAME}", app_zip(GOOD))
        out = self.run_install(dry_run=True)
        self.assertIn(NAME, out)
        self.assertEqual(os.listdir(self.card), [])
        self.assertIsNone(self.recorded())


GBA = {"bucket": "gba", "folders": {"onion": "GBA"}}
PS = {"bucket": "ps", "folders": {"onion": "PS"}}
WS = {"bucket": "ws", "folders": {"onion": "WS"}}
GOLDEN = ('{"label":"Golden Sun","rompath":"/mnt/SDCARD/Emu/GBA/../../Roms/GBA/Golden Sun (USA).gba",'
          '"imgpath":"/mnt/SDCARD/Emu/GBA/../../Roms/GBA/Imgs/Golden Sun (USA).png",'
          '"launch":"/mnt/SDCARD/Emu/GBA/launch.sh","type":5}')


class List(helpers.StorageDir):
    def setUp(self):
        super().setUp()
        self.card = os.path.join(self.tmp.name, "card")
        self.roms = os.path.join(self.card, "Roms")
        os.makedirs(self.roms)
        store.update_card("c", surprise=True)

    def emu(self, name, rompath, launch="launch.sh"):
        d = os.path.join(self.card, "Emu", name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "config.json"), "w") as f:
            json.dump({"rompath": rompath, "launch": launch}, f)

    def rom(self, *rel):
        path = os.path.join(self.roms, *rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()

    def lines(self, surprises, systems=(GBA, PS, WS)):
        folder_of = {s["bucket"]: s["folders"]["onion"] for s in systems}
        return onion_surprise.lines(self.card, self.roms, surprises, folder_of)

    def surprise(self, bucket="gba/Golden Sun (USA).gba", title="Golden Sun"):
        return {"system": bucket.split("/")[0], "bucket": bucket, "title": title}

    def write(self, dry_run=False, layout="onion"):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.changed = onion_surprise.write_list("c", layout, self.card, self.roms, [GBA, PS, WS], dry_run)
        return out.getvalue()

    def test_line_format(self):
        self.emu("GBA", "../../Roms/GBA")
        self.rom("GBA", "Golden Sun (USA).gba")
        self.rom("GBA", "Imgs", "Golden Sun (USA).png")
        self.assertEqual(self.lines([self.surprise()]), [GOLDEN])

    def test_no_image_empty_imgpath_omitted(self):
        self.emu("GBA", "../../Roms/GBA")
        self.rom("GBA", "Golden Sun (USA).gba")
        (line,) = self.lines([self.surprise()])
        self.assertEqual(list(json.loads(line)), ["label", "rompath", "launch", "type"])

    def test_missing_rom_or_emu_skipped(self):
        self.emu("GBA", "../../Roms/GBA")
        self.rom("PS", "Other.cue")
        self.assertEqual(self.lines([self.surprise(), self.surprise("ps/Other.cue", "Other")]), [])

    def test_label_stripped(self):
        self.emu("GBA", "../../Roms/GBA")
        self.rom("GBA", "z.gba")
        (line,) = self.lines([self.surprise("gba/z.gba", 'Zelda: Link\'s "Awakening"\\')])
        self.assertEqual(json.loads(line)["label"], "Zelda Link's Awakening")

    def test_control_characters_stripped(self):
        self.emu("GBA", "../../Roms/GBA")
        self.rom("GBA", "z.gba")
        (line,) = self.lines([self.surprise("gba/z.gba", "A\tB\nC")])
        self.assertEqual(json.loads(line)["label"], "ABC")

    def test_path_with_colon_skipped(self):
        self.emu("GBA", "../../Roms/GBA")
        self.rom("GBA", "Sub: Title.gba")
        self.assertEqual(self.lines([self.surprise("gba/Sub: Title.gba", "Sub")]), [])

    def test_long_line_skipped(self):
        self.emu("GBA", "../../Roms/GBA")
        name = "x" * 240 + ".gba"
        self.rom("GBA", name)
        self.assertEqual(self.lines([self.surprise("gba/" + name, "Long")]), [])

    def test_shared_rom_folder_prefers_same_name(self):
        self.emu("WSC", "../../Roms/WS", "launch_wsc.sh")
        self.emu("WS", "../../Roms/WS")
        self.rom("WS", "g.ws")
        (line,) = self.lines([self.surprise("ws/g.ws", "G")])
        self.assertEqual(json.loads(line)["launch"], "/mnt/SDCARD/Emu/WS/launch.sh")

    def test_shared_rom_folder_else_first_sorted(self):
        self.emu("B", "../../Roms/WS")
        self.emu("A", "../../Roms/WS")
        self.assertEqual(onion_surprise.emu_folders(self.card), {"WS": ("A", "launch.sh")})

    def test_emu_folders_skips_bad_configs(self):
        self.emu("GBA", "../../Roms/GBA")
        self.emu("Deep", "../../Roms/A/B")
        self.emu("Out", "../../../x")
        os.makedirs(os.path.join(self.card, "Emu", "Empty"))
        with open(os.path.join(self.card, "Emu", "Empty", "config.json"), "w") as f:
            f.write("not json")
        self.assertEqual(onion_surprise.emu_folders(self.card), {"GBA": ("GBA", "launch.sh")})

    def test_multi_disc_uses_playlist(self):
        self.emu("PS", "../../Roms/PS")
        self.rom("PS", "Game.m3u")
        (line,) = self.lines([self.surprise("ps/Game.m3u", "Game")])
        self.assertTrue(json.loads(line)["rompath"].endswith("Roms/PS/Game.m3u"))

    def test_write_list_writes_once_and_removes(self):
        self.emu("GBA", "../../Roms/GBA")
        self.rom("GBA", "Golden Sun (USA).gba")
        self.rom("GBA", "Imgs", "Golden Sun (USA).png")
        store.update_card("c", surprises=[self.surprise()])
        path = os.path.join(self.roms, "surprise.json")
        self.write()
        self.assertTrue(self.changed)
        with open(path) as f:
            self.assertEqual(f.read(), GOLDEN + "\n")
        os.utime(path, (1, 1))
        self.write()
        self.assertFalse(self.changed)
        self.assertEqual(os.stat(path).st_mtime, 1)
        store.update_card("c", surprise=False)
        self.write()
        self.assertTrue(self.changed)
        self.assertFalse(os.path.exists(path))

    def test_write_list_skips_malformed_surprises(self):
        self.emu("GBA", "../../Roms/GBA")
        self.rom("GBA", "Golden Sun (USA).gba")
        self.rom("GBA", "Imgs", "Golden Sun (USA).png")
        store.update_card("c", surprises=["x", {"system": "gba", "title": "No bucket"}, {"system": "gba", "bucket": 3},
                                          {"bucket": "gba/Golden Sun (USA).gba"}, self.surprise()])
        self.write()
        with open(os.path.join(self.roms, "surprise.json")) as f:
            self.assertEqual(f.read(), GOLDEN + "\n")

    def test_write_list_non_onion_does_nothing(self):
        self.emu("GBA", "../../Roms/GBA")
        self.rom("GBA", "Golden Sun (USA).gba")
        store.update_card("c", surprises=[self.surprise()])
        self.write(layout="knulli")
        self.assertFalse(self.changed)
        self.assertFalse(os.path.exists(os.path.join(self.roms, "surprise.json")))

    def test_write_list_dry_run(self):
        self.emu("GBA", "../../Roms/GBA")
        self.rom("GBA", "Golden Sun (USA).gba")
        store.update_card("c", surprises=[self.surprise()])
        out = self.write(dry_run=True)
        self.assertIn("surprise.json (1 game(s) on the card)", out)
        self.assertFalse(os.path.exists(os.path.join(self.roms, "surprise.json")))


if __name__ == "__main__":
    unittest.main()
