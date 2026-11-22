"""The user's own boot logos from the data folder's bootlogos/<resolution>/, copied into a spruce card's App/BootLogo/Imgs."""
import contextlib
import filecmp
import os
import shutil

from . import store, ui

FOLDER = "bootlogos"
IMGS = os.path.join("App", "BootLogo", "Imgs")
UNSUPPORTED = {"magicx-zero40"}  # spruce devices whose Boot Logo app can't run
CONFIRM = "Yes, flash "  # the app's confirm copy of a logo is Imgs/<CONFIRM><name>


def _wanted(resolution):
    folder = os.path.join(store.data_dir(), FOLDER, resolution)
    try:
        names = os.listdir(folder)
    except OSError:
        return {}
    return {n: os.path.join(folder, n) for n in sorted(names)
            if n.endswith((".png", ".bmp")) and CONFIRM[:-1] not in n and os.path.isfile(os.path.join(folder, n))}


def install(card, layout_name, device, base, dry_run, wrote=None, keep=False):
    """Copy the user's boot logos for the card's screen resolution into a spruce card's App/BootLogo/Imgs, and clean
    up the ones sync copied earlier that are gone from the data folder. The failure count. wrote, a list, gets the
    card paths copied. device: the card's device dict (None for Full). keep (--no-delete): leave stale ones. Imgs/ is
    never created and only recorded names are overwritten or removed (flashing is the user's step in Apps -> Boot
    Logo)."""
    device = device or {}  # None for a Full card
    resolution = device.get("resolution")
    if layout_name != "spruce" or not resolution or device.get("id") in UNSUPPORTED:
        return 0
    wanted = _wanted(resolution)
    saved = store.saved_card(card).get("boot_logos")
    saved = saved if isinstance(saved, list) else []
    recorded = [n for n in saved if isinstance(n, str) and n and n == os.path.basename(n)]  # plain file names only
    if not wanted and not saved:
        return 0
    imgs = os.path.join(base, IMGS)
    if not os.path.isdir(imgs):
        ui.warn(f"The card has no {IMGS.replace(os.sep, '/')}: install spruceOS first, then sync again to stage boot logos")
        return 0
    stale = [n for n in recorded if n not in wanted]

    def plan():
        """The wanted names to copy, and those already on the card (ours)."""
        own = {n.lower() for n in os.listdir(imgs)} - {n.lower() for n in recorded}  # spruce's own names
        todo, ours = [], set(recorded) & set(wanted)
        for name, source in wanted.items():
            target = os.path.join(imgs, name)
            if name not in recorded and name.lower() in own:
                ui.warn(f"Boot logo {name} is one of spruce's own names: skipping it")
            elif not (os.path.isfile(target) and filecmp.cmp(source, target, shallow=False)):
                todo.append(name)
            else:
                ours.add(name)
        return todo, ours
    if dry_run:
        todo = plan()[0]
        if todo or (stale and not keep):
            parts = ([f"copy {len(todo)} boot logo(s) to {IMGS.replace(os.sep, '/')}"] if todo else []) + \
                    ([f"remove {len(stale)} stale one(s)"] if stale and not keep else [])
            print(ui.dim(f"🧪 Dry run: would {' and '.join(parts)}"))
        return 0
    failures, copied, kept = 0, [], set()
    for name in stale:  # before the copies: on a case-insensitive card a stale K.png is the new k.png's slot
        if keep:
            kept.add(name)
            continue
        for gone in (name, CONFIRM + name):
            try:
                os.remove(os.path.join(imgs, gone))
            except FileNotFoundError:
                pass
            except OSError as e:
                ui.warn(f"Couldn't remove boot logo {gone}: {e}")
                failures += 1
                kept.add(name)
    todo, ours = plan()
    ours |= kept
    for name in todo:
        target = os.path.join(imgs, name)
        try:
            shutil.copyfile(wanted[name], target)
        except OSError as e:
            ui.warn(f"Couldn't copy boot logo {name}: {e}")
            failures += 1
            if name not in recorded:  # the target didn't exist before: don't leave a partial one
                with contextlib.suppress(OSError):
                    os.remove(target)
            continue
        copied.append(name)
        ours.add(name)
        if wrote is not None:
            wrote.append(target)
    if sorted(ours) != sorted(saved):
        store.update_card(card, boot_logos=sorted(ours))
    if copied:
        print(f"🖼️  {len(copied)} boot logo(s) {ui.green('→ ' + IMGS.replace(os.sep, '/'))} (run Apps → Boot Logo on the device)")
    return failures
