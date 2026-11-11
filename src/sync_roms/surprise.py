"""Surprise: a few random full English games per system, rotated on a schedule."""
import datetime
import json
import os
import posixpath
import random
import re

from . import m3u, mirroring, picker, s3, store, ui, usersettings

SLOTS = 10
RECOMMENDED_SHARE = 2 / 3
DEFAULT_TTL_DAYS = 183
COLLECTION = "Surprise"

ENGLISH_REGIONS = {"USA", "World", "Europe", "UK", "United Kingdom", "Australia", "Canada"}
REGIONS = ENGLISH_REGIONS | {
    "Japan", "Korea", "Asia", "China", "Taiwan", "Hong Kong", "India", "Israel", "Turkey", "UAE", "Brazil", "Argentina",
    "Chile", "Mexico", "Latin America", "France", "Germany", "Spain", "Italy", "Netherlands", "Sweden", "Denmark",
    "Finland", "Norway", "Scandinavia", "Poland", "Portugal", "Russia", "Greece", "Ireland", "Switzerland", "Austria",
    "Belgium", "Croatia", "Czech", "Hungary", "New Zealand", "South Africa", "Ukraine", "Bulgaria", "Romania",
    "Serbia", "Slovakia", "Slovenia", "Estonia", "Latvia", "Lithuania", "Iceland", "Indonesia", "Thailand", "Vietnam",
    "Philippines", "Malaysia", "Singapore", "Egypt", "Saudi Arabia", "Peru", "Colombia", "Venezuela", "Uruguay",
    "Macao", "Unknown"}
NOT_FULL = ("Proto", "Beta", "Demo", "Sample", "Kiosk", "Pirate", "Hack", "Unl")
RERELEASE = ("Virtual Console", "Switch Online", "Classic Mini", "Mini Mix", "Mega Drive Mini", "Genesis Mini",
             "Collection", "Anthology", "Archives", "Sega Ages", "Sega Channel", "Evercade", "Steam", "GOG",
             "Retro-Bit", "Limited Run", "e-Reader", "QUByte Classics")
LANGUAGE = re.compile(r"^[A-Z][a-z](-[A-Za-z]+)?$")


LABEL = "\U0001F381 Surprise"


def enabled(entry):
    """Whether Surprise is on for a card's cards.json entry (on unless 'surprise' is false)."""
    return not (isinstance(entry, dict) and entry.get("surprise") is False)


def ttl_days():
    """Days before a surprise may come around again: the surprise_ttl_days setting, default 183."""
    days = usersettings.load_settings().get("surprise_ttl_days")
    return days if isinstance(days, int) and not isinstance(days, bool) and days >= 0 else DEFAULT_TTL_DAYS


def _history_path():
    return os.path.join(store.data_dir(), "surprises.json")


def _read_history():
    """(entries, readable): readable is False when the file exists but isn't a JSON list."""
    try:
        with open(_history_path()) as f:
            data = json.load(f)
    except OSError:
        return [], True
    except ValueError:
        return [], False
    return (data, True) if isinstance(data, list) else ([], False)


def load_history():
    """Past surprises, [{"system", "bucket", "title", "card", "date"}]; empty when the file is missing or unreadable."""
    entries, readable = _read_history()
    if not readable and "surprises" not in store._warned:
        store._warned.add("surprises")
        ui.warn("surprises.json isn't a valid JSON list; ignoring it and leaving it untouched")
    return entries


def _date(entry):
    try:
        return datetime.date.fromisoformat(entry["date"])
    except (KeyError, TypeError, ValueError):
        return None


def recent(history, today, ttl):
    """Bucket keys surprised within the last ttl days."""
    return {e["bucket"] for e in history
            if isinstance(e, dict) and isinstance(e.get("bucket"), str)
            and (d := _date(e)) is not None and (today - d).days <= ttl}


def save_history(entries, today):
    """Write entries to surprises.json, dropping ones past the TTL or with a bad date. An unreadable file is left alone."""
    if not _read_history()[1]:
        ui.warn(f"Not saving: {_history_path()} isn't valid JSON and would be overwritten. Fix or move it first.")
        return
    ttl = ttl_days()
    kept = [e for e in entries if (d := _date(e)) is not None and (today - d).days <= ttl]
    try:
        os.makedirs(store.data_dir(), exist_ok=True)
        store.write_json(_history_path(), kept, **store.PRETTY)
    except OSError as e:
        ui.warn(f"Couldn't save the surprise history: {e}")


def past_keys(bucket):
    """Recently surprised bucket keys under a system's folder."""
    return {k for k in recent(load_history(), datetime.date.today(), ttl_days()) if k.startswith(bucket + "/")}


def _paren_groups(name):
    return [[p.strip() for p in g.split(",")] for g in re.findall(r"\(([^)]*)\)", name)]


def _english(name):
    groups = _paren_groups(name)
    for parts in groups:
        if all(LANGUAGE.match(p) for p in parts):
            return any(p == "En" or p.startswith("En-") for p in parts)
    for parts in groups:
        if all(p in REGIONS for p in parts):
            return bool(ENGLISH_REGIONS & set(parts))
    return True


def is_candidate(key, system, family, bios):
    """Whether the bucket key is a full English game: no BIOS, prototype, beta, demo, hack, re-release or compilation."""
    base = posixpath.basename(key)
    stem = posixpath.splitext(base)[0]
    if base in bios or "[BIOS]" in base:
        return False
    if family is not None:
        title = family["parents"].get(stem)
        return title is not None and not any(parts[0].split()[:1] == ["Japan"] for parts in _paren_groups(title))
    if re.search(r"\[[bh][^\]]*\]", stem, re.I):
        return False
    groups = _paren_groups(stem)
    if any(p.startswith(NOT_FULL) for parts in groups for p in parts):
        return False
    if any(t in g for g in re.findall(r"\(([^)]*)\)", stem) for t in RERELEASE):
        return False
    return _english(stem)


def units(system, keys, family, bios):
    """The candidate games among keys, each a list of its keys (a multi-disc game's playlist first, then its discs)."""
    keys = sorted(k for k in keys if not k.endswith("/"))
    groups = m3u.file_groups(keys)
    out, seen = [], set()
    for k in keys:
        unit = groups.get(k, [k])
        if tuple(unit) not in seen:
            seen.add(tuple(unit))
            if is_candidate(unit[0], system, family, bios):
                out.append(unit)
    return out


def _surprise(system, unit):
    out = {"system": system, "bucket": unit[0], "title": store.key_title(unit[0])}
    if unit[1:]:
        out["files"] = unit[1:]
    return out


def pick(pools, kept, need, recommended, recent, others_current, rng):
    """Up to need new surprises from pools ({system bucket: [units]}): about two thirds (kept ones counted) from the
    recommended systems, spread evenly, slots passing on when a system runs out. Unused games come first, then ones
    surprised before (recent), then ones another card currently holds."""
    left = {b: list(u) for b, u in pools.items()}
    groups = {g: [b for b in sorted(left) if (b in recommended) == g] for g in (True, False)}
    for g in groups.values():
        rng.shuffle(g)
    kept_rec = sum(1 for k in kept if k["system"] in recommended)
    want_rec = min(max(round(SLOTS * RECOMMENDED_SHARE) - kept_rec, 0), need)
    out = []

    def tier(unit):
        return 2 if unit[0] in others_current else 1 if unit[0] in recent else 0

    given = dict.fromkeys(left, 0)
    for k in kept:
        if k["system"] in given:
            given[k["system"]] += 1

    def fill(group, slots):
        """Give each slot to the group's system with the fewest picks that still has games, so systems that run out
        pass their slots on and the rest stay even. Returns the unused slots."""
        while slots > 0:
            open_ = [b for b in groups[group] if left[b]]
            if not open_:
                break
            b = min(open_, key=given.__getitem__)
            best = min(map(tier, left[b]))
            unit = rng.choice([u for u in left[b] if tier(u) == best])
            left[b].remove(unit)
            given[b] += 1
            out.append(_surprise(b, unit))
            slots -= 1
        return slots

    rest = fill(False, need - want_rec + fill(True, want_rec))
    fill(True, rest)
    return out


def _pools(chosen_systems, taken):
    """{system bucket: [units]} of the candidates in storage for the run's systems, past the mirror. Full systems are
    left out (they sync everything already), and so is every unit sharing a key with taken. None when storage
    couldn't be listed."""
    with mirroring.storage_reads():
        try:
            folders = s3.list_folders()
        except (*s3.ERRORS, SystemExit) as e:
            ui.warn(f"Couldn't list storage for surprises, keeping the current ones: {e}")
            return None
        clones = store.repo_json("clones")
        pools = {}
        for s in chosen_systems:
            bucket = s["bucket"]
            if bucket not in folders or s.get("full_system"):
                continue
            try:
                keys = s3.list_sizes(f"{bucket}/", sizes=False)
            except s3.ERRORS as e:
                ui.warn(f"Couldn't list {bucket} for surprises: {e}")
                continue
            found = units(s, keys, clones.get(bucket), set(s["bios"]["files"]))
            pools[bucket] = [u for u in found if not taken.intersection(u)]
    return pools


def run_surprise(card_name, setup, chosen_systems, interactive, dry_run, rng=None, today=None):
    """The sync step: replace some or all of a card's surprises (asking which when interactive), fill the empty slots,
    save the card and the history, then open the card editor when interactive. A dry run changes nothing and only
    previews the empty slots; when storage can't be listed nothing is replaced or saved. Returns the card's surprises
    after the step (on a dry run, the saved ones)."""
    rng = rng or random.Random()
    today = today or datetime.date.today()
    cards = store.load_cards()
    entry = cards.get(card_name)
    entry = entry if isinstance(entry, dict) else {}
    if not enabled(entry):
        if entry.get("surprises") and not dry_run:
            entry.pop("surprises")
            store.write_cards(cards)
        return []
    names = {s["bucket"]: s["name"] for s in chosen_systems}
    saved = entry.get("surprises")
    current = [x for x in (saved if isinstance(saved, list) else ())
               if isinstance(x, dict) and x.get("system") in names and isinstance(x.get("bucket"), str)]
    if dry_run:
        kept = current
        if current:
            print("\U0001F381 would ask which surprises to replace" if interactive
                  else f"\U0001F381 would replace all {len(current)} surprises")
    elif interactive and current:
        states = picker.filter_list("Pick the surprises to replace",
                                    [f"{x.get('title') or x['bucket']}  ({names[x['system']]})" for x in current],
                                    multi=True, initial=[False] * len(current))
        kept = current if states is None else [x for x, replace in zip(current, states) if not replace]
    else:
        kept = []
    need = max(SLOTS - len(kept), 0)
    new, pools = [], {}
    if need:
        taken = {g["bucket"] for s in chosen_systems for g in s.get("games", ()) if g.get("bucket")}
        taken |= {k for x in kept for k in [x["bucket"]] + list(x.get("files", ()))}
        recommended = store.recommended_systems(setup[0], store.repo_json("systems")) if setup[0] else set()
        others_current = {x.get("bucket") for name, other in cards.items() if name != card_name and isinstance(other, dict)
                          and enabled(other) and isinstance(other.get("surprises"), list)
                          for x in other["surprises"] if isinstance(x, dict)}
        pools = _pools(chosen_systems, taken)
        new = pick(pools or {}, kept, need, recommended, recent(load_history(), today, ttl_days()),
                   others_current, rng)
    if new:
        print(f"\U0001F381 Surprise: {len(new)} new pick(s)" + (ui.dim(" (dry run: not saved)") if dry_run else ""))
        for x in new:
            print(f"  {x['title']}  {ui.dim(names[x['system']])}")
    if dry_run:
        return current
    if pools is None:  # storage couldn't be listed: replace nothing
        result = current
    else:
        result = kept + new
        store.update_card(card_name, surprises=result)
        save_history(load_history() + [{"system": x["system"], "bucket": x["bucket"], "title": x["title"],
                                        "card": card_name, "date": today.isoformat()} for x in new], today)
    if interactive:
        from . import cardedit  # cardedit imports much of the package
        cardedit.edit_card(card_name, setup)
    return result
