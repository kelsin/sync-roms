"""Multi-disc .m3u playlist generation."""
import os
import posixpath
import re
from collections import defaultdict

from . import external, store, ui


DISC_RE = re.compile(r" \(Disc (\d+|[A-Z]|[IVX]+)\)")  # "Disc 1", "Disc A" or "Disc II"
ROMAN = {"I": 1, "V": 5, "X": 10}
TAG_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)")  # a bracket tag may hold parentheses: "[Hack v0 (09-04-2017)]"
DISC_EXTS = {".chd", ".rvz",".cue", ".iso", ".pbp", ".gdi", ".cso", ".ccd"}


def _roman(s):
    values = [ROMAN[c] for c in s]
    return sum(-v if v < w else v for v, w in zip(values, values[1:] + [0]))


def _disc_number(label, labels):
    """A disc label's number: 1 for "1", "A" or "I". A game's labels are Roman numerals only when all of them are."""
    if label.isdigit():
        return int(label)
    if all(set(n) <= set(ROMAN) for n in labels):
        return _roman(label)
    return ord(label) - ord("A") + 1 if len(label) == 1 else 0


def disc_groups(files):
    """{m3u name: disc files in order} for the multi-disc games among one folder's files.

    "Name (Disc 1) (Key Disc) (Sega CD).chd" and "Name (Disc 2) (Sega CD).chd" are one game; the playlist is named
    after the title with "(Disc N)" and any tags the discs don't all share removed: "Name (Sega CD).m3u".
    "[...]" tags after "(Disc N)" (translations, hacks) make a game of their own and are always kept in the name.
    """
    games = defaultdict(list)
    for f in files:
        stem, ext = os.path.splitext(f)
        m = DISC_RE.search(stem)
        if m and ext.lower() in DISC_EXTS:
            tags = TAG_RE.findall(stem[m.end():])
            brackets = tuple(t for t in tags if t.startswith("["))
            games[(stem[:m.start()], brackets, ext.lower())].append((m.group(1), tags, f))
    groups = {}
    for (title, _, _), discs in games.items():
        discs = sorted((_disc_number(n, {n for n, _, _ in discs}), tags, f) for n, tags, f in discs)
        if len(discs) < 2 or len({n for n, _, _ in discs}) < len(discs):
            continue
        shared = [t for t in discs[0][1] if all(t in tags for _, tags, _ in discs)]
        groups[title + "".join(f" {t}" for t in shared) + ".m3u"] = [f for _, _, f in discs]
    return groups


def disc_keys(keys):
    """The bucket keys that are discs of a multi-disc game (the files its playlist lists)."""
    folders = defaultdict(list)
    for k in keys:
        folders[posixpath.dirname(k)].append(posixpath.basename(k))
    return {posixpath.join(d, f) for d, names in folders.items() for discs in disc_groups(names).values() for f in discs}


def file_groups(keys):
    """{bucket key: every key of its game} for the multi-disc games among keys: its playlist (when in keys) and its
    discs, within one folder. Keys that are no multi-disc game's are left out."""
    folders = defaultdict(set)
    for k in keys:
        folders[posixpath.dirname(k)].add(posixpath.basename(k))
    out = {}
    for d, names in folders.items():
        for m3u, discs in disc_groups(names).items():
            group = [posixpath.join(d, f) for f in ([m3u] if m3u in names else []) + discs]
            for k in group:
                out[k] = group
    return out


def prefixed_entries(entries, dest, disc_dir, coming=()):
    """entries with each bare disc name whose file is in dest/disc_dir (or is in coming, paths a sync is about to write)
    pointed into disc_dir."""
    return [posixpath.join(disc_dir, e) if "/" not in e and (os.path.exists(os.path.join(dest, disc_dir, e))
                                                            or os.path.normpath(os.path.join(dest, disc_dir, e)) in coming) else e
            for e in entries]


def prefix_playlists(dest, disc_dir, skip=()):
    """Point the playlists directly in dest at their discs in dest/disc_dir, except those in skip (paths written already
    prefixed). Returns how many it rewrote."""
    rewritten = 0
    skip = {os.path.normpath(p) for p in skip}
    for name in sorted(os.listdir(dest)):
        path = os.path.join(dest, name)
        if not name.lower().endswith(".m3u") or os.path.normpath(path) in skip or not os.path.isfile(path):
            continue
        entries = m3u_entries(path)
        fixed = prefixed_entries(entries, dest, disc_dir)
        if fixed != entries:
            store.replace_file(path, "".join(line + "\n" for line in fixed), newline="\n")
            rewritten += 1
    return rewritten


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
        dirs[:] = sorted(d for d in dirs if not external.own_temp(d) and not d.startswith("."))
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
        ui.fail(f"{root} is not a folder", 2)
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
            store.replace_file(path, "".join(line + "\n" for line in lines), newline="\n")
    print(ui.green(f"🎉 Done: {len(plan) - kept} change(s)"))
    return 0
