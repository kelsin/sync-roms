import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401
import helpers  # noqa: E402,F401
from sync_roms import flash, format_card, picker, store, ui  # noqa: E402

CARD = flash.Disk("disk4", 64_000_000_000, "SD Card Reader", ("SHARE",))
CARDS = {"MIYOOFLIP": {}, "Odin SD": {}, "averyverylongname": {}}
LAYOUTS = {"esde": {}, "spruce": {}}


def patched(cards=CARDS, layouts=LAYOUTS):
    return (mock.patch.object(store, "load_cards", return_value=cards),
            mock.patch.object(store, "repo_json", return_value=layouts))


class Helpers(unittest.TestCase):
    def choices(self, fs, cards=CARDS):
        with patched(cards)[0], patched(cards)[1]:
            return format_card.label_choices(fs)

    def test_label_choices(self):
        self.assertEqual(self.choices("FAT32"), ["MIYOOFLIP", "ODIN SD", "ESDE", "SPRUCE"])
        self.assertEqual(self.choices("exFAT"), ["MIYOOFLIP", "Odin SD", "ESDE", "SPRUCE"])

    def test_duplicates_dropped(self):
        self.assertEqual(self.choices("FAT32", {"spruce": {}}), ["SPRUCE", "ESDE"])

    def test_label_problem(self):
        self.assertIsNotNone(format_card.label_problem("ROMS.1", "FAT32"))
        self.assertIsNone(format_card.label_problem("ROMS.1", "exFAT"))
        self.assertIsNotNone(format_card.label_problem("A" * 12, "FAT32"))
        self.assertIsNone(format_card.label_problem("A" * 15, "exFAT"))
        self.assertIsNotNone(format_card.label_problem("  ", "exFAT"))

    def test_erase_command(self):
        self.assertEqual(format_card.erase_command("disk4", "FAT32", "SPRUCE"),
                         ["diskutil", "eraseDisk", "FAT32", "SPRUCE", "MBR", "disk4"])
        self.assertEqual(format_card.erase_command("disk4", "exFAT", "X")[2], "ExFAT")


class Args:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run


class Run(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.answers = ["disk4"]
        self.picks = [0, 1, None]  # card, filesystem, label (set per test)
        self.erase = subprocess.CompletedProcess([], 0, "", "")

        def run(cmd, **kw):
            self.calls.append(cmd)
            return self.erase if cmd[:2] == ["sudo", "diskutil"] else subprocess.CompletedProcess(cmd, 0, "", "")

        self.external_disks = mock.Mock(return_value=[CARD])
        self.disks_of = mock.Mock(return_value={"disk0"})
        self.filter_list = mock.Mock(side_effect=lambda *a, **k: self.picks.pop(0))
        self.asked = []

        def ask(prompt):
            self.asked.append(prompt)
            return self.answers.pop(0)

        label = ["MIYOOFLIP", "ODIN SD", "ESDE", "SPRUCE"]
        for p in (mock.patch.object(flash, "_run", side_effect=run), mock.patch.object(picker, "filter_list", self.filter_list),
                  mock.patch.object(ui, "ask", ask), mock.patch.object(flash, "external_disks", self.external_disks),
                  mock.patch.object(flash, "disks_of", self.disks_of), mock.patch.object(format_card.sys, "platform", "darwin"),
                  mock.patch.object(format_card, "label_choices", return_value=label)):
            self.enterContext(p)

    def format(self, dry_run=False):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            code = format_card.run(Args(dry_run))
        self.out, self.err = out.getvalue(), err.getvalue()
        return code

    def erased(self):
        return [c for c in self.calls if c[:2] == ["sudo", "diskutil"]]

    def test_happy_path(self):
        self.picks = [0, 1, 3]
        self.assertEqual(self.format(), 0)
        self.assertEqual(self.calls, [["sudo", "-v"],
                                      ["sudo", "diskutil", "eraseDisk", "FAT32", "SPRUCE", "MBR", "disk4"]])
        self.assertIn("✅", self.out)

    def test_typed_label_is_cleaned_and_bad_one_asked_again(self):
        self.picks = [0, 1, 4]
        self.answers = ["bad/name", "roms", "disk4"]
        self.assertEqual(self.format(), 0)
        self.assertIn("ROMS", self.erased()[0])
        self.assertTrue(self.err)

    def test_empty_typed_label_exits(self):
        self.picks = [0, 1, 4]
        self.answers = [""]
        self.assertEqual(self.format(), 0)
        self.assertEqual(self.erased(), [])

    def test_wrong_confirmation(self):
        self.picks = [0, 1, 3]
        for answer in ("Disk4", ""):
            self.picks, self.answers = [0, 1, 3], [answer]
            self.assertEqual(self.format(), 0)
            self.assertEqual(self.erased(), [])
            self.assertIn("Not formatted", self.err)

    def test_dry_run(self):
        self.picks = [0, 1, 3]
        self.assertEqual(self.format(dry_run=True), 0)
        self.assertEqual(self.calls, [])
        self.assertIn("diskutil eraseDisk FAT32 SPRUCE MBR disk4", self.out)

    def test_esc_at_each_picker(self):
        for picks in ([None], [0, None], [0, 1, None]):
            self.picks = list(picks)
            self.assertEqual(self.format(), 0)
            self.assertEqual(self.erased(), [])

    def test_swapped_card(self):
        self.picks = [0, 1, 3]
        self.external_disks.side_effect = [[CARD], [flash.Disk("disk4", 32_000_000_000, "SD Card Reader", ("SHARE",))]]
        self.assertEqual(self.format(), 1)
        self.assertEqual(self.erased(), [])
        self.assertIn("changed since you picked it", self.err)

    def test_erase_failure(self):
        self.picks = [0, 1, 3]
        self.erase = subprocess.CompletedProcess([], 1, "", "boom")
        self.assertEqual(self.format(), 1)
        self.assertIn("boom", self.err)
        self.assertNotIn("✅", self.out)

    def test_unknown_boot_disk(self):
        self.disks_of.return_value = set()
        self.assertEqual(self.format(), 1)
        self.external_disks.assert_not_called()

    def test_not_macos(self):
        with mock.patch.object(format_card.sys, "platform", "linux"):
            self.assertEqual(self.format(), 1)


if __name__ == "__main__":
    unittest.main()
