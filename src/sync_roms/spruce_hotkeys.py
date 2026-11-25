"""Quit on hotkey + Start in a spruce card's RetroArch configs (Saves/ra-configs/retroarch-<platform>.cfg). The rest of the
hotkey scheme is spruceOS's default; the key and the Start value come from spruce's own platform script on the card."""
import glob
import os
import re

from . import applied, cardfs, spruce_syncthing, ui

ASSIGN = re.compile(r'^(RA_HOTKEY_LINE|RA_START_VAL)=["\']?([^"\'\r\n]*)["\']?\s*$')
SOURCE = re.compile(r"^\.\s+/mnt/SDCARD/(\S+)\s*$")


def _read_script(base, path, values, seen):
    if path in seen:
        return
    seen.add(path)
    for line in cardfs.read(path).decode("utf-8", "replace").splitlines():
        m = ASSIGN.match(line)
        if m:
            values[m.group(1)] = m.group(2)
            continue
        m = SOURCE.match(line)
        if m:
            sourced = os.path.join(base, *m.group(1).split("/"))
            if os.path.isfile(sourced):
                _read_script(base, sourced, values, seen)


def start_value(base, platform):
    """(quit key, Start value) from spruce's platform script for the platform, e.g. ("input_exit_emulator_btn", "6"); None when not found."""
    scripts = glob.glob(os.path.join(glob.escape(base), "spruce", "scripts", "platform", "*", glob.escape(platform) + ".cfg"))
    if not scripts:
        return None
    values = {}
    try:
        _read_script(base, sorted(scripts)[0], values, set())
    except OSError:
        return None
    if not values.get("RA_HOTKEY_LINE") or not values.get("RA_START_VAL"):
        return None
    return values["RA_HOTKEY_LINE"].replace("enable_hotkey", "exit_emulator"), values["RA_START_VAL"]


def _configs(base):
    return sorted(glob.glob(os.path.join(glob.escape(base), "Saves", "ra-configs", "retroarch-*.cfg")))


def _platform(path):
    return os.path.basename(path)[len("retroarch-"):-len(".cfg")]


def _value(text, key):
    m = spruce_syncthing._pattern(key).search(text)
    return m.group(0).split("=", 1)[1].strip().strip('"') if m else None


def _plan(base):
    """([(path, shown, key, old, new, text)], warnings): the cfgs a quit hotkey applies to."""
    paths = _configs(base)
    if not paths:
        return [], ["Saves/ra-configs has no retroarch-*.cfg yet; launch a game once on the device, then sync again for the quit hotkey"]
    plan, warnings = [], []
    for path in paths:
        shown = f"Saves/ra-configs/{os.path.basename(path)}"
        found = start_value(base, _platform(path))
        if not found:
            warnings.append(f"{shown}: spruce's Start button for {_platform(path)} wasn't found; quit left on its default")
            continue
        try:
            text = cardfs.read(path).decode("utf-8")  # raw: cardfs.text would turn CRLF into LF
        except (OSError, ValueError):
            warnings.append(f"{shown} can't be read; its quit hotkey left as it is")
            continue
        key, start = found
        if _value(text, key.replace("exit_emulator", "enable_hotkey")) == start:
            warnings.append(f"{shown}: the hotkey button is Start, so quit stays on spruce's default")
            continue
        plan.append((path, shown, key, _value(text, key), start, text))
    return plan, warnings


def entries(base):
    """[Entry] per RetroArch config: the quit key with its current value and the Start value."""
    plan, warnings = _plan(base)
    for w in warnings:
        ui.warn(w)
    return [applied.Entry(shown, key, old, new, False) for _, shown, key, old, new, _ in plan]


def _edit(text, key, value):
    line = f'{key} = "{value}"'
    pattern = spruce_syncthing._pattern(key)
    if pattern.search(text):
        return pattern.sub(lambda m: m.group(0) if m.group(0) == line or spruce_syncthing._same(m.group(0), value) else line, text)
    eol = "\r\n" if "\r\n" in text else "\n"
    return text + ("" if not text or text.endswith("\n") else eol) + line + eol


def install(card, layout_name, base, dry_run):
    """Set quit to hotkey + Start in each RetroArch config of a spruce card. The failure count."""
    if layout_name != "spruce":
        return 0
    plan, warnings = _plan(base)
    for w in warnings:
        ui.warn(w)
    changed = 0
    for path, shown, key, _, value, text in plan:
        new = _edit(text, key, value)
        if new == text:
            continue
        if not dry_run:
            try:
                cardfs.write_text(path, new)
            except OSError as e:
                ui.warn(f"{shown} can't be written: {e}")
                return 1
        changed += 1
    if changed:
        print(ui.dim(f"🧪 Would set the quit hotkey to hotkey + Start in {changed} RetroArch config(s)") if dry_run
              else f"🎮 Quit hotkey set to hotkey + Start in {changed} RetroArch config(s)")
    return 0
