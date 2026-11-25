import json, os, re, collections, sys
D = "/Volumes/roms/sets"
SERIES_MIN = 15
sets, cats, ser = {}, collections.defaultdict(set), collections.defaultdict(set)
catsets = collections.defaultdict(set)
for f in sorted(os.listdir(D)):
    if not f.endswith(".json"): continue
    s = json.load(open(os.path.join(D, f))); sid = f[:-5]
    sets[sid] = {"name": s["name"], "games": {g["bucket"] for g in s["games"]}}
    for g in s["games"]:
        if g.get("category"): cats[g["category"]].add(g["bucket"]); catsets[g["category"]].add(sid)
        if g.get("series"): ser[g["series"]].add(g["bucket"])

def norm(n): return re.sub(r"[^a-z0-9]+", "", re.sub(r"^the |^tales of$", lambda m: "tales" if "tales" in m.group() else "", n.lower()))

# hand aliases: name -> tag name it merges into (set names or kept names)
ALIAS = {"Super Mario": "Mario", "Zelda": "The Legend of Zelda", "Sonic": "Sonic the Hedgehog",
         "Tales": "Tales of", "Shin Megami Tensei & Persona": "Shin Megami Tensei",
         "Pokemon": "Pokemon", "Kirby": "Kirby", "Disney": "Disney",
         "Visual Novel": "Visual Novels", "Strategy RPG": "Tactical RPGs",
         "Platformer": "Platformers", "Puzzle": "Puzzle & Pick-Up-and-Play", "Racing": "Racing",
         "Kunio & Technos": "Kunio-kun", "Looney Tunes & Cartoons": "Looney Tunes",
         "Bemani": "Bemani", "Doom & id Tech": "Doom & id Tech"}
SYSTEM = {"3DS", "Famicom Disk System", "Master System", "Neo Geo Pocket", "Nintendo 64", "PC Engine / TG-16",
          "PC Engine CD", "PS Vita", "SG-1000", "Saturn", "WonderSwan"}
GENERIC = {"Other", "Other 16-bit", "Other 32-bit and Later", "Other 8-bit", "Other Sports", "Mainline", "Spin-offs",
           "Handheld", "Arcade", "Life", "Creative", "Combat", "Futuristic", "Military", "Extreme", "Nintendo", "Sony",
           "Golden Age", "Sci-Fi & Horror", "Brands & Mascots", "16-bit Mascots", "Kart & Mascot", "Top-down & RC",
           "Deception", "Card, Board & Sports"}
FT_GENRE = {"Action", "Action RPG", "Adventure", "Fighting & Brawler", "RPG", "Rhythm & Idol", "Shooter", "Simulation"}

tags = {}  # name -> {"kind", "games", "from": [...]}
def add(name, kind, games, src):
    t = tags.setdefault(name, {"kind": kind, "games": set(), "from": []})
    t["games"] |= games; t["from"].append(src)
for sid, s in sets.items(): add(s["name"], "set", s["games"], f"set {sid}")
setnames = {norm(s["name"]): s["name"] for s in sets.values()}

rows = []  # every source name with its fate
def target(name):
    a = ALIAS.get(name, name)
    return setnames.get(norm(a), a)

for c, g in sorted(cats.items()):
    where = ", ".join(sorted(catsets[c])); n = len(g)
    if c in SYSTEM: rows.append(("category", c, n, where, "prune", "same as the system")); continue
    if c in GENERIC: rows.append(("category", c, n, where, "prune", "only means something inside its set")); continue
    if c in FT_GENRE: rows.append(("category", c, n, where, "prune", "fan-translation genre; genre suggestions cover it")); continue
    t = target(c)
    if t != c or norm(t) in setnames:
        rows.append(("category", c, n, where, "merge", t)); add(t, "set" if norm(t) in setnames else "category", g, f"category {c}")
    else:
        rows.append(("category", c, n, where, "keep", "")); add(c, "category", g, f"category {c}")
catnorm = {norm(k): k for k in tags}
for s, g in sorted(ser.items(), key=lambda x: (-len(x[1]), x[0])):
    n = len(g); t = target(s)
    hit = catnorm.get(norm(t)) or catnorm.get(norm(s))
    if hit:
        rows.append(("series", s, n, "", "merge", hit)); add(hit, tags[hit]["kind"], g, f"series {s}")
    elif n >= SERIES_MIN:
        rows.append(("series", s, n, "", "keep", "")); add(s, "series", g, f"series {s}")
    else:
        rows.append(("series", s, n, "", "prune", f"fewer than {SERIES_MIN} games"))
out = {"series_min": SERIES_MIN,
       "tags": sorted(({"name": k, "kind": v["kind"], "games": len(v["games"]), "from": v["from"]} for k, v in tags.items()), key=lambda x: x["name"].lower()),
       "rows": [dict(zip(("type", "name", "games", "sets", "fate", "detail"), r)) for r in rows]}
json.dump(out, open(sys.argv[1], "w"), indent=1)
c = collections.Counter((r[0], r[4]) for r in rows); print(c, "tags", len(tags))
