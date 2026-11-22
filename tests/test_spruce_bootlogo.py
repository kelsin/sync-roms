import contextlib
import io
import os
import shutil
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402
from sync_roms import spruce_bootlogo, store  # noqa: E402

DEVICES = {d["id"]: d for d in store.repo_json("devices")}
DEVICE = DEVICES["miyoo-a30"]  # 640x480


class Install(helpers.CardDir):
    FIELD = "boot_logos"

    def setUp(self):
        super().setUp()
        store.update_card("c", layout="spruce")
        self.imgs = self.cp("App", "BootLogo", "Imgs")
        os.makedirs(self.imgs)

    def logo(self, name, data=b"x", res="640x480"):
        helpers.touch(os.path.join(store.data_dir(), "bootlogos", res, name), data)

    def img(self, name):
        return os.path.join(self.imgs, name)

    def run_install(self, layout="spruce", device=DEVICE, dry_run=False, **kw):
        out, self.err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(self.err):
            self.failures = spruce_bootlogo.install("c", layout, device, self.card, dry_run, **kw)
        return out.getvalue()

    def read(self, name):
        with open(self.img(name), "rb") as f:
            return f.read()

    def test_copies_matching_logos_and_records_them(self):
        self.logo("K.png", b"k")
        self.logo("A.bmp", b"a")
        wrote = []
        out = self.run_install(wrote=wrote)
        self.assertEqual((self.read("K.png"), self.read("A.bmp")), (b"k", b"a"))
        self.assertEqual(self.recorded(), ["A.bmp", "K.png"])
        self.assertEqual(self.failures, 0)
        self.assertEqual(sorted(wrote), [self.img("A.bmp"), self.img("K.png")])
        self.assertIn("Boot Logo", out)

    def test_second_run_copies_nothing(self):
        self.logo("K.png")
        self.run_install()
        wrote = []
        out = self.run_install(wrote=wrote)
        self.assertEqual((out, wrote), ("", []))

    def test_changed_logo_is_copied_again(self):
        self.logo("K.png", b"old")
        self.run_install()
        self.logo("K.png", b"new!")
        self.run_install()
        self.assertEqual(self.read("K.png"), b"new!")

    def test_other_resolution_folder_is_ignored(self):
        self.logo("K.png", res="720x480")
        self.run_install()
        self.assertEqual(os.listdir(self.imgs), [])
        self.assertIsNone(self.recorded())

    def test_ignores_uppercase_extension_other_types_and_confirm_names(self):
        for name in ("K.PNG", "notes.txt", "Yes, flash K.png"):
            self.logo(name)
        self.run_install()
        self.assertEqual(os.listdir(self.imgs), [])

    def test_not_spruce_full_unknown_unsupported_are_silent_noops(self):
        for layout, device in (("onion", DEVICE), ("spruce", None), ("spruce", {"id": "nope"}),
                               ("spruce", DEVICES["magicx-zero40"])):
            with self.subTest(layout=layout, device=(device or {}).get("id")):
                store.update_card("c", boot_logos=["K.png"])
                helpers.touch(self.img("K.png"))
                out = self.run_install(layout, device)
                self.assertEqual((out, self.err.getvalue(), self.failures), ("", "", 0))
                self.assertTrue(os.path.isfile(self.img("K.png")))
                self.assertEqual(self.recorded(), ["K.png"])

    def test_missing_imgs_folder_warns_and_creates_nothing(self):
        self.logo("K.png")
        shutil.rmtree(self.cp("App"))
        self.run_install()
        self.assertEqual(self.failures, 0)
        self.assertIn("App/BootLogo/Imgs", self.err.getvalue())
        self.assertFalse(os.path.exists(self.cp("App", "BootLogo")))
        self.assertIsNone(self.recorded())

    def test_spruces_own_name_is_skipped_case_insensitively(self):
        helpers.touch(self.img("Spruce.png"), b"own")
        self.logo("spruce.png", b"mine")
        self.run_install()
        self.assertEqual(self.read("Spruce.png"), b"own")
        self.assertFalse(self.recorded())
        self.assertIn("spruce.png", self.err.getvalue())
        shutil.rmtree(os.path.join(store.data_dir(), "bootlogos"))
        self.run_install()
        self.assertTrue(os.path.isfile(self.img("Spruce.png")))

    def test_removed_logo_is_cleaned_with_its_confirm_copy(self):
        self.logo("K.png")
        self.run_install()
        helpers.touch(self.img("Yes, flash K.png"))
        helpers.touch(self.img("Other.png"))
        shutil.rmtree(os.path.join(store.data_dir(), "bootlogos"))
        self.run_install()
        self.assertEqual(os.listdir(self.imgs), ["Other.png"])
        self.assertFalse(self.recorded())

    def test_keep_leaves_stale_logos_recorded(self):
        self.logo("K.png")
        self.run_install()
        helpers.touch(self.img("Yes, flash K.png"))
        shutil.rmtree(os.path.join(store.data_dir(), "bootlogos"))
        self.run_install(keep=True)
        self.assertEqual(sorted(os.listdir(self.imgs)), ["K.png", "Yes, flash K.png"])
        self.assertEqual(self.recorded(), ["K.png"])

    def test_copy_failure_counts_and_records_only_what_landed(self):
        self.logo("K.png")
        self.logo("A.bmp")
        real = shutil.copyfile

        def copy(src, dst, *a, **kw):
            if os.path.basename(dst) == "K.png":
                raise OSError("No space left")
            return real(src, dst, *a, **kw)
        with mock.patch("shutil.copyfile", side_effect=copy):
            self.run_install()
        self.assertEqual(self.failures, 1)
        self.assertIn("K.png", self.err.getvalue())
        self.assertEqual(self.recorded(), ["A.bmp"])

    def test_recorded_names_with_path_components_are_never_removed(self):
        victim = os.path.join(self.tmp.name, "victim.txt")
        helpers.touch(victim)
        helpers.touch(self.img("sub/x.png"))
        helpers.touch(os.path.join(self.card, "App", "BootLogo", "x.png"))
        for name in ("../../../../victim.txt", "sub/x.png"):
            with self.subTest(name):
                store.update_card("c", boot_logos=[name])
                self.run_install()
                self.assertTrue(os.path.isfile(victim))
                self.assertTrue(os.path.isfile(self.img("sub/x.png")))
                self.assertFalse(self.recorded())

    def test_failed_copy_leaves_no_partial_file_and_is_retried(self):
        self.logo("K.png", b"kkk")
        def partial(src, dst, *a, **kw):
            with open(dst, "wb") as f:
                f.write(b"k")
            raise OSError("No space left")
        with mock.patch("shutil.copyfile", side_effect=partial):
            self.run_install()
        self.assertEqual(self.failures, 1)
        self.assertEqual(os.listdir(self.imgs), [])
        self.assertFalse(self.recorded())
        self.run_install()
        self.assertEqual((self.failures, self.read("K.png"), self.recorded()), (0, b"kkk", ["K.png"]))

    def test_case_only_rename_replaces_the_old_logo_without_a_clash_warning(self):
        self.logo("K.png", b"old")
        self.run_install()
        shutil.rmtree(os.path.join(store.data_dir(), "bootlogos"))
        self.logo("k.png", b"new")
        self.run_install()
        self.assertEqual(self.err.getvalue(), "")
        self.assertEqual([n.lower() for n in os.listdir(self.imgs)], ["k.png"])
        with open(self.img("k.png"), "rb") as f:
            self.assertEqual(f.read(), b"new")
        self.assertEqual(self.recorded(), ["k.png"])

    def test_dry_run_writes_and_records_nothing(self):
        self.logo("Old.png")
        self.run_install()
        shutil.rmtree(os.path.join(store.data_dir(), "bootlogos"))
        self.logo("New.png")
        out = self.run_install(dry_run=True)
        self.assertIn("Dry run", out)
        self.assertEqual(os.listdir(self.imgs), ["Old.png"])
        self.assertEqual(self.recorded(), ["Old.png"])


if __name__ == "__main__":
    unittest.main()
