"""Print, as JSON, the groups of one system's ROMs that a frontend shows under the same scraped name.

Run from the repo root: uv run --frozen python .claude/skills/dedup-names/scripts/find_duplicates.py
Reads which ROMs storage holds only through the storage cache (sync-roms cache update refreshes it), and each system's
scrapes/<system>/metadata.json from storage.
"""
import json
import posixpath
import sys
from collections import Counter, defaultdict

from sync_roms import inventory, m3u, scrape_online, store, ui, usersettings, vita


def shown(name):
    """A name reduced for comparing: whitespace collapsed, case folded."""
    return " ".join(name.split()).casefold()


def set_folder_files(stored):
    """The keys of files inside a folder named after a sibling file's stem (mame/area51/area51.chd beside mame/area51.zip)."""
    stems = defaultdict(set)
    for k in stored:
        stems[posixpath.dirname(k)].add(posixpath.splitext(posixpath.basename(k))[0])
    return {k for k in stored for d in [posixpath.dirname(k)] if posixpath.basename(d) in stems[posixpath.dirname(d)]}


def why_skipped(system, rom, stored, discs, in_sets, clones):
    """Why a ROM with a metadata entry isn't shown as its own game under that name, or None."""
    key = f"{system}/{rom}"
    family = clones.get(system, {})
    stem = posixpath.splitext(rom)[0]
    for reason, hit in (("not_stored", key not in stored), ("vita_extras", vita.is_extra(key)), ("discs", key in discs),
                        ("set_folders", key in in_sets),
                        ("clones", stem in family.get("parents", {}) or stem in family.get("clones", {}))):
        if hit:
            return reason
    return None


def find(metadata, stored, clones):
    """{"groups": [...], "skipped": {reason: count}} from {system: metadata.json}, the stored keys and clones.json."""
    discs, in_sets, skipped, groups = m3u.disc_keys(stored), set_folder_files(stored), Counter(), []
    for system, entries in sorted(metadata.items()):
        by_name = defaultdict(list)
        for rom, entry in sorted(entries.items()):
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            reason = why_skipped(system, rom, stored, discs, in_sets, clones)
            if reason:
                skipped[reason] += 1
                continue
            by_name[shown(entry["name"])].append({
                "rom": rom, "name": entry["name"],
                **{k: entry[k] for k in ("qualifier", "translated") if entry.get(k)},
                "developer": entry.get("developer"), "releasedate": entry.get("releasedate")})
        groups += [{"system": system, "name": roms[0]["name"], "roms": roms}
                   for _, roms in sorted(by_name.items()) if len(roms) > 1]
    return {"groups": groups, "skipped": dict(sorted(skipped.items()))}


def main():
    usersettings.apply_settings()  # where storage is, as the CLI reads it
    if inventory.current() is None:
        sys.exit("No storage cache for the storage in use: run `sync-roms cache update` first.")
    metadata, stored = {}, set()
    for s in store.repo_json("systems"):
        name = s["bucket"]
        stored.update(k for k in inventory.files(f"{name}/", sizes=False) if not k.endswith("/"))
        try:
            metadata[name] = scrape_online.load_metadata(name)
        except ValueError as e:
            ui.warn(f"Skipping {name}: {e}")
    json.dump(find(metadata, stored, store.repo_json("clones")), sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
