"""Filter values from a system's scraped metadata.json ({ROM path in the system folder: {developer, publisher, genre,
releasedate, ...}}), for the card editor's game view.

Each field gives a game a set of values; an empty or "unknown" field gives none, and such a game never matches a filter
on that field:
- developer, publisher: the text, trimmed.
- genre: the first segment of the label before " / " ("Sports / Baseball" is "Sports").
- year: the first 4-digit year in releasedate ("1999", "1999-03-04" and "19990304" are all "1999").

Values are matched case-insensitively: "Capcom" and "capcom" are one value.
"""
import re

FIELDS = (("developer", "Developer"), ("publisher", "Publisher"), ("genre", "Genre"), ("year", "Year"))


def _text(value):
    text = value.strip() if isinstance(value, str) else ""
    return "" if text.lower() == "unknown" else text


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
    """Whether a game's {field: values} has every {field: value} of filters (AND across fields), ignoring case."""
    return all(value.casefold() in {v.casefold() for v in vals.get(field, ())} for field, value in filters.items())


def counts(idx, keys, field):
    """[(value, number of keys with it)] of one field over the given bucket keys: most common first, then by name;
    years in year order. Spellings that differ only by case are one value, shown as its most common spelling (the
    first seen on a tie)."""
    spellings = {}  # casefolded value -> {spelling: count}, in the order first seen
    for k in keys:
        for v in idx.get(k, {}).get(field, ()):
            seen = spellings.setdefault(v.casefold(), {})
            seen[v] = seen.get(v, 0) + 1
    tally = {max(seen, key=seen.get): sum(seen.values()) for seen in spellings.values()}
    if field == "year":
        return sorted(tally.items())
    return sorted(tally.items(), key=lambda kv: (-kv[1], kv[0].lower(), kv[0]))


def describe(filters):
    """The active filters for a title: "genre: Platform · year: 1999" (fields in FIELDS order)."""
    return " · ".join(f"{field}: {filters[field]}" for field, _ in FIELDS if field in filters)
