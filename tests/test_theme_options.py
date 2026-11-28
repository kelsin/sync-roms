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
from sync_roms import cardedit, picker, runtime, store, theme_options, ui  # noqa: E402
from sync_roms.custom_themes import palette_picker, palettes, pixel_options  # noqa: E402

PREFIX = runtime.SPRUCE_THEMES_PREFIX
NORD = {"text": "#ECEFF4", "list": "#D8DEE9", "selected": "#FFFFFF", "accent": "#88C0D0", "dim": "#4C566A",
        "bar": "#434C5E"}


class Base(helpers.StorageDir):
    """Theme Pixel in storage with options/manifest.json, on the card at self.card with its options/ folder."""

    def setUp(self):
        super().setUp()
        self.card = os.path.join(self.tmp.name, "card")
        self.put(f"{PREFIX}Pixel/options/manifest.json", json.dumps(pixel_options.manifest()).encode())
        os.makedirs(os.path.join(self.card, "Themes", "Pixel", "options"))
        self.path = os.path.join(self.card, "Themes", "Pixel", "options", "selected.json")

    def write(self, names=("Pixel",), dry_run=False):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            result = theme_options.write("card", self.card, list(names), dry_run)
        self.out, self.err = out.getvalue(), err.getvalue()
        return result

    def selected(self):
        with open(self.path) as f:
            return json.load(f)

    def saved(self):
        return store.load_cards().get("card") or {}


class ThemeOptions(Base):
    def test_manifest(self):
        self.assertEqual(theme_options.manifest("Pixel"), pixel_options.manifest())
        self.assertIsNone(theme_options.manifest("Other"))

    def test_selected_has_every_role(self):
        self.assertEqual(theme_options.selected(pixel_options.manifest(), "controllers", "Nord"),
                         {"variant": "controllers", "palette": "Nord", "colors": NORD})

    def test_write_selected_json(self):
        store.update_card("card", theme_options={"Pixel": {"variant": "controllers", "palette": "Nord"}})
        self.assertTrue(self.write())
        self.assertEqual(self.selected(), {"variant": "controllers", "palette": "Nord", "colors": NORD})
        self.assertEqual(self.saved()["theme_options_written"], {"Pixel": {"variant": "controllers", "palette": "Nord"}})

    def test_unchanged_setting_never_overwrites_device_choice(self):
        setting = {"Pixel": {"variant": "controllers", "palette": "Nord"}}
        store.update_card("card", theme_options=setting, theme_options_written=setting)
        custom = {"variant": "consoles", "palette": None, "colors": {**NORD, "bar": "#123456"}}
        with open(self.path, "w") as f:
            json.dump(custom, f)
        self.assertFalse(self.write())
        self.assertEqual(self.selected(), custom)

    def test_changed_setting_overwrites(self):
        store.update_card("card", theme_options={"Pixel": {"variant": "controllers", "palette": "Nord"}},
                          theme_options_written={"Pixel": {"variant": "consoles", "palette": "Gruvbox"}})
        with open(self.path, "w") as f:
            json.dump({"variant": "consoles", "palette": None, "colors": {}}, f)
        self.assertTrue(self.write())
        self.assertEqual(self.selected()["palette"], "Nord")
        self.assertEqual(self.saved()["theme_options_written"], {"Pixel": {"variant": "controllers", "palette": "Nord"}})

    def test_dry_run_writes_nothing(self):
        store.update_card("card", theme_options={"Pixel": {"variant": "controllers", "palette": "Nord"}})
        self.assertTrue(self.write(dry_run=True))
        self.assertFalse(os.path.exists(self.path))
        self.assertNotIn("theme_options_written", self.saved())
        self.assertIn("Pixel", self.out)
        self.assertIn("Nord", self.out)

    def test_unknown_palette_warns(self):
        store.update_card("card", theme_options={"Pixel": {"variant": "controllers", "palette": "Nope"}})
        self.assertFalse(self.write())
        self.assertFalse(os.path.exists(self.path))
        self.assertIn("Nope", self.err + self.out)
        self.assertNotIn("theme_options_written", self.saved())

    def test_unknown_variant_warns(self):
        store.update_card("card", theme_options={"Pixel": {"variant": "robots", "palette": "Nord"}})
        self.assertFalse(self.write())
        self.assertFalse(os.path.exists(self.path))
        self.assertIn("robots", self.err + self.out)

    def test_theme_without_manifest_skipped(self):
        os.makedirs(os.path.join(self.card, "Themes", "Other", "options"))
        store.update_card("card", theme_options={"Other": {"variant": "a", "palette": "Nord"}})
        self.assertFalse(self.write(["Other"]))
        self.assertFalse(os.path.exists(os.path.join(self.card, "Themes", "Other", "options", "selected.json")))
        self.assertNotIn("theme_options_written", self.saved())

    def test_theme_not_synced_skipped(self):
        store.update_card("card", theme_options={"Pixel": {"variant": "controllers", "palette": "Nord"}})
        self.assertFalse(self.write([]))
        self.assertFalse(os.path.exists(self.path))

    def test_missing_options_folder_skipped(self):
        os.rmdir(os.path.dirname(self.path))
        store.update_card("card", theme_options={"Pixel": {"variant": "controllers", "palette": "Nord"}})
        self.assertFalse(self.write())
        self.assertFalse(os.path.exists(self.path))
        self.assertNotIn("theme_options_written", self.saved())

    def test_missing_file_written_again(self):
        setting = {"Pixel": {"variant": "controllers", "palette": "Nord"}}
        store.update_card("card", theme_options=setting, theme_options_written=setting)
        self.assertTrue(self.write())
        self.assertEqual(self.selected()["palette"], "Nord")


class PickOne(unittest.TestCase):
    def test_returns_name_or_false(self):
        pals = {n: palettes.get(n) for n in ("Gruvbox", "Nord")}
        with mock.patch.object(picker, "filter_list", return_value=1) as fl:
            self.assertEqual(palette_picker.pick_one("t", ["Gruvbox", "Nord"], pals, "Nord"), "Nord")
        self.assertEqual(fl.call_args.kwargs["cursor"], 1)
        with mock.patch.object(picker, "filter_list", return_value=None):
            self.assertIs(palette_picker.pick_one("t", ["Gruvbox", "Nord"], pals, None), False)


class EditorRow(Base):
    def test_settings_row_picks_variant_then_palette(self):
        store.update_card("card", layout="spruce", spruce_theme="Pixel")
        labels = []

        def fake(title, rows, **kw):
            labels.append(rows)
            if len(labels) == 1:
                return next(i for i, r in enumerate(rows) if r.startswith("🎨 Theme options"))
            if len(labels) == 2:  # the variant list
                return [i for i, r in enumerate(rows) if r == "Controllers"][0]
            return None
        with mock.patch.object(picker, "filter_list", side_effect=fake), \
                mock.patch.object(palette_picker, "pick_one", return_value="Nord") as pick:
            cardedit.settings_menu("card", [], [])
        self.assertIn("🎨 Theme options (Pixel): consoles · Gruvbox", labels[0])
        self.assertEqual(pick.call_args.args[1], palettes.names())
        self.assertEqual(self.saved()["theme_options"], {"Pixel": {"variant": "controllers", "palette": "Nord"}})
        self.assertIn("🎨 Theme options (Pixel): controllers · Nord", labels[2])

    def test_no_row_without_manifest(self):
        store.update_card("card", layout="spruce", spruce_theme="Other")
        rows = []
        with mock.patch.object(picker, "filter_list", side_effect=lambda t, r, **kw: rows.append(r)):
            cardedit.settings_menu("card", [], [])
        self.assertFalse(any(r.startswith("🎨 Theme options") for r in rows[0]))


if __name__ == "__main__":
    unittest.main()
