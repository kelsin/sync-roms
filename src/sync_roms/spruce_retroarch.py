"""The RetroArch preferences of data/retroarch.json, set in each Saves/ra-configs/retroarch-*.cfg of a spruce card (always, not only with Syncthing)."""
import os

from . import applied, cardfs, spruce_hotkeys, store, ui


def settings():
    return store.repo_json("retroarch")["settings"]


def _texts(base):
    """[(path, shown, text)] for each readable RetroArch config; unreadable ones warn."""
    result = []
    for path in spruce_hotkeys._configs(base):
        shown = f"Saves/ra-configs/{os.path.basename(path)}"
        try:
            result.append((path, shown, cardfs.raw_text(path)))  # raw: cardfs.text would turn CRLF into LF
        except (OSError, ValueError):
            ui.warn(f"{shown} can't be read; its RetroArch settings left as they are")
    return result


def entries(base):
    """[Entry] for every RetroArch setting in each config, changed or not."""
    return [applied.Entry(shown, key, spruce_hotkeys._value(text, key), value, False)
            for _, shown, text in _texts(base) for key, value in settings().items()]


def install(card, layout_name, base, dry_run):
    """Set the RetroArch preferences in each RetroArch config of a spruce card, other lines kept. The failure count."""
    if layout_name != "spruce":
        return 0
    changed = failures = 0
    for path, shown, text in _texts(base):
        new = text
        for key, value in settings().items():
            new = spruce_hotkeys._edit(new, key, value)
        if new == text:
            continue
        if not dry_run:
            try:
                cardfs.write_text(path, new)
            except OSError as e:
                ui.warn(f"{shown} can't be written: {e}")
                failures += 1
                continue
        changed += 1
    if changed:
        print(ui.dim(f"🧪 Would set RetroArch's save state and netplay settings in {changed} RetroArch config(s)") if dry_run
              else f"🕹️  RetroArch's save state and netplay settings set in {changed} RetroArch config(s)")
    return failures
