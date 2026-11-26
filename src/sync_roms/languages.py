"""The regions and languages in a ROM's file name, as No-Intro and Redump write them: "Game (Japan) (En,Fr) [T-En by X]"."""
import posixpath
import re

from . import names

ARCADE = ("mame", "fbneo")

ENGLISH_REGIONS = {"USA", "World", "Europe", "UK", "United Kingdom", "Australia", "Canada"}
REGIONS = ENGLISH_REGIONS | {
    "Japan", "Korea", "Asia", "China", "Taiwan", "Hong Kong", "India", "Israel", "Turkey", "UAE", "Brazil", "Argentina",
    "Chile", "Mexico", "Latin America", "France", "Germany", "Spain", "Italy", "Netherlands", "Sweden", "Denmark",
    "Finland", "Norway", "Scandinavia", "Poland", "Portugal", "Russia", "Greece", "Ireland", "Switzerland", "Austria",
    "Belgium", "Croatia", "Czech", "Hungary", "New Zealand", "South Africa", "Ukraine", "Bulgaria", "Romania",
    "Serbia", "Slovakia", "Slovenia", "Estonia", "Latvia", "Lithuania", "Iceland", "Indonesia", "Thailand", "Vietnam",
    "Philippines", "Malaysia", "Singapore", "Egypt", "Saudi Arabia", "Peru", "Colombia", "Venezuela", "Uruguay",
    "Macao", "Unknown"}
LANGUAGE = re.compile(r"^[A-Z][a-z](-[A-Za-z]+)?$")

US = "\U0001F1FA\U0001F1F8"
LANGUAGE_FLAGS = {
    "Ja": "\U0001F1EF\U0001F1F5", "Fr": "\U0001F1EB\U0001F1F7", "De": "\U0001F1E9\U0001F1EA",
    "Es": "\U0001F1EA\U0001F1F8", "It": "\U0001F1EE\U0001F1F9", "Nl": "\U0001F1F3\U0001F1F1",
    "Pt": "\U0001F1F5\U0001F1F9", "Sv": "\U0001F1F8\U0001F1EA", "Da": "\U0001F1E9\U0001F1F0",
    "No": "\U0001F1F3\U0001F1F4", "Fi": "\U0001F1EB\U0001F1EE", "Pl": "\U0001F1F5\U0001F1F1",
    "Ru": "\U0001F1F7\U0001F1FA", "Ko": "\U0001F1F0\U0001F1F7", "Zh": "\U0001F1E8\U0001F1F3"}


def _flag(code):
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


REGION_FLAGS = {
    **{r: _flag(c) for r, c in {
        "Japan": "JP", "Korea": "KR", "China": "CN", "Taiwan": "TW", "Hong Kong": "HK", "India": "IN", "Israel": "IL",
        "Turkey": "TR", "UAE": "AE", "Brazil": "BR", "Argentina": "AR", "Chile": "CL", "Mexico": "MX", "France": "FR",
        "Germany": "DE", "Spain": "ES", "Italy": "IT", "Netherlands": "NL", "Sweden": "SE", "Denmark": "DK",
        "Finland": "FI", "Norway": "NO", "Poland": "PL", "Portugal": "PT", "Russia": "RU", "Greece": "GR",
        "Ireland": "IE", "Switzerland": "CH", "Austria": "AT", "Belgium": "BE", "Croatia": "HR", "Czech": "CZ",
        "Hungary": "HU", "New Zealand": "NZ", "South Africa": "ZA", "Ukraine": "UA", "Bulgaria": "BG",
        "Romania": "RO", "Serbia": "RS", "Slovakia": "SK", "Slovenia": "SI", "Estonia": "EE", "Latvia": "LV",
        "Lithuania": "LT", "Iceland": "IS", "Indonesia": "ID", "Thailand": "TH", "Vietnam": "VN",
        "Philippines": "PH", "Malaysia": "MY", "Singapore": "SG", "Egypt": "EG", "Saudi Arabia": "SA", "Peru": "PE",
        "Colombia": "CO", "Venezuela": "VE", "Uruguay": "UY", "Macao": "MO"}.items()},
    "Asia": "\U0001F30F", "Latin America": "\U0001F30E", "Scandinavia": _flag("SE")}


def paren_groups(name):
    """The comma-separated parts of each parenthesised group in name."""
    return [[p.strip() for p in g.split(",")] for g in re.findall(r"\(([^)]*)\)", name)]


def stem(key):
    """The name regions and languages are read from: an arcade set's scraped title, else the file name without extension."""
    if key.split("/", 1)[0] in ARCADE:
        return names.title(key)
    return posixpath.splitext(posixpath.basename(key))[0]


def _deciding(name):
    """(kind, parts) of the group that says what language the ROM is in, or None."""
    groups = paren_groups(name)
    for parts in groups:
        if all(LANGUAGE.match(p) for p in parts):
            return "language", parts
    for parts in groups:
        if all(p in REGIONS for p in parts):
            return "region", parts
    return None


def _translated(name):
    return bool(re.search(r"\[T-En", name, re.I))


def translated(key):
    """True when the ROM is a fan translation into English (its name has a `[T-En` tag)."""
    return _translated(stem(key))


def _english(name, found):
    if _translated(name):
        return True
    if not found:
        return None
    kind, parts = found
    if kind == "language":
        return any(p == "En" or p.startswith("En-") for p in parts)
    return bool(ENGLISH_REGIONS & set(parts))


def english(name):
    """True when the ROM is in English (a `[T-En` translation, an English language tag, else an English region), False
    when it isn't, None when the name says nothing."""
    return _english(name, _deciding(name))


def flag(key):
    """A flag emoji for the ROM's language: the US flag for English; else the first mapped flag of a region group with
    no English region (Brazil beats a `Pt` tag), else the first mapped one of the deciding group; or an empty string."""
    name = stem(key)
    found = _deciding(name)
    is_english = _english(name, found)
    if is_english is None:
        return ""
    if is_english:
        return US
    for parts in paren_groups(name):
        if all(p in REGIONS for p in parts) and not ENGLISH_REGIONS & set(parts):
            for p in parts:
                if p in REGION_FLAGS:
                    return REGION_FLAGS[p]
    kind, parts = found
    for p in parts:
        mapped = LANGUAGE_FLAGS.get(p.split("-")[0]) if kind == "language" else REGION_FLAGS.get(p)
        if mapped:
            return mapped
    return ""


def column(key):
    """The editors' flag column cell: (text, style)."""
    f = flag(key)
    return ("  " + f if f else "", "dim")
