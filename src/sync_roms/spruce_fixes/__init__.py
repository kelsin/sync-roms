"""Temporary fixes for bugs in spruceOS's Art Book themes (PyUI-Themes), applied to `spruce` cards on every sync.

A fix is a module here with `ID` (a key of data/spruce-fixes.json, which holds its `title` and `upstream` PR URL) and `plan(base)`, which returns
`(writes, skip)`: `writes` is `[(path, bytes)]` to write on the card; with none, `skip` says why: `ABSENT` (the theme
isn't on the card) or a short reason the theme is already right. To add a fix, write its module and list it in FIXES and add it to spruce-fixes.json;
to remove one, delete its module, its list entry, its json entry, its test and its data. `pyui` finds PyUI's resized
copies of a theme (`icons_<W>x<H>/`, `bg_<W>x<H>/`), which the fixes patch too."""
import os

from . import fds, pokemini, pyui
from .. import cardfs, store, ui

ABSENT = None
FIXES = (pokemini, fds)


def run(layout_name, base, dry_run):
    """Print one line per fix and write what each plans (nothing with dry_run). Returns the number of files written,
    or, with dry_run, that would be."""
    if layout_name != "spruce":
        return 0
    info = store.repo_json("spruce-fixes")
    print(ui.bold("🎨 Spruce theme fixes"))
    total = 0
    for fix in FIXES:
        title, url = info[fix.ID]["title"], info[fix.ID]["upstream"]
        writes, skip = fix.plan(base)
        if writes:
            if not dry_run:
                for path, data in writes:
                    cardfs.write_bytes(path, data)
            verb = "would apply to" if dry_run else "applied to"
            print(ui.green(f"   ✅ {title}: {verb} {len(writes)} file(s) ({url})"))
            total += len(writes)
            sizes = {f"{m[2]}x{m[3]}" for path, _ in writes for m in map(pyui.VARIANT.match,
                     os.path.relpath(path, base).split(os.sep)) if m}
            for size in sorted(sizes):
                print(ui.dim(f"      ↳ Fixing {size} theme variation"))
        elif skip is ABSENT:
            print(ui.dim(f"   ⏭️  {title}: skipped, the theme isn't on the card ({url})"))
        else:
            print(ui.dim(f"   ⏭️  {title}: skipped, {skip} ({url}); remove this fix once every card shows this"))
    return total
