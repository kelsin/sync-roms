"""Adds PyUI's Settings → Game Select Settings → "Reopen last collection" (on by default; off, Collections opens on the
list with the last collection highlighted), from https://github.com/spruceUI/spruceOS/pull/2070, which isn't released
yet. Delete this fix once a spruceOS release with that PR is on every spruce card (the line then reads "the card's
PyUI already has it").

Each of the five files gets small insertions next to anchors that must each appear once, in the 4.6.0 and the
Development code alike, so the card's own version is kept (never a whole file). The fix is all or nothing: when none of
the files has the change yet and every anchor matches, all five are patched; when all of them have it, nothing is
done; anything else (another PyUI version, a file missing, half patched) leaves the card untouched with a warning.
Line ends (CRLF on spruce cards) are kept."""
import os

from .. import cardfs

ID = "reopen_collection"
MISSING = "PyUI isn't on the card"
ROOT = os.path.join("App", "PyUI")

COLLECTION_OVERRIDE = """\
    def _run_rom_selection_for_rom_list(self, page_name, rom_list, refresh_rom_list=None):
        if(self.current_collection is None and not UserConfig.get_reopen_last_collection()):
            last_game_selection, last_subfolder = PyUiState.get_last_game_selection(page_name)
            if(last_game_selection == "Collection" and last_subfolder):
                # Highlight the last collection instead of reopening it
                PyUiState.set_last_game_selection(page_name, last_subfolder, '')
        return super()._run_rom_selection_for_rom_list(page_name, rom_list, refresh_rom_list)

"""
SETTINGS_ENTRY = """\

        option_list.append(
            self.build_enabled_disabled_entry(
                primary_text=Language.reopen_last_collection(),
                get_value_func=UserConfig.get_reopen_last_collection,
                set_value_func=UserConfig.set_reopen_last_collection,
            )
        )
"""
USER_CONFIG_METHODS = """\

    @classmethod
    def get_reopen_last_collection(cls):
        return cls.config.get("reopenLastCollection", True)

    @classmethod
    def set_reopen_last_collection(cls, value):
        cls.config["reopenLastCollection"] = value
        cls.save_config()
"""
LANGUAGE_METHOD = """\

    @classmethod
    def reopen_last_collection(cls):
        return cls._data.get("reopenLastCollection","Reopen last collection")
"""

# (path under App/PyUI, marker of the change, [(anchor, text, before)]: text goes before or after the anchor)
PATCHES = (
    ("lang/English.json", '"reopenLastCollection"', [
        ('    "ignoreArticlesWhenSorting": "Ignore articles when sorting",\n',
         '    "reopenLastCollection": "Reopen last collection",\n', False)]),
    ("main-ui/devices/miyoo/user_config.py", "get_reopen_last_collection", [
        ('        cls.config["ignoreArticlesWhenSorting"] = value\n        cls.save_config()\n',
         USER_CONFIG_METHODS, False)]),
    ("main-ui/menus/language/language.py", "def reopen_last_collection", [
        ('        return cls._data.get("ignoreArticlesWhenSorting","Ignore articles when sorting")\n',
         LANGUAGE_METHOD, False)]),
    ("main-ui/menus/settings/game_select_settings_menu.py", "reopen_last_collection", [
        ("from devices.miyoo.user_config import UserConfig\n", "", False),
        ("from menus.language.language import Language\n", "", False),
        ("\n        return option_list\n", SETTINGS_ENTRY, True)]),
    ("main-ui/menus/games/collections_menu.py", "def _run_rom_selection_for_rom_list", [
        ("from devices.device import Device\n", "from devices.miyoo.user_config import UserConfig\n", False),
        ("from utils.py_ui_state import PyUiState\n", "", False),
        ("    def _menu_pressed(self, selection, rom_list):\n", COLLECTION_OVERRIDE, True)]),
)
# What the patched code calls, which must be there as it is (read only)
REQUIRED = (
    ("main-ui/menus/games/roms_menu_common.py",
     "    def _run_rom_selection_for_rom_list(self, page_name, rom_list, refresh_rom_list=None) :\n"),
    ("main-ui/utils/py_ui_state.py", "    def get_last_game_selection(cls, page_name):\n"),
    ("main-ui/utils/py_ui_state.py", "    def set_last_game_selection(cls, page_name, value, subfolder):\n"),
)


def plan(base):
    root = os.path.join(base, ROOT)
    if not cardfs.is_dir(os.path.join(root, "main-ui")):
        return [], None
    texts = {}
    for rel in {rel for rel, *_ in PATCHES} | {rel for rel, _ in REQUIRED}:
        try:
            texts[rel] = _decode(cardfs.read(os.path.join(root, *rel.split("/"))))
        except OSError:
            return [], _mismatch(f"{rel} is missing")
        except ValueError as e:
            return [], _mismatch(f"{rel} {e}")
    done = [marker in texts[rel][0] for rel, marker, _ in PATCHES]
    if all(done):
        return [], "the card's PyUI already has it"
    if any(done):
        return [], _mismatch("only some of its files have the change")
    for rel, anchor in REQUIRED:
        if texts[rel][0].count(anchor) != 1:
            return [], _mismatch(f"{rel} isn't as expected")
    writes = []
    for rel, _, edits in PATCHES:
        text, newline = texts[rel]
        for anchor, insert, before in edits:
            if text.count(anchor) != 1:
                return [], _mismatch(f"{rel} isn't as expected")
            text = text.replace(anchor, insert + anchor if before else anchor + insert)
        writes.append((os.path.join(root, *rel.split("/")), text.replace("\n", newline).encode("utf-8")))
    return writes, None


def _decode(data):
    """(text with LF line ends, the file's line end); ValueError for mixed line ends or text that isn't UTF-8."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("isn't UTF-8 text") from None
    crlf = text.count("\r\n")
    if crlf and crlf != text.count("\n") or text.count("\r") != crlf:
        raise ValueError("has mixed line ends")
    return text.replace("\r\n", "\n"), "\r\n" if crlf else "\n"


def _mismatch(reason):
    from . import Mismatch
    return Mismatch(f"the card's PyUI isn't a version it knows ({reason}); the card is left as it is")


def keeps(path):
    """Never: this fix patches PyUI's own files, which no theme copy writes."""
    return False
