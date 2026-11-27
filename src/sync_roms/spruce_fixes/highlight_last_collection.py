"""Backing out of a collection or a folder with B highlights it the next time instead of opening it again, and each
folder of a system's game list remembers its own last game (in pyui-state.json, under its system's entry in a "folders"
map keyed by the folder's path), from https://github.com/spruceUI/spruceOS/pull/2070, which isn't released yet. PyUI
still resumes inside a collection or folder after a game. Delete this fix once a spruceOS release with that PR is on
every spruce card (the line then reads "the card's PyUI already has it").

Three files under App/PyUI/main-ui/menus/games/ and utils/py_ui_state.py are edited by replacing blocks that must each
appear once, in the 4.6.0 and the Development code alike, so the card's own version is kept (never a whole file). The
fix is all or nothing: when none of the four has the change yet and every block matches, all four are patched; when all
of them have it, nothing is done; anything else (another PyUI version, a file missing, half patched) leaves the card
untouched with a warning. Line ends (CRLF on spruce cards) are kept.

An earlier sync-roms applied a draft of the same PR that kept each folder's selection under a "<system>::<folder>" key
(KEYED). On cards that have it, it is undone exactly before the change is applied, in the same write.

An even earlier sync-roms patched cards with a "Reopen last collection" setting (another draft of the same PR). Its
insertions in five files (OLD) are taken out again, exactly, in the same write, so those cards end up as if they had
never had it. A draft of that patch put user_config.py's methods before set_ignore_articles_when_sorting instead of after
it, so either placement is taken out."""
import os
import re

from .. import cardfs

ID = "highlight_last_collection"
MISSING = "PyUI isn't on the card"
ROOT = os.path.join("App", "PyUI")
GAMES = "main-ui/menus/games/"

ROMS_MENU = GAMES + "roms_menu_common.py"
RUN_METHOD = "    def _run_rom_selection_for_rom_list(self, page_name, rom_list, refresh_rom_list=None) :\n"
# Every state write in RUN_METHOD's body passes the folder after its last argument
RUN_CALLS = (re.compile(r"(PyUiState\.set_last_game_selection\(\s*page_name,(?:[^()]|\([^()]*\))*?"
                        r"\n( +)[^\n]*[^,\s])(\n *\))"),
             r"\1,\n\2folder=folder\3", 10)
# Only in Development: 4.6.0 has no ROM deletion handler
DELETION_METHOD = "    def _restore_selection_after_rom_deletion(self, page_name, rom_list, selected_index):\n"
DELETION_EDIT = ("""\
            PyUiState.set_last_game_selection(
                page_name,
                next_game.rom_file_path,
                getattr(self, 'subfolder', '') or ''
            )
""", """\
            PyUiState.set_last_game_selection(
                page_name,
                next_game.rom_file_path,
                getattr(self, 'subfolder', '') or '',
                folder=self._selection_folder()
            )
""")

# (path under App/PyUI, marker of the change, [(old, new)])
EDITS = (
    (ROMS_MENU, "def _selection_folder", [
        ("""\
    def _check_for_last_subfolder_existance(self, last_subfolder, rom_list):
        if (
            last_subfolder != '' and
""", """\
    def _check_for_last_subfolder_existance(self, page_name, folder, last_subfolder, rom_list):
        if (
            last_subfolder and
"""),
        ("""\
                return return_value

    def default_to_last_game_selection(self):
        return True
""", """\
                return return_value
            # Backed out of the reopened folder, so highlight it
            PyUiState.set_last_game_selection(page_name, last_subfolder, getattr(self, 'subfolder', '') or '', folder=folder)

    def default_to_last_game_selection(self):
        return True

    def _selection_folder(self):
        return None
"""),
        ("""\
        last_game_file_path, last_subfolder = PyUiState.get_last_game_selection(page_name)

        last_subfolder = self._check_for_last_subfolder_existance(last_subfolder, rom_list)

        if(last_subfolder is not None):
            return last_subfolder
""", """\
        folder = self._selection_folder()
        last_game_file_path, last_subfolder = PyUiState.get_last_game_selection(page_name, folder=folder)

        last_subfolder = self._check_for_last_subfolder_existance(page_name, folder, last_subfolder, rom_list)

        if(last_subfolder is not None):
            return last_subfolder

        # Backing out of a reopened folder or collection updates what to highlight
        last_game_file_path, _ = PyUiState.get_last_game_selection(page_name, folder=folder)
"""),
        ("""\
                        )

                        if(selected.get_selection().get_value().is_collection):
                            PyUiState.set_last_game_selection(
                                page_name,
                                "Collection",
                                selected.get_selection().get_value().rom_file_path
                            )
""" + " " * 24 + """
                    return ControllerInput.B
""", """\
                        )

                    return ControllerInput.B
"""),
    ]),
    (GAMES + "game_select_menu.py", "def _selection_folder", [
        ("""\

    def prefer_savestate_screenshot(self):
""", """\

    def _selection_folder(self):
        # Each folder remembers its own last game under its system's entry
        return self.subfolder or None

    def prefer_savestate_screenshot(self):
"""),
    ]),
    (GAMES + "collections_menu.py", "def _check_for_last_subfolder_existance(self, page_name, folder,", [
        ("    def _check_for_last_subfolder_existance(self, last_subfolder, rom_list):\n",
         "    def _check_for_last_subfolder_existance(self, page_name, folder, last_subfolder, rom_list):\n"),
        ("""\
                    self._load_collection_menu(RomInfo(None, collection, is_collection=True))
                    PyUiState.set_last_game_selection(
                        "Collections",
                        '',
                        getattr(self, 'subfolder', '') or ''
                    )
""", """\
                    self._load_collection_menu(RomInfo(None, collection, is_collection=True))
                    # Backed out of the reopened collection, so highlight it
                    PyUiState.set_last_game_selection(
                        page_name,
                        collection,
                        getattr(self, 'subfolder', '') or '',
                        folder=folder
                    )
"""),
    ]),
    ("main-ui/utils/py_ui_state.py", "def get_last_game_selection(cls, page_name, folder=None)", [
        ("""\
    def get_last_game_selection(cls, page_name):
        return cls._data.get(page_name, {}).get("lastGameSelection", None), cls._data.get(page_name, {}).get("subfolder", None)
""", """\
    def get_last_game_selection(cls, page_name, folder=None):
        entry = cls._data.get(page_name, {})
        if(folder is not None):
            entry = entry.get("folders", {}).get(folder, {})
        return entry.get("lastGameSelection", None), entry.get("subfolder", None)
"""),
        ("""\
    def set_last_game_selection(cls, page_name, value, subfolder):
        if page_name not in cls._data:
            cls._data[page_name] = {}
        cls._data[page_name]["lastGameSelection"] = value
        cls._data[page_name]["subfolder"] = subfolder
""", """\
    def set_last_game_selection(cls, page_name, value, subfolder, folder=None):
        if page_name not in cls._data:
            cls._data[page_name] = {}
        entry = cls._data[page_name]
        if(folder is not None):
            entry = entry.setdefault("folders", {}).setdefault(folder, {})
        entry["lastGameSelection"] = value
        entry["subfolder"] = subfolder
"""),
    ]),
)

# The same PR's earlier draft, which an earlier sync-roms applied: each folder's selection under a
# "<system>::<folder>" key. Taken out, exactly, before EDITS: (path, its marker, [(old, new)] as it applied them), its
# RUN_METHOD state writes (pattern, replacement, count) and its ROM deletion handler edit, each undone
KEYED_CALLS = (re.compile(r"(PyUiState\.set_last_game_selection\(\s*)state_key,"), r"\1page_name,", 10)
KEYED_DELETION_EDIT = ("""\
            PyUiState.set_last_game_selection(
                self._selection_state_key(page_name),
                next_game.rom_file_path,
""", """\
            PyUiState.set_last_game_selection(
                page_name,
                next_game.rom_file_path,
""")
KEYED = (
    (ROMS_MENU, "def _selection_state_key", [
        ("""\
    def _check_for_last_subfolder_existance(self, last_subfolder, rom_list):
        if (
            last_subfolder != '' and
""", """\
    def _check_for_last_subfolder_existance(self, state_key, last_subfolder, rom_list):
        if (
            last_subfolder and
"""),
        ("""\
                return return_value

    def default_to_last_game_selection(self):
        return True
""", """\
                return return_value
            # Backed out of the reopened folder, so highlight it
            PyUiState.set_last_game_selection(state_key, last_subfolder, getattr(self, 'subfolder', '') or '')

    def default_to_last_game_selection(self):
        return True

    def _selection_state_key(self, page_name):
        return page_name
"""),
        ("""\
        last_game_file_path, last_subfolder = PyUiState.get_last_game_selection(page_name)

        last_subfolder = self._check_for_last_subfolder_existance(last_subfolder, rom_list)

        if(last_subfolder is not None):
            return last_subfolder
""", """\
        state_key = self._selection_state_key(page_name)
        last_game_file_path, last_subfolder = PyUiState.get_last_game_selection(state_key)

        last_subfolder = self._check_for_last_subfolder_existance(state_key, last_subfolder, rom_list)

        if(last_subfolder is not None):
            return last_subfolder

        # Backing out of a reopened folder or collection updates what to highlight
        last_game_file_path, _ = PyUiState.get_last_game_selection(state_key)
"""),
        ("""\
                        )

                        if(selected.get_selection().get_value().is_collection):
                            PyUiState.set_last_game_selection(
                                page_name,
                                "Collection",
                                selected.get_selection().get_value().rom_file_path
                            )
""" + " " * 24 + """
                    return ControllerInput.B
""", """\
                        )

                    return ControllerInput.B
"""),
    ]),
    (GAMES + "game_select_menu.py", "def _selection_state_key", [
        ("""\

    def prefer_savestate_screenshot(self):
""", """\

    def _selection_state_key(self, page_name):
        # Each folder remembers its own last game; page_name stays the system name for display
        if(self.subfolder):
            return f"{page_name}::{self.subfolder}"
        return page_name

    def prefer_savestate_screenshot(self):
"""),
    ]),
    (GAMES + "collections_menu.py", "def _check_for_last_subfolder_existance(self, state_key,", [
        ("    def _check_for_last_subfolder_existance(self, last_subfolder, rom_list):\n",
         "    def _check_for_last_subfolder_existance(self, state_key, last_subfolder, rom_list):\n"),
        ("""\
                    self._load_collection_menu(RomInfo(None, collection, is_collection=True))
                    PyUiState.set_last_game_selection(
                        "Collections",
                        '',
""", """\
                    self._load_collection_menu(RomInfo(None, collection, is_collection=True))
                    # Backed out of the reopened collection, so highlight it
                    PyUiState.set_last_game_selection(
                        state_key,
                        collection,
"""),
    ]),
)

REOPEN_METHODS = """\
    @classmethod
    def get_reopen_last_collection(cls):
        return cls.config.get("reopenLastCollection", True)

    @classmethod
    def set_reopen_last_collection(cls, value):
        cls.config["reopenLastCollection"] = value
        cls.save_config()
"""
# The earlier "Reopen last collection" patch: (path, its marker, [(anchor, inserted text, inserted before the anchor)]),
# or for a file it patched in more than one way, (path, its marker, ([...], [...])), the first that matches taken out
OLD = (
    ("lang/English.json", '"reopenLastCollection"', [
        ('    "ignoreArticlesWhenSorting": "Ignore articles when sorting",\n',
         '    "reopenLastCollection": "Reopen last collection",\n', False)]),
    ("main-ui/devices/miyoo/user_config.py", "get_reopen_last_collection", (
        [('        cls.config["ignoreArticlesWhenSorting"] = value\n        cls.save_config()\n',
          "\n" + REOPEN_METHODS, False)],
        [("    @classmethod\n    def set_ignore_articles_when_sorting(cls, value):\n", REOPEN_METHODS + "\n", True)])),
    ("main-ui/menus/language/language.py", "def reopen_last_collection", [
        ('        return cls._data.get("ignoreArticlesWhenSorting","Ignore articles when sorting")\n', """\

    @classmethod
    def reopen_last_collection(cls):
        return cls._data.get("reopenLastCollection","Reopen last collection")
""", False)]),
    ("main-ui/menus/settings/game_select_settings_menu.py", "reopen_last_collection", [
        ("\n        return option_list\n", """\

        option_list.append(
            self.build_enabled_disabled_entry(
                primary_text=Language.reopen_last_collection(),
                get_value_func=UserConfig.get_reopen_last_collection,
                set_value_func=UserConfig.set_reopen_last_collection,
            )
        )
""", True)]),
    (GAMES + "collections_menu.py", "get_reopen_last_collection", [
        ("from devices.device import Device\n", "from devices.miyoo.user_config import UserConfig\n", False),
        ("    def _menu_pressed(self, selection, rom_list):\n", """\
    def _run_rom_selection_for_rom_list(self, page_name, rom_list, refresh_rom_list=None):
        if(self.current_collection is None and not UserConfig.get_reopen_last_collection()):
            last_game_selection, last_subfolder = PyUiState.get_last_game_selection(page_name)
            if(last_game_selection == "Collection" and last_subfolder):
                # Highlight the last collection instead of reopening it
                PyUiState.set_last_game_selection(page_name, last_subfolder, '')
        return super()._run_rom_selection_for_rom_list(page_name, rom_list, refresh_rom_list)

""", True)]),
)


def plan(base):
    root = os.path.join(base, ROOT)
    if not cardfs.is_dir(os.path.join(root, "main-ui")):
        return [], None
    texts = {}
    for rel in {rel for rel, *_ in EDITS} | {rel for rel, *_ in OLD}:
        try:
            texts[rel] = _decode(cardfs.read(os.path.join(root, *rel.split("/"))))
        except OSError:
            return [], _mismatch(f"{rel} is missing")
        except ValueError as e:
            return [], _mismatch(f"{rel} {e}")
    original = {rel: text for rel, (text, _) in texts.items()}
    edited = dict(original)

    old = [marker in edited[rel] for rel, marker, _ in OLD]
    if any(old) and not all(old):
        return [], _mismatch("only some of its files have the earlier Reopen last collection setting")
    if all(old):
        for rel, _, forms in OLD:
            texts_out = (_take_out(edited[rel], form) for form in (forms if isinstance(forms, tuple) else (forms,)))
            text = next((t for t in texts_out if t is not None), None)
            if text is None:
                return [], _mismatch(f"{rel} isn't as the earlier Reopen last collection patch left it")
            edited[rel] = text

    keyed = [marker in edited[rel] for rel, marker, _ in KEYED]
    if any(keyed) and not all(keyed):
        return [], _mismatch("only some of its files have the earlier per-folder key patch")
    if all(keyed):
        for rel, _, edits in KEYED:
            text = _run_calls(edited[rel], KEYED_CALLS, KEYED_DELETION_EDIT) if rel == ROMS_MENU else edited[rel]
            for old_text, new_text in reversed(edits):
                if text is None or text.count(new_text) != 1:
                    return [], _mismatch(f"{rel} isn't as the earlier per-folder key patch left it")
                text = text.replace(new_text, old_text)
            edited[rel] = text

    done = [marker in edited[rel] for rel, marker, _ in EDITS]
    if any(done) and not all(done):
        return [], _mismatch("only some of its files have the change")
    if not all(done):
        for rel, _, edits in EDITS:
            for old_text, new_text in edits:
                if edited[rel].count(old_text) != 1:
                    return [], _mismatch(f"{rel} isn't as expected")
                edited[rel] = edited[rel].replace(old_text, new_text)
        text = _run_calls(edited[ROMS_MENU], RUN_CALLS, DELETION_EDIT)
        if text is None:
            return [], _mismatch(f"{ROMS_MENU} isn't as expected")
        edited[ROMS_MENU] = text

    writes = [(os.path.join(root, *rel.split("/")), edited[rel].replace("\n", texts[rel][1]).encode("utf-8"))
              for rel in sorted(texts) if edited[rel] != original[rel]]
    if not writes:
        return [], "the card's PyUI already has it"
    return writes, None


def _take_out(text, inserts):
    """text without the inserts, None when one isn't there exactly once."""
    for anchor, insert, before in inserts:
        patched = insert + anchor if before else anchor + insert
        if text.count(patched) != 1:
            return None
        text = text.replace(patched, anchor)
    return text


def _run_calls(text, calls, deletion_edit):
    """RUN_METHOD's state writes edited with calls (pattern, replacement, count) and the ROM deletion handler's (where
    there is one) with deletion_edit; None when the code isn't as expected."""
    if text.count(RUN_METHOD) != 1:
        return None
    start = text.index(RUN_METHOD)
    end = text.find("\n    def ", start + len(RUN_METHOD))
    end = len(text) if end < 0 else end
    pattern, replacement, expected = calls
    body, count = pattern.subn(replacement, text[start:end])
    if count != expected or text[start:end].count("PyUiState.set_last_game_selection(") != expected:
        return None
    text = text[:start] + body + text[end:]
    if DELETION_METHOD in text:
        if text.count(deletion_edit[0]) != 1:
            return None
        text = text.replace(*deletion_edit)
    return text


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
