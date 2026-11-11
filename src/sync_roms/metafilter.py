"""Filter values from a system's scraped metadata.json ({ROM path in the system folder: {developer, publisher, genre,
players, releasedate, ...}}), for the card editor's game view.

Each field gives a game a set of values; an empty or "unknown" field gives none, and such a game never matches a filter
on that field:
- developer, publisher: the text, trimmed.
- genre: the first segment of the label before " / " ("Sports / Baseball" is "Sports").
- players: the groups its count or range overlaps, of "1 player", "2 players", "3-4 players" and "5+ players"
  ("1-2" is both "1 player" and "2 players"; "2+" is every group from 2 up).
- year: the first 4-digit year in releasedate ("1999", "1999-03-04" and "19990304" are all "1999").
"""
import re

FIELDS = (("developer", "Developer"), ("publisher", "Publisher"), ("genre", "Genre"), ("players", "Players"),
          ("year", "Year"))
PLAYER_GROUPS = ((1, 1, "1 player"), (2, 2, "2 players"), (3, 4, "3-4 players"), (5, float("inf"), "5+ players"))


def _text(value):
    text = value.strip() if isinstance(value, str) else ""
    return "" if text.lower() == "unknown" else text


def players(text):
    """The player groups a players string ("1", "1-2", "2+", "1-4") overlaps, or () when it has no number."""
    nums = [int(n) for n in re.findall(r"\d+", text)]
    if not nums:
        return ()
    lo, hi = min(nums), (float("inf") if text.rstrip().endswith("+") else max(nums))
    return tuple(name for a, b, name in PLAYER_GROUPS if a <= hi and lo <= b)


def values(entry):
    """{field: set of values} for one metadata.json entry (fields without a value are left out)."""
    if not isinstance(entry, dict):
        return {}
    out = {}
    for field in ("developer", "publisher"):
        if _text(entry.get(field)):
            out[field] = {_text(entry[field])}
    genre = _text(entry.get("genre")).split(" / ")[0].strip()
    if genre:
        out["genre"] = {genre}
    groups = players(_text(entry.get("players")))
    if groups:
        out["players"] = set(groups)
    year = re.search(r"(?<!\d)\d{4}", _text(entry.get("releasedate")))
    if year:
        out["year"] = {year.group()}
    return out


def index(metadata, bucket):
    """{bucket key ("<bucket>/<ROM path>"): {field: values}} for a parsed metadata.json; None if it isn't an object."""
    if not isinstance(metadata, dict):
        return None
    return {f"{bucket}/{path}": values(entry) for path, entry in metadata.items()}


def matches(vals, filters):
    """Whether a game's {field: values} has every {field: value} of filters (AND across fields)."""
    return all(value in vals.get(field, ()) for field, value in filters.items())


def counts(idx, keys, field):
    """[(value, number of keys with it)] of one field over the given bucket keys: most common first, then by name;
    years in year order."""
    tally = {}
    for k in keys:
        for v in idx.get(k, {}).get(field, ()):
            tally[v] = tally.get(v, 0) + 1
    if field == "year":
        return sorted(tally.items())
    return sorted(tally.items(), key=lambda kv: (-kv[1], kv[0].lower(), kv[0]))


def describe(filters):
    """The active filters for a title: "genre: Platform · year: 1999" (fields in FIELDS order)."""
    return " · ".join(f"{field}: {filters[field]}" for field, _ in FIELDS if field in filters)
