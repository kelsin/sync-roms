"""`sync-roms sets edit`: edit the repo's game sets by hand and open a PR with the changes."""
import copy
import json
import os
import shutil
import subprocess
import tempfile
import time

from . import edit, picker, s3, store, ui


REPO = "kelsin/sync-roms"
SETS_DIR = os.path.join("src", "sync_roms", "data", "sets")


# --- Set files ---------------------------------------------------------------------------------------

def repo_sets():
    """The repo's own sets as {id: {"name", "description", "games"}} (personal sets aren't included)."""
    folder = os.path.join(store.REPO_DATA, "sets")
    sets = {}
    for name in sorted(os.listdir(folder)):
        if name.endswith(".json"):
            game_set = store.read_set_file(os.path.join(folder, name), name[:-5])
            sets[game_set.pop("id")] = game_set
    return sets


def set_text(game_set):
    """A set as the text of its file, in the format the repo's set files already use."""
    data = {"name": game_set["name"]}
    if game_set.get("description"):
        data["description"] = game_set["description"]
    data["games"] = game_set["games"]
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# --- Editing the games of one set --------------------------------------------------------------------

def view(game_set, systems):
    """The set's games per known system, shaped like a games list so the toggler can edit them."""
    return {s["bucket"]: {"bucket": s["bucket"], "name": s["name"], "full_system": False,
                          "games": [g for g in game_set["games"] if g.get("system") == s["bucket"] and g.get("bucket")]}
            for s in systems}


def insert_game(games, game):
    """Add game after the last game of its category, or at the end when its category is new (or it has none)."""
    cat = game.get("category")
    last = max((i for i, x in enumerate(games) if cat and x.get("category") == cat), default=len(games) - 1)
    games.insert(last + 1, game)


def reconcile(games, shown, category=""):
    """The set's games after the toggler changed `shown` (a view): drop what was switched off, add what was switched on.

    Entries of systems that weren't shown, and untouched entries, are kept as they are."""
    now = {g["bucket"]: (s["bucket"], g) for s in shown.values() for g in s["games"]}
    out = [g for g in games if g.get("system") not in shown or not g.get("bucket") or g["bucket"] in now]
    have = {g.get("bucket") for g in out}
    for key, (system, g) in now.items():
        if key not in have:
            insert_game(out, {"title": g["title"], **({"category": category} if category else {}),
                              "system": system, "bucket": key})
    return out


def recategorize(games, game, category):
    """Give game a new category (empty removes it) and move it next to the games of that category."""
    if (game.get("category") or "") == category:
        return
    moved = {}
    for k, v in game.items():
        if k != "category":
            moved[k] = v
        if k == "title" and category:
            moved["category"] = category
    if category:
        moved.setdefault("category", category)
    games[:] = [x for x in games if x is not game]
    insert_game(games, moved)


def ask_category(games, what):
    cats = list(dict.fromkeys(g["category"] for g in games if g.get("category")))
    if cats:
        print(ui.dim(f"  Categories: {', '.join(cats)}"))
    return ui.ask(f"🏷️  Category for {what} (empty for none): ").strip()


def game_label(game, systems):
    names = {s["bucket"]: s["name"] for s in systems}
    return f"{game.get('category') + ' — ' if game.get('category') else ''}{names.get(game.get('system'), game.get('system'))}" \
           f" — {game.get('title') or game['bucket']}"


def edit_one(game_set, systems, keys_of):
    """Edit one set: remove games, add games from a system, change categories, rename."""
    while True:
        i = picker.filter_list(f"✏️  {game_set['name']} (Esc = back)",
                               [f"Games in this set ({len(game_set['games'])}): switch some off",
                                "Add games from a system", "Change a game's category", "Rename / change the description"])
        if i is None:
            return
        shown = view(game_set, systems)
        if i == 0:
            rows = edit.set_rows(game_set, shown, lambda s: keys_of(s["bucket"]))
            if not rows:
                edit.note(ui.yellow("ℹ️  This set has no games yet."))
                continue
            edit.toggle_games(f"✏️  {game_set['name']} — ✅ in the set, ⬜ remove it", rows)
            game_set["games"] = reconcile(game_set["games"], shown)
        elif i == 1:
            j = picker.filter_list("✏️  Add games from which system?", [s["name"] for s in systems])
            if j is None:
                continue
            s = shown[systems[j]["bucket"]]
            had = {g["bucket"] for g in s["games"]}
            edit.toggle_games(f"✏️  {s['name']} — ✅ in {game_set['name']}, ⬜ in storage only",
                              edit.system_rows(s, keys_of(s["bucket"])))
            added = {g["bucket"] for g in s["games"]} - had
            category = ask_category(game_set["games"], f"{len(added)} new game(s)") if added else ""
            game_set["games"] = reconcile(game_set["games"], shown, category)
        elif i == 2:
            games = [g for g in game_set["games"] if g.get("bucket")]
            j = picker.filter_list("✏️  Change which game's category?", [game_label(g, systems) for g in games])
            if j is not None:
                recategorize(game_set["games"], games[j], ask_category(game_set["games"], games[j].get("title", "it")))
        else:
            name = ui.ask(f"Name [{game_set['name']}] (empty keeps it): ").strip()
            desc = ui.ask("Description (empty keeps it): ").strip()
            game_set["name"] = name or game_set["name"]
            game_set["description"] = desc or game_set.get("description", "")


# --- What changed ------------------------------------------------------------------------------------

def game_line(game):
    return f"{game.get('title') or game['bucket']} ({game['bucket']})"


def diff_sets(before, after):
    """[(kind, set id, [lines])] for every set that was created, removed or changed; kind is new, removed or changed."""
    found = []
    for sid in sorted(set(before) | set(after)):
        a, b = before.get(sid), after.get(sid)
        if a is None:
            found.append(("new", sid, [f"+ {game_line(g)}" for g in b["games"] if g.get("bucket")]))
        elif b is None:
            found.append(("removed", sid, [f"{len(a['games'])} game(s)"]))
        elif a != b:
            lines = [f"name: {a['name']} → {b['name']}"] if a["name"] != b["name"] else []
            if a.get("description", "") != b.get("description", ""):
                lines.append("description changed")
            old = {g["bucket"]: g for g in a["games"] if g.get("bucket")}
            new = {g["bucket"]: g for g in b["games"] if g.get("bucket")}
            lines += [f"+ {game_line(new[k])}" for k in new if k not in old]
            lines += [f"- {game_line(old[k])}" for k in old if k not in new]
            lines += [f"~ {game_line(new[k])}: category {old[k].get('category') or 'none'} → {new[k].get('category') or 'none'}"
                      for k in new if k in old and (old[k].get("category") or "") != (new[k].get("category") or "")]
            found.append(("changed", sid, lines or ["edited"]))
    return found


def commit_title(found):
    if len(found) == 1:
        kind, sid, _ = found[0]
        return f"feat(sets): {'add' if kind == 'new' else 'remove' if kind == 'removed' else 'update'} {sid}"
    return f"feat(sets): update {len(found)} sets"


def pr_body(found):
    return "\n\n".join(f"### {sid} ({kind})\n" + "\n".join(f"- {line}" for line in lines) for kind, sid, lines in found)


def print_changes(found):
    print(ui.bold("\n📝 Changes"))
    for kind, sid, lines in found:
        print(ui.bold(f"  {sid}") + ui.dim(f"  ({kind})"))
        for line in lines:
            print((ui.green if line.startswith("+") else ui.red if line.startswith("-") else str)(f"    {line}"))


# --- The pull request --------------------------------------------------------------------------------

def need_tools():
    for tool in ("git", "gh"):
        if not shutil.which(tool):
            ui.fail(f"{tool} isn't installed, and opening a PR needs both git and the GitHub CLI (gh).")
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode:
        ui.fail("gh isn't logged in. Run `gh auth login` first.")


def run(cmd, cwd=None):
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if done.returncode:
        ui.fail(f"{' '.join(cmd[:2])} failed: {(done.stderr or done.stdout).strip()}", 1)
    return done.stdout.strip()


def open_pr(after, found):
    """Clone the repo to a temp folder, write the changed sets, and push a branch with a PR. Returns the PR's URL."""
    tmp = tempfile.mkdtemp(prefix="sync-roms-pr-")
    try:
        print(ui.dim(f"📥 Cloning {REPO} ..."))
        run(["gh", "repo", "clone", REPO, tmp, "--", "--depth", "1"])
        branch = "sets-edit-" + time.strftime("%Y%m%d-%H%M%S")
        run(["git", "checkout", "-b", branch], tmp)
        for kind, sid, _ in found:
            path = os.path.join(tmp, SETS_DIR, sid + ".json")
            if kind == "removed":
                os.remove(path)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(set_text(after[sid]))
        title = commit_title(found)
        run(["git", "add", "-A"], tmp)
        run(["git", "commit", "-m", title], tmp)
        run(["git", "push", "-u", "origin", branch], tmp)
        return run(["gh", "pr", "create", "--title", title, "--body", pr_body(found), "--head", branch], tmp).splitlines()[-1]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- The editor --------------------------------------------------------------------------------------

def local_references(set_id):
    """Where your own lists still use a set id: games.json and cards."""
    found = []
    try:
        if set_id in store.list_sets(store.personal_json("games.json")):
            found.append("games.json")
    except OSError:
        pass
    found += [f"card {card}" for card in store.all_card_names() if set_id in store.list_sets(store.card_games(card))]
    return found


def new_set(working):
    """Ask for a new set's name and description and add it to working; returns its id, or None when cancelled."""
    while True:
        name = ui.ask("📦 Name for the new set (empty to cancel): ").strip()
        if not name:
            return None
        sid = store.set_slug(name)
        if not sid:
            print(ui.yellow("  A set needs a name with letters or digits."))
        elif sid in working:
            print(ui.yellow(f"  There is already a set with the id {sid}."))
        else:
            break
    working[sid] = {"name": name, "description": ui.ask("   One-line description (optional): ").strip(), "games": []}
    return sid


def edit_sets():
    """Edit the repo's sets, then open a PR with the changes. Returns the exit code."""
    need_tools()
    systems = sorted(store.repo_json("systems"), key=lambda s: s["name"].lower())
    before = repo_sets()
    working = copy.deepcopy(before)
    listed = {}

    def keys_of(bucket):
        if bucket not in listed:
            print(ui.dim(f"📡 Listing {s3.location()}/{bucket}/ ..."))
            listed[bucket] = {k for k in s3.list_sizes(bucket + "/") if not k.endswith("/")}
        return listed[bucket]

    while True:
        ids = sorted(working, key=lambda x: working[x]["name"].lower())
        n = len(ids)
        edited = {sid for _, sid, _ in diff_sets(before, working)}
        labels = ([f"{working[x]['name']}  ({len(working[x]['games'])} games)" for x in ids]
                  + ["➕ New set", "✅ Done (review & open PR)", "🚪 Quit without saving"])
        extras = [[("  " + ("new" if x not in before else "edited"), "cyan")] if x in edited else [] for x in ids] + [[], [], []]
        i = picker.filter_list("✏️  Which set?  (Esc = review & open PR)", labels, extras=extras,
                               hotkeys=(edit.DELETE_KEY,), hint="/ filter · Enter open · d delete · Esc review")
        if isinstance(i, tuple):
            if i[1] < n:
                sid = ids[i[1]]
                where = local_references(sid)
                note = f" Your {', '.join(where)} still reference(s) it." if where else ""
                if ui.confirm(f"🗑️  Delete set {working[sid]['name']}?{note}", default=False):
                    del working[sid]
            continue
        if i is not None and i < n:
            edit_one(working[ids[i]], systems, keys_of)
            continue
        if i == n:
            sid = new_set(working)
            if sid:
                edit_one(working[sid], systems, keys_of)
            continue
        if i == n + 2:
            if not edited or ui.confirm("Discard your pending changes and quit?", default=False):
                print(ui.yellow("👋 Quit without saving."))
                return 0
            continue
        found = diff_sets(before, working)
        if not found:
            print(ui.yellow("👋 No changes, nothing opened."))
            return 0
        empty = [sid for kind, sid, _ in found if kind != "removed" and not working[sid]["games"]]
        if empty:
            edit.note(ui.yellow(f"ℹ️  {', '.join(empty)} has no games. Add some or delete it first."))
            continue
        print_changes(found)
        answer = ui.choose("🔀 Open a PR with these changes?", "oed", "o", "o open · e keep editing · d discard")
        if answer == "e":
            continue
        if answer == "d":
            print(ui.yellow("👋 Not opened."))
            return 0
        print(ui.green("🎉 PR opened: ") + open_pr(working, found))
        return 0
