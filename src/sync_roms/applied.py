"""One setting `config apply` would write: where it lives, its key, the value now and the value to set."""
from collections import namedtuple

from . import ui

Entry = namedtuple("Entry", "where key old new secret")  # old is None when the key is missing


def changed(entry):
    return entry.old != entry.new


def _shown(entry, value):
    return "(hidden)" if entry.secret else value


def show(entries, dry_run):
    """Print the entries grouped by where, in order: every one in a dry run, only the changed ones otherwise."""
    groups = {}
    for entry in entries:
        groups.setdefault(entry.where, []).append(entry)
    for where, group in groups.items():
        if not dry_run:
            group = [e for e in group if changed(e)]
            if not group:
                continue
        print(ui.dim("🧪 Dry run: " + where) if dry_run else where)
        for e in group:
            new = _shown(e, e.new)
            if not dry_run:
                print(f"   {e.key} = {new}")
            elif changed(e):
                was = "missing" if e.old is None else "empty" if e.old == "" else _shown(e, e.old)
                print(f"   would set   {e.key} = {new} (was {was})")
            else:
                print(f"   already set {e.key} = {new}")
