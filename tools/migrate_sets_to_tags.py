#!/usr/bin/env python3
"""One-off: turn the game sets in storage into tags.json.

    tools/migrate_sets_to_tags.py [--write [--force]]

Every set becomes a tag (its id, name, description, art and current emoji); series and categories of the sets' games
become tags too, pruned by the rules below. A game's record is the union of the tags, files and variants from every
set that lists it. Without --write it only prints what it would do; --write puts tags.json in storage (refused when
it already holds games, unless --force). The set files are left untouched.
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from sync_roms import inventory, runtime, s3, shared, tags, themeart, ui, usersettings  # noqa: E402

SERIES_MIN = 15
NO_ART_EMOJI = "📦"  # a set's tag whose set had no art with an emoji

# Names that mean the same thing: name -> the tag name it merges into (a set's name or a kept name).
ALIAS = {"Super Mario": "Mario", "Zelda": "The Legend of Zelda", "Sonic": "Sonic the Hedgehog",
         "Tales": "Tales of", "Shin Megami Tensei & Persona": "Shin Megami Tensei",
         "Pokemon": "Pokemon", "Kirby": "Kirby", "Disney": "Disney",
         "Visual Novel": "Visual Novels", "Strategy RPG": "Tactical RPGs",
         "Platformer": "Platformers", "Puzzle": "Puzzle & Pick-Up-and-Play", "Racing": "Racing",
         "Kunio & Technos": "Kunio-kun", "Looney Tunes & Cartoons": "Looney Tunes",
         "Bemani": "Bemani", "Doom & id Tech": "Doom & id Tech"}
# Categories that are dropped: system names, qualifiers that only mean something inside their set, and the genres of
# the fan translations (genre suggestions cover them).
SYSTEM = {"3DS", "Famicom Disk System", "Master System", "Neo Geo Pocket", "Nintendo 64", "PC Engine / TG-16",
          "PC Engine CD", "PS Vita", "SG-1000", "Saturn", "WonderSwan"}
GENERIC = {"Other", "Other 16-bit", "Other 32-bit and Later", "Other 8-bit", "Other Sports", "Mainline", "Spin-offs",
           "Handheld", "Arcade", "Life", "Creative", "Combat", "Futuristic", "Military", "Extreme", "Nintendo", "Sony",
           "Golden Age", "Sci-Fi & Horror", "Brands & Mascots", "16-bit Mascots", "Kart & Mascot", "Top-down & RC",
           "Deception", "Card, Board & Sports"}
FT_GENRE = {"Action", "Action RPG", "Adventure", "Fighting & Brawler", "RPG", "Rhythm & Idol", "Shooter", "Simulation"}

# The emoji of the tags that don't come from a set, by tag name. Set tags keep their set's emoji.
EMOJI = {
    "Ace Attorney": "⚖️",
    "Action Dungeon Crawlers": "🪓",
    "Alchemy & Crafting": "⚗️",
    "Arc the Lad": "🦜",
    "Arcade Light Gun": "🎪",
    "Atari Collection": "📼",
    "Atari, Midway & Williams": "🪙",
    "Atelier": "🧪",
    "Band games": "🎸",
    "Baseball": "⚾",
    "Basketball": "🏀",
    "Batman": "🦇",
    "Bemani": "🎛️",
    "Bomberman": "💣",
    "Boxing & Wrestling": "🏋️",
    "Breath of Fire": "🐲",
    "Bubble Bobble": "🫧",
    "Cabal-Style": "🪖",
    "Call of Duty": "🎖️",
    "Capcom": "🅲",
    "Cave": "🐝",
    "Chrono": "⏳",
    "Cinematic Platformers": "🎬",
    "City & Tycoon": "🏙️",
    "Comics": "💭",
    "Console Light Gun": "📺",
    "Contra": "🦅",
    "Crash & Spyro": "🦊",
    "Dance Dance Revolution": "💃",
    "Detective & Mystery": "🕵️",
    "Digimon": "🦖",
    "Disney": "🐭",
    "Donkey Kong": "🍌",
    "Doom & id Tech": "👹",
    "Dragon Ball": "🟠",
    "Dragon Quest": "🧙",
    "Duke Nukem & Build Engine": "🕶️",
    "Dungeons & Dragons": "🧝",
    "Dynasty Warriors": "🏇",
    "Etrian Odyssey": "🧗",
    "FMV & CD-ROM Era": "💿",
    "FMV Shooters": "📽️",
    "Farming": "🚜",
    "Fire Emblem": "🦄",
    "Fire Pro Wrestling": "🏟️",
    "First-Person Dungeon RPGs": "🚪",
    "Football": "🏈",
    "Formula 1": "🏁",
    "Front Mission": "🦿",
    "God Games & Evolution": "🌍",
    "Golden Sun": "☀️",
    "Golf & Tennis": "⛳",
    "Gradius": "🛰️",
    "Grandia": "🪁",
    "Gundam": "🔩",
    "Halo": "🔰",
    "Harry Potter": "🪄",
    "Harvest Moon": "🐄",
    "Hockey": "🏒",
    "Hot Wheels": "🚙",
    "Hudson": "🐰",
    "Indiana Jones": "🏺",
    "Irem": "🚤",
    "James Bond 007": "🍸",
    "Japanese Adventure Classics": "🏮",
    "King of Fighters": "🥋",
    "Kingdom Hearts": "🔑",
    "Koei": "🏯",
    "Koei Historical": "📜",
    "Konami": "🟥",
    "Kunio-kun": "🤜",
    "LEGO": "🏗️",
    "Langrisser": "💍",
    "Lode Runner": "⛏️",
    "Looney Tunes": "🥕",
    "Lufia": "🌠",
    "Lunar": "🌛",
    "MLB": "🧢",
    "Mana": "🌿",
    "Marvel": "🦸",
    "Metal Gear": "🥫",
    "Monster Hunter": "🦴",
    "Mortal Kombat": "🩸",
    "Mother": "🌻",
    "Movies & TV": "🍿",
    "Mystery Dungeon": "🎴",
    "NBA": "⛹️",
    "NFL": "🏉",
    "NHL": "🥅",
    "Namco": "🔵",
    "Namco Museum": "🏛️",
    "Naruto": "🍥",
    "Nascar": "🛞",
    "Need for Speed": "🚓",
    "Neo Geo": "🔹",
    "Nintendo Wars": "🚁",
    "Nippon Ichi": "😈",
    "Nobunaga's Ambition": "🏹",
    "Ogre Battle & Final Fantasy Tactics": "🦁",
    "Olympic & Multi-event": "🥇",
    "Pac-Man": "🍒",
    "Phantasy Star": "🪐",
    "Pitfall": "🌴",
    "Pixar": "💡",
    "Point-and-Click": "🖱️",
    "Professor Layton": "🎩",
    "Psikyo": "🦋",
    "Puyo Puyo": "🟣",
    "ROM Hacks": "🔧",
    "Rail Shooters": "🚂",
    "Raizing": "🦂",
    "Rare & 007": "🕴️",
    "Rare & 3D Mascots": "🐻",
    "Rayman": "🙌",
    "Real-Time Strategy": "⚙️",
    "Roguelikes": "🎰",
    "Romance of the Three Kingdoms": "🐯",
    "SaGa": "🎼",
    "Sega": "🌀",
    "Sega Mascots": "🦔",
    "Shadow Hearts": "🖤",
    "Shin Megami Tensei": "👿",
    "Shining Force": "✨",
    "Sims": "🛋️",
    "Single-Screen": "🔲",
    "Soccer": "🦵",
    "Spider-Man": "🕷️",
    "Splinter Cell": "🌃",
    "Star Ocean": "🌟",
    "Suikoden": "🌊",
    "Super Robot Wars": "🧰",
    "Syphon Filter": "☣️",
    "Tactical RPGs": "♞",
    "Taiko": "🪘",
    "Taito": "🪀",
    "Tales of": "📕",
    "Teenage Mutant Ninja Turtles": "🍕",
    "Tenchu": "🌑",
    "Tetris": "🟧",
    "The Legend of Heroes": "🦉",
    "Toaplan": "🛩️",
    "Tom Clancy": "🪂",
    "Tony Hawk": "🛼",
    "Touhou": "⛩️",
    "Treasure": "🏴‍☠️",
    "Turn-Based Strategy": "🧮",
    "Turok": "🦕",
    "Virtual Pets & Monster Raising": "🐣",
    "Visual Novels": "💌",
    "Vocaloid & idol": "🎤",
    "WWE": "🏅",
    "Wario": "💰",
    "Western CRPGs": "🧌",
    "Wild Arms": "🌵",
    "Wizardry": "📿",
    "Worms": "🪱",
    "X-Men": "🧬",
    "Xeno": "🧿",
    "Ys": "🔴",
    "Zero Escape & Danganronpa": "🔪",
}


def _norm(name):
    name = re.sub(r"^the |^tales of$", lambda m: "tales" if "tales" in m.group() else "", name.lower())
    return re.sub(r"[^a-z0-9]+", "", name)


def build(sets, emoji=None):
    """(tags.json data, report) for the sets ({"id", "name", "description"?, "art"?, "games"} dicts).

    report is {"kept": [...], "pruned": [...], "merged": [...]} of {"type", "name", "games", "sets", "detail"} rows
    for the categories and series. A kept tag with no emoji, or sharing one, raises ValueError."""
    emoji = EMOJI if emoji is None else emoji
    cats, ser, catsets = collections.defaultdict(set), collections.defaultdict(set), collections.defaultdict(set)
    tag_defs = {}  # name -> {"id", "set", "games": {bucket}}
    for s in sets:
        tag_defs.setdefault(s["name"], {"id": s["id"], "set": s, "games": set()})["games"].update(g["bucket"] for g in s["games"])
        for g in s["games"]:
            if g.get("category"):
                cats[g["category"]].add(g["bucket"])
                catsets[g["category"]].add(s["id"])
            if g.get("series"):
                ser[g["series"]].add(g["bucket"])
    setnames = {_norm(n): n for n in tag_defs}

    def target(name):
        a = ALIAS.get(name, name)
        return setnames.get(_norm(a), a)

    def add(name, games):
        tag_defs.setdefault(name, {"id": tags.slug(name), "set": None, "games": set()})["games"].update(games)

    report = {"kept": [], "pruned": [], "merged": []}

    def row(fate, kind, name, n, where, detail):
        report[fate].append({"type": kind, "name": name, "games": n, "sets": where, "detail": detail})

    for c, g in sorted(cats.items()):
        where, n = ", ".join(sorted(catsets[c])), len(g)
        if c in SYSTEM:
            row("pruned", "category", c, n, where, "same as the system")
        elif c in GENERIC:
            row("pruned", "category", c, n, where, "only means something inside its set")
        elif c in FT_GENRE:
            row("pruned", "category", c, n, where, "fan-translation genre; genre suggestions cover it")
        else:
            t = target(c)
            if t != c or _norm(t) in setnames:
                row("merged", "category", c, n, where, t)
                add(t, g)
            else:
                row("kept", "category", c, n, where, "")
                add(c, g)
    catnorm = {_norm(k): k for k in tag_defs}
    for s, g in sorted(ser.items(), key=lambda x: (-len(x[1]), x[0])):
        n = len(g)
        hit = catnorm.get(_norm(target(s))) or catnorm.get(_norm(s))
        if hit:
            row("merged", "series", s, n, "", hit)
            tag_defs[hit]["games"].update(g)
        elif n >= SERIES_MIN:
            row("kept", "series", s, n, "", "")
            add(s, g)
        else:
            row("pruned", "series", s, n, "", f"fewer than {SERIES_MIN} games")

    data = {"tags": {}, "games": {}, "declined": {}}
    used = {}
    for name, t in tag_defs.items():
        s = t["set"]
        em = themeart.art_emoji(s.get("art") or s["id"], NO_ART_EMOJI) if s else emoji.get(name)
        if not em:
            raise ValueError(f"no emoji for the tag {name!r}")
        if em in used:
            raise ValueError(f"the tags {used[em]!r} and {name!r} share the emoji {em}")
        used[em] = name
        if t["id"] in data["tags"]:
            raise ValueError(f"two tags have the id {t['id']!r}")
        tag = {"name": name, "emoji": em}
        if s:
            if s.get("description"):
                tag["description"] = s["description"]
            if s.get("art"):
                tag["art"] = s["art"]
        data["tags"][t["id"]] = tag
        for bucket in t["games"]:
            data["games"].setdefault(bucket, {"tags": []})["tags"].append(t["id"])
    for rec in data["games"].values():
        rec["tags"] = sorted(set(rec["tags"]))
    for s in sets:
        for g in s["games"]:
            rec = data["games"][g["bucket"]]
            if g.get("files"):
                rec["files"] = rec.get("files", []) + [f for f in g["files"] if f not in rec.get("files", [])]
            for v in g.get("variants") or ():
                have = {x["bucket"]: x for x in rec.setdefault("variants", [])}
                if v["bucket"] not in have:
                    rec["variants"].append(dict(v))
                elif v.get("files"):
                    old = have[v["bucket"]]
                    old["files"] = old.get("files", []) + [f for f in v["files"] if f not in old.get("files", [])]
    return data, report


def read_sets():
    """The sets in storage's sets/ as {"id", "name", "description", "art"?, "games"} dicts, in file-name order."""
    out = []
    for key in sorted(inventory.files("sets/", sizes=False)):
        name = key[len("sets/"):]
        if "/" in name or name.startswith(".") or not name.endswith(".json"):
            continue
        try:
            data = json.loads(shared.read(key))
        except (UnicodeDecodeError, ValueError, *s3.ERRORS):
            data = None
        if not (isinstance(data, dict) and isinstance(data.get("games"), list)):
            print(f"skipped {key}: not a set")
            continue
        set_id = name[:-len(".json")]
        game_set = {"id": set_id, "name": data.get("name", set_id), "description": data.get("description", ""),
                    "games": data["games"]}
        if isinstance(data.get("art"), str):
            game_set["art"] = data["art"]
        out.append(game_set)
    return out


def report_text(data, report):
    lines = [f"{len(data['tags'])} tags, {len(data['games'])} games"]
    for fate in ("pruned", "merged", "kept"):
        counts = collections.Counter(r["type"] for r in report[fate])
        lines.append(f"{fate}: {counts['series']} series, {counts['category']} categories")
    for fate in ("pruned", "merged"):
        lines.append(f"\n{fate}:")
        lines += [f"  {r['type']:8} {r['name']} ({r['games']})" + (f" -> {r['detail']}" if fate == "merged" else f": {r['detail']}")
                  for r in report[fate]]
    return "\n".join(lines)


def tag_list(data):
    count = collections.Counter(i for rec in data["games"].values() for i in rec["tags"])
    return "\n".join(f"{t['emoji']}  {t['name']} ({count[i]})  [{i}]"
                     for i, t in sorted(data["tags"].items(), key=lambda x: x[1]["name"].casefold()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--write", action="store_true", help="write tags.json to storage (default: only print)")
    parser.add_argument("--force", action="store_true", help="write even when tags.json already has games")
    args = parser.parse_args(argv)
    usersettings.apply_settings()
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):  # an unmounted share, not an empty storage
        ui.fail(f"{runtime.ROOT} is missing", 1)
    try:
        data, report = build(read_sets())
    except (ValueError, *s3.ERRORS) as e:
        ui.fail(str(e), 1)
    print(report_text(data, report))
    print("\nTags:\n" + tag_list(data))
    if not args.write:
        print("\nDry run: nothing written. Run again with --write to put tags.json in storage.")
        return 0
    try:
        def change(old):
            if old["games"] and not args.force:
                raise ValueError("tags.json already has games; --force replaces it")
            return data

        try:
            shared.update(tags.KEY, tags.parse, {"tags": {}, "games": {}, "declined": {}}, change, tags.dump)
        finally:
            inventory.flush()
    except (*s3.ERRORS, ValueError) as e:
        ui.fail(str(e), 1)
    print("tags.json written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
