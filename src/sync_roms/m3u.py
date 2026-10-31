"""Multi-disc .m3u playlist generation."""
import os
import re
from collections import defaultdict

from . import external, ui


DISC_RE = re.compile(r" \(Disc (\d+)\)")
DISC_EXTS = {".chd", ".rvz",".cue", ".iso", ".pbp", ".gdi", ".cso", ".ccd"}


def disc_groups(files):
    """{m3u name: disc files in order} for the multi-disc games among one folder's files.

    "Name (Disc 1) (Key Disc) (Sega CD).chd" and "Name (Disc 2) (Sega CD).chd" are one game; the playlist is named
    after the title with "(Disc N)" and any tags the discs don't all share removed: "Name (Sega CD).m3u".
    """
    games = defaultdict(list)
    for f in files:
        stem, ext = os.path.splitext(f)
        m = DISC_RE.search(stem)
        if m and ext.lower() in DISC_EXTS:
            games[(stem[:m.start()], ext.lower())].append((int(m.group(1)), re.findall(r"\([^)]*\)", stem[m.end():]), f))
    groups = {}
    for (title, _), discs in games.items():
        discs.sort()
        if len(discs) < 2 or len({n for n, _, _ in discs}) < len(discs):
            continue
        shared = [t for t in discs[0][1] if all(t in tags for _, tags, _ in discs)]
        groups[title + "".join(f" {t}" for t in shared) + ".m3u"] = [f for _, _, f in discs]
    return groups


def m3u_entries(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return [line.strip() for line in f if line.strip() and not line.lstrip().startswith("#")]


def plan_m3u(root):
    """[(action, path, lines)] to make every multi-disc game under root have a correct .m3u.

    create: a game with none. rewrite: a playlist whose discs differ from the game's, or one with some missing files.
    delete: a playlist whose files are all missing. rename: a playlist under another name that lists exactly a game's
    discs (lines is the new path). A playlist that matches no game is kept if all its files exist.
    """
    plan = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not external.own_temp(d))
        files = sorted(f for f in files if not external.own_temp(f))
        groups = disc_groups(files)
        covered = {}
        for f in files:
            if not f.lower().endswith(".m3u") or f in groups:
                continue
            path = os.path.join(dirpath, f)
            entries = m3u_entries(path)
            valid = [e for e in entries if os.path.exists(os.path.join(dirpath, e))]
            if not valid:
                plan.append(("delete", path, []))
            elif len(valid) < len(entries):
                plan.append(("rewrite", path, valid))
            covered.setdefault(tuple(sorted(valid)), path)
        for name, discs in groups.items():
            path = os.path.join(dirpath, name)
            if name in files:
                if m3u_entries(path) != discs:
                    plan.append(("rewrite", path, discs))
            elif tuple(sorted(discs)) in covered:
                plan.append(("rename", covered[tuple(sorted(discs))], path))
            else:
                plan.append(("create", path, discs))
    return plan


def m3u_command(args):
    root = os.path.abspath(os.path.expanduser(args.m3u or os.getcwd()))
    if not os.path.isdir(root):
        raise SystemExit(ui.red(f"❌ {root} is not a folder"))
    print(ui.bold("💿 m3u playlists") + ui.dim(f"  {root}"))
    plan = plan_m3u(root)
    if not plan:
        print(ui.green("✅ All multi-disc playlists are correct"))
        return 0
    icons = {"create": "➕", "rewrite": "✏️ ", "delete": "🗑️ ", "rename": "🏷️ "}
    for action, path, lines in plan:
        to = f" {ui.dim('→')} {os.path.basename(lines)}" if action == "rename" else ""
        print(f"  {icons[action]} {action} {os.path.relpath(path, root)}{to}")
    if args.dry_run:
        print(ui.yellow("\n🧪 Dry run — nothing changed"))
        return 0
    deletes = [path for action, path, _ in plan if action == "delete"]
    kept = 0
    if deletes and not ui.confirm(f"🗑️  Delete {len(deletes)} playlist(s) whose files are all missing?", default=False):
        print(ui.yellow("  ↩️  Keeping them"))
        kept, deletes = len(deletes), []
    for action, path, lines in plan:
        if action == "delete":
            if path in deletes:
                os.remove(path)
        elif action == "rename":
            os.rename(path, lines)
        else:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("".join(line + "\n" for line in lines))
    print(ui.green(f"🎉 Done: {len(plan) - kept} change(s)"))
    return 0
