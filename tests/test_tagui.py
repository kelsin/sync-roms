import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import edit, picker, store, tags, tagui, ui  # noqa: E402

A, B = "nes/A (USA).zip", "nes/B (USA).zip"


class Base(unittest.TestCase):
    def setUp(self):
        data_dir = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(store, "data_dir", return_value=data_dir))
        helpers.storage_tags(self, {
            "tags": {"shmups": {"name": "Shmups", "emoji": "🚀"}, "cave": {"name": "Cave", "emoji": "🐝"}},
            "games": {B: {"tags": ["shmups"]}}, "declined": {}})
        self.notes = []
        self.enterContext(mock.patch.object(edit, "note", self.notes.append))
        tagui.RECENT.clear()
        self.addCleanup(tagui.RECENT.clear)
        tagui.LAST[:] = []
        self.addCleanup(tagui.LAST.clear)

    def pick_tags(self, key, on, title="B", after=None):
        """edit_game_tags(key) answered with the tag ids in on; returns (labels, kw) of the picker."""
        seen = []

        def fake(t, labels, **kw):
            seen.append((labels, kw))
            return after(labels) if after else [i in on for i in self._ids(labels)]
        with mock.patch.object(picker, "filter_list", fake):
            self.result = tagui.edit_game_tags(key, title)
        return seen[0]

    def _ids(self, labels):
        defs = tags.all_tags()
        return [next(i for i, t in defs.items() if label.startswith(f"{t['emoji']} {t['name']}")) for label in labels]

    def bulk(self, keys, checked, confirm=True):
        """bulk_tag(keys) with the checklist answered by checked (tag ids on); returns the checklist's (labels, initial)."""
        seen = []

        def fake(title, labels, **kw):
            seen.append((labels, kw["initial"], title))
            return [i in checked for i in self._ids(labels)]
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "confirm", return_value=confirm) as c:
            self.result = tagui.bulk_tag(keys)
        self.asked = [a[0][0] for a in c.call_args_list]
        return seen[0] if seen else None



class TagUi(Base):
    def test_bulk_tag_adds_the_checked_tags_to_every_game_after_a_count_confirm(self):
        seen = self.bulk([A, B], {"cave", "shmups"})
        self.assertEqual(seen[0], ["🐝 Cave", "🚀 Shmups"])
        self.assertEqual(seen[1], [False, False])  # B has shmups, A doesn't: not on all of them
        self.assertEqual(self.asked, ["🏷️  Tag 2 games?"])
        self.assertEqual((tags.tags_of(A), tags.tags_of(B)), (["cave", "shmups"], ["cave", "shmups"]))
        self.assertEqual(self.notes[-1], "🏷️  Tagged 2 games")

    def test_bulk_tag_checks_the_tags_all_games_have_and_unchecking_removes_only_those(self):
        tags.change_game_tags(A, add=["shmups", "cave"])
        seen = self.bulk([A, B], {"cave"})
        self.assertEqual(seen[1], [True, False])  # Shmups is on both, so it is listed first
        self.assertEqual((tags.tags_of(A), tags.tags_of(B)), (["cave"], ["cave"]))

    def test_bulk_tag_declined_or_unchanged_writes_nothing(self):
        self.bulk([A, B], {"cave"}, confirm=False)
        self.assertFalse(self.result)
        self.assertEqual((tags.tags_of(A), tags.tags_of(B)), ([], ["shmups"]))
        self.bulk([A], set())
        self.assertEqual(self.asked, [])
        self.assertIn("No tag changed", self.notes[-1])

    def test_bulk_tag_counts_a_record_and_its_files_once(self):
        tags.change_game_tags(A, add=["cave"])
        with mock.patch.object(tags, "owner", lambda k: A if k == "nes/A.sav" else k):
            self.bulk([A, "nes/A.sav"], {"cave", "shmups"})
        self.assertEqual(self.asked, ["🏷️  Tag 1 game?"])

    def test_unchecking_a_tag_on_only_some_shown_games_leaves_it_untouched(self):
        self.bulk([A, B], {"cave"})  # shmups is on B only: not checked at the start, and still unchecked
        self.assertEqual((tags.tags_of(A), tags.tags_of(B)), (["cave"], ["cave", "shmups"]))

    def test_esc_on_the_bulk_checklist_writes_nothing(self):
        before = tags.load()
        with mock.patch.object(picker, "filter_list", return_value=None), \
                mock.patch.object(ui, "confirm") as confirm:
            self.assertFalse(tagui.bulk_tag([A, B]))
        confirm.assert_not_called()
        self.assertIs(tags.load(), before)
        self.assertEqual((tags.tags_of(A), tags.tags_of(B)), ([], ["shmups"]))

    def test_n_in_the_bulk_checklist_creates_a_tag_checked_for_every_game(self):
        calls = []

        def fake(title, labels, **kw):
            calls.append(labels)
            return ("n", None) if len(calls) == 1 else kw["session"]["sel"]
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", side_effect=["Pixel Art", "🎨"]), \
                mock.patch.object(ui, "confirm", return_value=True):
            self.assertTrue(tagui.bulk_tag([A, B]))
        self.assertIn("🎨 Pixel Art", calls[1])
        self.assertEqual(tags.all_tags()["pixel-art"], {"name": "Pixel Art", "emoji": "🎨"})
        self.assertEqual((tags.tags_of(A), tags.tags_of(B)), (["pixel-art"], ["pixel-art", "shmups"]))

    def test_games_pluralises(self):
        self.assertEqual([tagui.games(n) for n in (1, 2)], ["1 game", "2 games"])

    def test_column_rows(self):
        self.assertEqual(tagui.column([A, B]), [("", ""), ("🚀", "")])
        tags.change_game_tags(A, add=["cave", "shmups"])
        self.assertEqual(tagui.column([A, B]), [("🐝🚀", ""), ("🚀", "")])
        with mock.patch.object(tags, "emoji_of", return_value="12345678"):
            self.assertEqual(tagui.column([A]), [("12345678", "")])

    def test_summary_rows(self):
        tags.define_tag("cave", {"name": "Cave", "emoji": "🐝", "description": "Cave shooters"})
        tags.change_game_tags(A, add=["cave", "shmups"])
        summary = tagui.summary([A, B, "nes/None.zip"])
        self.assertEqual(summary(0), [("🐝", "Cave", "Cave shooters"), ("🚀", "Shmups", "")])
        self.assertEqual(summary(1), [("🚀", "Shmups", "")])
        self.assertEqual(summary(2), [])

    def test_unknown_key_row(self):
        tags.change_game_tags("nes/Gone.zip", add=["cave"])
        self.assertEqual(tagui.column(["nes/Gone.zip"]), [("🐝", "")])

    def test_edit_game_tags_saves(self):
        seen = []

        def fake(title, labels, **kw):
            seen.append((labels, kw["initial"]))
            return [True, True]
        with mock.patch.object(picker, "filter_list", fake):
            self.assertTrue(tagui.edit_game_tags(B, "B"))
        self.assertEqual(seen, [(["🚀 Shmups (1 games)", "🐝 Cave (0 games)"], [True, False])])
        self.assertEqual(tags.tags_of(B), ["cave", "shmups"])

    def test_unchanged_returns_false(self):
        with mock.patch.object(picker, "filter_list", lambda t, labels, **kw: kw["initial"]):
            self.assertFalse(tagui.edit_game_tags(B, "B"))
        with mock.patch.object(picker, "filter_list", return_value=None):
            self.assertFalse(tagui.edit_game_tags(B, "B"))

    def test_edit_game_tags_new_tag(self):
        calls = []

        def fake(title, labels, **kw):
            calls.append(labels)
            return ("n", None) if len(calls) == 1 else kw["session"]["sel"]
        with mock.patch.object(picker, "filter_list", fake), \
                mock.patch.object(ui, "ask", side_effect=["Pixel Art", "🎨"]):
            self.assertTrue(tagui.edit_game_tags(A, "A"))
        self.assertEqual(tags.all_tags()["pixel-art"], {"name": "Pixel Art", "emoji": "🎨"})
        self.assertEqual(tags.tags_of(A), ["pixel-art"])
        self.assertIn("🎨 Pixel Art (0 games)", calls[1])

    def test_new_tag_refused(self):
        for answers in (["", "🎨"], ["Pixel", ""], ["shmups", "🎨"], ["Pixel", "🐝"]):
            self.notes.clear()
            calls = []

            def fake(title, labels, **kw):
                calls.append(1)
                return ("n", None) if len(calls) == 1 else None
            with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", side_effect=answers):
                self.assertFalse(tagui.edit_game_tags(A, "A"))
            self.assertEqual(len(self.notes), 1, answers)
            self.assertEqual(list(tags.all_tags()), ["cave", "shmups"])

    def test_emoji_only_name_gets_its_own_message(self):
        calls = []
        with mock.patch.object(picker, "filter_list", lambda t, l, **kw: ("n", None) if not calls.append(1) and len(calls) == 1 else None), \
                mock.patch.object(ui, "ask", side_effect=["🎨", "🎨"]):
            self.assertFalse(tagui.edit_game_tags(A, "A"))
        self.assertIn("no letters or digits", self.notes[0])
        self.assertNotIn("already", self.notes[0])

    def test_unmounted_share_systemexit(self):
        before = tags.load()
        with mock.patch.object(picker, "filter_list", return_value=[True, True]), \
                mock.patch.object(tags, "change_game_tags", side_effect=SystemExit("share not mounted")):
            self.assertFalse(tagui.edit_game_tags(B, "B"))
        self.assertEqual(len(self.notes), 1)
        self.assertIs(tags.load(), before)

    def test_edit_game_tags_storage_error(self):
        before = tags.load()
        with mock.patch.object(picker, "filter_list", return_value=[True, True]), \
                mock.patch.object(tags, "change_game_tags", side_effect=OSError("down")):
            self.assertFalse(tagui.edit_game_tags(B, "B"))
        self.assertEqual(len(self.notes), 1)
        self.assertIs(tags.load(), before)
        self.assertEqual(tags.tags_of(B), ["shmups"])


    def test_saving_keeps_tags_another_machine_added(self):
        root = helpers.storage_tags(self, {
            "tags": {"shmups": {"name": "Shmups", "emoji": "🚀"}, "cave": {"name": "Cave", "emoji": "🐝"},
                     "rpg": {"name": "RPG", "emoji": "🐉"}},
            "games": {B: {"tags": ["shmups"]}}, "declined": {}})
        tags.load()
        with open(os.path.join(root, tags.KEY), "w", encoding="utf-8") as f:  # another machine adds cave to B
            f.write(tags.dump({"tags": tags.load()["tags"], "games": {B: {"tags": ["cave", "shmups"]}}, "declined": {}}))
        with mock.patch.object(picker, "filter_list", return_value=[True, False, True]):  # checked first: shmups, then cave and rpg; rpg checked, cave unseen
            self.assertTrue(tagui.edit_game_tags(B, "B"))
        self.assertEqual(tags.tags_of(B), ["cave", "rpg", "shmups"])

    def test_malformed_tags_json_in_storage_is_noted(self):
        root = helpers.storage_tags(self, {"tags": {"shmups": {"name": "Shmups", "emoji": "🚀"}},
                                           "games": {}, "declined": {}})
        tags.load()
        with open(os.path.join(root, tags.KEY), "w", encoding="utf-8") as f:  # broken after this run read it
            f.write("{nope")
        with mock.patch.object(picker, "filter_list", return_value=[True]):
            self.assertFalse(tagui.edit_game_tags(B, "B"))
        self.assertEqual(len(self.notes), 1)

    def test_a_disc_row_edits_its_games_record(self):
        helpers.storage_tags(self, {"tags": {"shmups": {"name": "Shmups", "emoji": "🚀"}, "cave": {"name": "Cave", "emoji": "🐝"}},
                                    "games": {B: {"tags": ["shmups"], "files": ["nes/B (Disc 2).zip"]}}, "declined": {}})
        seen = []

        def fake(title, labels, **kw):
            seen.append(kw["initial"])
            return [True, True]
        with mock.patch.object(picker, "filter_list", fake):
            self.assertTrue(tagui.edit_game_tags("nes/B (Disc 2).zip", "B"))
        self.assertEqual(seen, [[True, False]])  # checked tags first
        self.assertEqual(set(tags.load()["games"]), {B})
        self.assertEqual(tags.tags_of(B), ["cave", "shmups"])


class TagFilterTest(unittest.TestCase):
    C = "nes/C (USA).zip"

    def setUp(self):
        data_dir = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(store, "data_dir", return_value=data_dir))
        helpers.storage_tags(self, {
            "tags": {"shmups": {"name": "Shmups", "emoji": "🚀"}, "cave": {"name": "Cave", "emoji": "🐝"},
                     "rpg": {"name": "RPG", "emoji": "🐉"}},
            "games": {A: {"tags": ["shmups"], "files": ["nes/A.sav"]}, B: {"tags": ["cave", "shmups"]}},
            "declined": {}})
        self.notes = []
        self.enterContext(mock.patch.object(edit, "note", self.notes.append))

    def test_keep_needs_every_required_tag_and_none_of_the_excluded(self):
        f = tagui.TagFilter()
        self.assertTrue(all(f.keep(k) for k in (A, B, self.C)))
        f.required, f.excluded = {"shmups"}, {"cave"}
        self.assertEqual([k for k in (A, B, self.C) if f.keep(k)], [A])
        self.assertTrue(f.keep("nes/A.sav"))  # a file of a record counts as its game
        f.required = set()
        self.assertEqual([k for k in (A, B, self.C) if f.keep(k)], [A, self.C])  # untagged games aren't excluded
        f.clear()
        self.assertEqual((f.required, f.excluded), (set(), set()))
        self.assertTrue(all(f.keep(k) for k in (A, B, self.C)))

    def test_keep_follows_a_tag_change(self):
        f = tagui.TagFilter()
        f.required = {"shmups"}
        self.assertFalse(f.keep(self.C))
        tags.change_game_tags(self.C, add=["shmups"])
        self.assertTrue(f.keep(self.C))

    def test_a_filter_of_tags_that_no_longer_exist_is_not_active(self):
        f = tagui.TagFilter()
        f.required = {"gone"}
        self.assertFalse(f.active())
        f.excluded = {"cave"}
        self.assertTrue(f.active())

    def test_a_deleted_filter_tag_stops_hiding_games(self):
        f = tagui.TagFilter()
        f.required = {"shmups"}
        self.assertFalse(f.keep(self.C))
        tags.delete_tag("shmups")
        self.assertTrue(f.keep(self.C))  # every row hidden by a tag no banner names was the bug
        self.assertEqual((f.describe(), f.active(), f.required), ("", False, set()))

    def test_state_restore_and_pick_drop_tags_that_no_longer_exist(self):
        f = tagui.TagFilter()
        f.restore(({"gone", "shmups"}, {"lost"}, False))
        self.assertEqual(f.state(), ({"shmups"}, set(), False))
        f.required, f.excluded = {"gone"}, {"cave", "lost"}
        seen = []
        with mock.patch.object(picker, "filter_list", lambda title, labels, **kw: seen.append(labels)):
            f.pick({A, B, self.C})
        self.assertEqual((f.required, f.excluded), (set(), {"cave"}))
        self.assertEqual(seen[0][0], "🚫 🐝 Cave (0)")

    def test_retarget_follows_a_merge_and_a_delete(self):
        f = tagui.TagFilter()
        f.required, f.excluded = {"shmups"}, {"rpg"}
        f.retarget("shmups", "cave")
        self.assertEqual((f.required, f.excluded), ({"cave"}, {"rpg"}))
        f.retarget("rpg", "cave")  # already required: required wins
        self.assertEqual((f.required, f.excluded), ({"cave"}, set()))
        f.retarget("cave", None)
        self.assertEqual((f.required, f.excluded), (set(), set()))

    def test_describe(self):
        f = tagui.TagFilter()
        self.assertEqual(f.describe(), "")
        f.required, f.excluded = {"shmups"}, {"cave"}
        self.assertEqual(f.describe(), "✅ 🚀 Shmups · 🚫 🐝 Cave")

    def test_pick_cycles_a_tag_off_required_excluded_off_on_the_same_row(self):
        f, seen = tagui.TagFilter(), []
        answers = iter([1, 1, 1, None])

        def fake(title, labels, **kw):
            seen.append((labels, kw.get("cursor"), set(f.required), set(f.excluded)))
            return next(answers)
        with mock.patch.object(picker, "filter_list", fake):
            self.assertIsNone(f.pick({A, B, self.C}))
        none = "⬜ 🈳 No tags at all (1)"
        self.assertEqual(seen[0][0], ["⬜ 🐝 Cave (1)", "⬜ 🚀 Shmups (2)", none])  # RPG has no game among the rows
        self.assertEqual(seen[1][0], ["⬜ 🐝 Cave (1)", "✅ 🚀 Shmups (2)", "⬜ 🈳 No tags at all (replaces the ✅ tags)"])
        self.assertEqual(seen[2][0], ["⬜ 🐝 Cave (0)", "🚫 🚀 Shmups (0)", none])  # the rows stay, the counts follow
        self.assertEqual(seen[3][0], ["⬜ 🐝 Cave (1)", "⬜ 🚀 Shmups (2)", none])
        self.assertEqual([s[1] for s in seen[1:]], [1, 1, 1])
        self.assertEqual([(s[2], s[3]) for s in seen[1:]], [({"shmups"}, set()), (set(), {"shmups"}), (set(), set())])
        self.assertEqual((f.required, f.excluded), (set(), set()))

    def test_the_no_tags_row_is_left_out_while_a_tag_is_required(self):
        f, seen = tagui.TagFilter(), []
        f.required = {"shmups"}
        with mock.patch.object(picker, "filter_list", lambda t, labels, **kw: seen.append(list(labels)) or None):
            f.pick({A, B, self.C})
        self.assertEqual(seen, [["⬜ 🐝 Cave (1)", "✅ 🚀 Shmups (2)"]])

    def test_untagged_keeps_only_games_with_no_tags_and_excludes_required_tags(self):
        f = tagui.TagFilter()
        f.untagged = True
        self.assertEqual([k for k in (A, B, self.C, "nes/A.sav") if f.keep(k)], [self.C])
        self.assertEqual(f.describe(), "✅ " + tagui.NO_TAGS)
        f.clear()
        self.assertFalse(f.untagged)
        self.assertFalse(f.active())

    def test_pick_untagged_and_required_tags_clear_each_other(self):
        f, seen = tagui.TagFilter(), []
        answers = iter([2, 0, None])  # no tags, then Cave required (clears it)

        def fake(title, labels, **kw):
            seen.append((list(labels), f.untagged, set(f.required)))
            return next(answers)
        with mock.patch.object(picker, "filter_list", fake):
            f.pick({A, B, self.C})
        self.assertEqual(seen[1][1:], (True, set()))
        self.assertEqual(seen[1][0][0], "⬜ 🐝 Cave (1)")  # the tags stay listed with the untagged filter on
        self.assertEqual(seen[2][1:], (False, {"cave"}))

    def test_pick_lists_a_required_tag_with_no_game_here_and_counts_the_narrowed_rows(self):
        f, seen = tagui.TagFilter(), []
        f.required = {"rpg"}
        with mock.patch.object(picker, "filter_list", lambda t, labels, **kw: seen.append(labels)):
            f.pick({A, B})
        self.assertEqual(seen, [["✅ 🐉 RPG (0)"]])
        f.required = {"cave"}
        seen.clear()
        with mock.patch.object(picker, "filter_list", lambda t, labels, **kw: seen.append(labels)):
            f.pick({A, B, self.C})
        self.assertEqual(seen, [["✅ 🐝 Cave (1)", "⬜ 🚀 Shmups (1)"]])  # only B is left, and it has Shmups too

    def test_pick_c_clears_and_reopens(self):
        f, calls = tagui.TagFilter(), []
        f.required, f.excluded = {"shmups"}, {"cave"}
        answers = iter([("c", 0), None])

        def fake(title, labels, **kw):
            calls.append(labels)
            self.assertIn("c", kw["hotkeys"])
            return next(answers)
        with mock.patch.object(picker, "filter_list", fake):
            f.pick({A, B})
        self.assertEqual(calls[1], ["⬜ 🐝 Cave (1)", "⬜ 🚀 Shmups (2)"])
        self.assertEqual((f.required, f.excluded), (set(), set()))

    def test_pick_with_no_tag_among_the_rows_notes_it(self):
        f = tagui.TagFilter()
        with mock.patch.object(picker, "filter_list") as fl:
            f.pick({self.C})
        fl.assert_not_called()
        self.assertEqual(self.notes, ["ℹ️  No tag has games among these."])


class StickyFilter(unittest.TestCase):
    def setUp(self):
        data_dir = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(store, "data_dir", return_value=data_dir))
        helpers.storage_tags(self, {
            "tags": {"shmups": {"name": "Shmups", "emoji": "🚀"}, "cave": {"name": "Cave", "emoji": "🐝"}},
            "games": {A: {"tags": ["shmups"]}, B: {"tags": ["cave"]}}, "declined": {}})
        tagui.FILTER.clear()
        self.addCleanup(tagui.FILTER.clear)

    def test_filter_is_shared(self):
        from sync_roms import cardedit
        with mock.patch.object(cardedit, "_spawn", lambda fn: None), mock.patch.object(cardedit, "_metadata", {"nes": None}):
            self.assertIs(cardedit.GameFilters({"bucket": "nes", "name": "NES"}).tags, tagui.FILTER)

    def test_banner_empty_without_filter(self):
        self.assertEqual(tagui.banner(), "")

    def test_banner_counts_the_hidden_rows_only_when_some_are_hidden(self):
        tagui.FILTER.required = {"shmups"}
        self.assertEqual(tagui.banner(1, 3), "✅ 🚀 Shmups · 1 of 3 shown (c clear filters)")
        self.assertEqual(tagui.banner(3, 3), "✅ 🚀 Shmups (c clear filters)")
        tagui.FILTER.clear()
        self.assertEqual(tagui.banner(0, 3), "")

    def test_paused_names_the_filter_only_when_one_is_set(self):
        self.assertEqual(tagui.paused(), "")
        tagui.FILTER.required = {"shmups"}
        self.assertIn("paused", tagui.paused())

    def test_games_hint_names_s_t_c_and_the_live_keys_once(self):
        hint = tagui.games_hint("Space toggle · Enter done · a all · s tag · m meta · c clear · t tags · v variant")
        self.assertEqual(hint, "Space toggle · Enter done · s filter by tag · t edit tags · T tag all shown · c clear filters · / filter"
                               " · w note · a all shown · m meta · v variant")
        self.assertNotIn("w note", tagui.games_hint("Space toggle · Enter done", notes=False))
        self.assertNotIn("a all", tagui.games_hint("Space toggle · Enter done", select_all=False))
        paused = tagui.games_hint("Space toggle · Enter done", filtering=False)
        self.assertIn("t edit tags", paused)
        self.assertNotIn("s filter", paused)

    def test_banner_lists_required_and_excluded(self):
        tagui.FILTER.required, tagui.FILTER.excluded = {"shmups"}, {"cave"}
        self.assertEqual(tagui.banner(), "✅ 🚀 Shmups · 🚫 🐝 Cave (c clear filters)")

    def test_handle_key_clear_resets_filter_and_query(self):
        tagui.FILTER.required = {"shmups"}
        place = {"session": {"query": "x"}}
        self.assertTrue(tagui.handle_key("c", [A], place))
        self.assertEqual(tagui.FILTER.required, set())
        self.assertEqual(place, {"session": {}})
        self.assertTrue(tagui.handle_key("c", [A]))  # no place

    def test_handle_key_s_picks_over_the_rows(self):
        with mock.patch.object(tagui.FILTER, "pick") as pick:
            self.assertTrue(tagui.handle_key("s", [A, B], {}))
        pick.assert_called_once_with([A, B])

    def test_handle_key_ignores_other_keys(self):
        tagui.FILTER.required = {"shmups"}
        self.assertFalse(tagui.handle_key("m", [A]))
        self.assertEqual(tagui.FILTER.required, {"shmups"})
        self.assertEqual(tagui.HOTKEYS, ("s", "c"))
        self.assertEqual([k for k, _ in tagui.KEYS_HELP], ["s", "c"])


class TagPickerErgonomics(Base):
    def setUp(self):
        super().setUp()
        tags.define_tag("arcade", {"name": "Arcade", "emoji": "🕹️"})
        tags.define_tag("zed", {"name": "Zed", "emoji": "💤", "description": "sleepy picks"})

    def test_t_picker_lists_checked_then_recent_then_alphabetical(self):
        tagui.RECENT[:] = ["zed"]
        labels, kw = self.pick_tags(B, {"shmups"})
        self.assertEqual([x.split(" (")[0].split(" ", 1)[1] for x in labels], ["Shmups", "Zed", "Arcade", "Cave"])

    def test_t_picker_label_carries_the_description_so_search_matches_it(self):
        labels, kw = self.pick_tags(B, {"shmups"})
        self.assertTrue(any("sleepy picks" in x for x in labels))

    def test_saving_remembers_the_added_tags_most_recent_first_capped_at_eight(self):
        for n in range(10):
            tags.define_tag(f"t{n}", {"name": f"T{n}", "emoji": f"{n}\ufe0f\u20e3"})
        self.pick_tags(B, {"shmups", "cave"})
        self.assertEqual(tagui.RECENT, ["cave"])
        for n in range(10):
            self.pick_tags(B, {"shmups", "cave", f"t{n}"}, after=None)
        self.assertEqual(len(tagui.RECENT), 8)
        self.assertEqual(tagui.RECENT[0], "t9")

    def test_saving_says_what_changed(self):
        self.pick_tags(B, {"cave"})  # shmups off, cave on
        self.assertEqual(self.notes[-1], "🏷️  Tagged B: +1 −1")

    def test_repeat_applies_the_last_add_and_remove_to_another_game(self):
        self.pick_tags(B, {"cave"})
        tags.change_game_tags(A, add={"shmups"})
        self.assertTrue(tagui.repeat_last(A, "A"))
        self.assertEqual(tags.tags_of(A), ["cave"])
        self.assertEqual(self.notes[-1], "🏷️  Tagged A: +1 −1")

    def test_the_note_counts_only_what_changed_and_repeat_keeps_what_it_repeats(self):
        self.pick_tags(B, {"cave"})  # shmups off, cave on
        self.assertTrue(tagui.repeat_last(A, "A"))  # A lacked shmups: nothing to take off
        self.assertEqual(self.notes[-1], "🏷️  Tagged A: +1 −0")
        self.assertTrue(tagui.repeat_last(A, "A"))  # A has cave now
        self.assertEqual(self.notes[-1], "🏷️  Tagged A: +0 −0")
        self.assertEqual(tagui.LAST, [(frozenset({"cave"}), frozenset({"shmups"}))])

    def test_repeat_with_nothing_to_repeat_says_so(self):
        self.assertFalse(tagui.repeat_last(A, "A"))
        self.assertIn("Nothing to repeat", self.notes[-1])
        self.assertEqual(tags.tags_of(A), [])

    def test_esc_after_n_notes_the_new_tag_was_not_applied(self):
        calls = []

        def fake(title, labels, **kw):
            calls.append(1)
            return ("n", None) if len(calls) == 1 else None
        with mock.patch.object(picker, "filter_list", fake), mock.patch.object(ui, "ask", side_effect=["Pixel Art", "🎨"]):
            self.assertFalse(tagui.edit_game_tags(B, "B"))
        self.assertIn("Pixel Art was added but not applied", self.notes[-1])
        self.assertIn("pixel-art", tags.all_tags())

    def test_x_in_the_filter_picker_excludes_directly_and_again_clears(self):
        self.addCleanup(tagui.FILTER.clear)
        tagui.FILTER.clear()
        script = iter([("x", 0), None])
        seen = []

        def fake(title, labels, **kw):
            seen.append(kw)
            return next(script)
        with mock.patch.object(picker, "filter_list", fake):
            tagui.FILTER.pick([A, B])
        self.assertEqual(tagui.FILTER.excluded, {"shmups"})
        self.assertIn("x", seen[0]["hotkeys"])
        self.assertIn("x", seen[0]["hint"])
        script = iter([("x", 0), None])
        with mock.patch.object(picker, "filter_list", fake):
            tagui.FILTER.pick([A, B])
        self.assertEqual(tagui.FILTER.excluded, set())

    def test_pickers_show_the_description_as_the_row_note(self):
        self.addCleanup(tagui.FILTER.clear)
        tags.change_game_tags(A, add=["zed"])
        seen = []

        def fake(title, labels, **kw):
            seen.append((labels, kw))
            return None
        with mock.patch.object(picker, "filter_list", fake):
            tagui.FILTER.pick([A, B])
            tagui.bulk_tag([A, B])
        labels, kw = seen[0]
        self.assertEqual(kw["row_note"](next(i for i, x in enumerate(labels) if "Zed" in x)), "sleepy picks")
        self.assertEqual(kw["row_note"](0), "")
        labels, kw = seen[1]
        self.assertEqual(kw["row_note"](next(i for i, x in enumerate(labels) if "Zed" in x)), "sleepy picks")


class DiscsComeBack(Base):
    """A multi-disc game whose last tag went loses its record and files; t, . and T tag it again with its discs."""
    PLAYLIST = ["psx/FF7.m3u", "psx/FF7 (Disc 1).chd", "psx/FF7 (Disc 2).chd"]
    LOOSE = ["psx/MGS (Disc 1).chd", "psx/MGS (Disc 2).chd"]  # discs with no playlist

    def setUp(self):
        super().setUp()
        from sync_roms import inventory, runtime
        for key in self.PLAYLIST + self.LOOSE:
            helpers.touch(os.path.join(runtime.ROOT, key))
        inventory.reset()

    def files(self):
        return {k: (tags.record(k) or {}).get("files") for k in (self.PLAYLIST[0], self.LOOSE[0])}

    def untag(self):
        for lead in (self.PLAYLIST[0], self.LOOSE[0]):
            self.pick_tags(lead, set())
        self.assertEqual(self.files(), {self.PLAYLIST[0]: None, self.LOOSE[0]: None})

    def test_t_dot_and_T_restore_the_discs(self):
        want = {self.PLAYLIST[0]: self.PLAYLIST[1:], self.LOOSE[0]: self.LOOSE[1:]}
        for lead in want:
            self.pick_tags(lead, {"cave"})
        self.assertEqual(self.files(), want)
        self.untag()
        tagui.LAST[:] = [(frozenset({"cave"}), frozenset())]
        for lead in want:
            self.assertTrue(tagui.repeat_last(lead, lead))
        self.assertEqual(self.files(), want)
        self.untag()
        self.bulk(list(want), {"cave"})
        self.assertEqual(self.files(), want)


if __name__ == "__main__":
    unittest.main()
