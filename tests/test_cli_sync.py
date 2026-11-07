import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sync_roms import cli, s3, store, usersettings  # noqa: E402

SYSTEM = {"name": "Game Boy Advance", "bucket": "gba", "folders": {"esde": "gba"}, "bios": {"files": []},
          "games": [{"bucket": "gba/Game.zip"}]}
MANIFEST = {"systems": [SYSTEM], "devices": [], "layouts": {"esde": {"label": "ES-DE", "roms_dir": "ROMs", "bios_dir": "BIOS"}}}


def list_sizes(prefix):
    return {"gba/Game.zip": 5} if prefix == "gba/" else {}


class SyncSmokeTest(unittest.TestCase):
    def run_sync(self, dry_run, picks=lambda rows, present, state, editable: [0], edit_card_system=None, prepare=None, patches=()):
        with tempfile.TemporaryDirectory() as card:
            if prepare:
                prepare(card)
            argv = ["sync-roms", card, "--yes"] + (["--dry-run"] if dry_run else [])
            with contextlib.ExitStack() as st:
                for target, kw in (
                        (sys, {"argv": argv}),
                        (usersettings, {"ensure_bucket": lambda: None, "load_settings": lambda: {}}),
                        (store, {"load_manifest": lambda names=(): MANIFEST, "load_cards": lambda: {}, "save_card": lambda *a: None}),
                        (s3, {"list_sizes": list_sizes, "fetch_texts": lambda keys: {}}),
                        (cli.picker, {"saved_setup": lambda *a: (None, "esde"), "pick_systems": picks}),
                        (cli.downloads, {"run_downloads": lambda *a: 0}),
                        (cli.clean, {"clean_android_media": lambda *a: None})) + tuple(patches):
                    for name, value in kw.items():
                        st.enter_context(mock.patch.object(target, name, value))
                st.enter_context(mock.patch.object(cli.clean, "_clean_root", None))
                if edit_card_system:
                    st.enter_context(mock.patch.object(cli.edit, "edit_card_system", edit_card_system))
                st.enter_context(contextlib.redirect_stdout(io.StringIO()))
                return cli.sync()

    def test_dry_run_with_a_scrape_layout(self):
        self.assertEqual(self.run_sync(True), 0)

    def test_real_run_with_a_scrape_layout(self):
        self.assertEqual(self.run_sync(False), 0)

    def test_games_key_edits_the_cards_games_then_reopens_the_picker(self):
        answers, edited, states = iter([("games", 0), [0]]), [], []

        def picks(rows, present, state, editable):
            states.append(state)
            state.setdefault("sel", [False])
            return next(answers)
        self.assertEqual(self.run_sync(False, picks, lambda *a: edited.append(a) or True), 0)
        self.assertEqual([a[1] for a in edited], ["gba"])
        self.assertIs(states[0], states[1])
        self.assertTrue(states[1]["sel"][0])

    def test_dry_run_picker_is_not_editable(self):
        flags = []
        self.run_sync(True, lambda rows, present, state, editable: flags.append(editable) or [0])
        self.assertEqual(flags, [False])

    def old_rom(self, size):
        def prepare(card):
            os.makedirs(os.path.join(card, "ROMs", "gba"))
            with open(os.path.join(card, "ROMs", "gba", "Old.zip"), "wb") as f:
                f.write(b"x" * size)
        return prepare

    def test_space_check_counts_the_unwanted_roms_that_can_be_deleted(self):
        asked = []
        patches = ((cli, {"free_space": lambda path: 3}),
                   (cli.ui, {"confirm": lambda q, default=True: asked.append(q) or True,
                             "choose": lambda *a, **k: "y"}))
        self.assertEqual(self.run_sync(False, prepare=self.old_rom(100), patches=patches), 0)
        self.assertTrue(any("Delete" in q and "first" in q for q in asked), asked)
        self.assertFalse(any("Try anyway" in q for q in asked), asked)

    def test_roms_of_systems_with_nothing_to_sync_are_extras(self):
        """A system with no games listed, selected or not, keeps no ROMs on the card."""
        empty = {"name": "GCE Vectrex", "bucket": "vectrex", "folders": {"esde": "vectrex"}, "bios": {"files": []}, "games": []}
        manifest = {**MANIFEST, "systems": [SYSTEM, empty]}

        def prepare(card):
            for rel in ("gba/Game.zip", "vectrex/Old.zip"):
                os.makedirs(os.path.join(card, "ROMs", os.path.dirname(rel)), exist_ok=True)
                open(os.path.join(card, "ROMs", rel), "w").close()
        for picked in ([0], [0, 1]):
            with self.subTest(picked=picked):
                asked = []
                patches = ((store, {"load_manifest": lambda names=(): manifest}),
                           (cli.ui, {"choose": lambda q, *a, **k: asked.append(q) or "n"}))
                self.run_sync(False, lambda rows, present, state, editable: picked, prepare=prepare, patches=patches)
                self.assertEqual([q for q in asked if q.startswith("Delete these")], ["Delete these 1 local file(s)?"])

    def test_declining_the_space_prompt_exits_0(self):
        patches = ((cli, {"free_space": lambda path: 3}), (cli.ui, {"confirm": lambda q, default=True: False}))
        self.assertEqual(self.run_sync(False, patches=patches), 0)


if __name__ == "__main__":
    unittest.main()
