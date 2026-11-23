"""`config apply [CARD]`: apply the saved settings to a mounted spruce card, or over adb to an Android device."""
import os

from . import adb, android, android_settings, applied, picker, spruce_settings, spruce_syncthing, spruce_wifi, store, ui


VOLUMES = "/Volumes"


def _mounted(card, cards):
    """The mounted folder and card name for CARD (a folder, or a saved card's name found at /Volumes), else the current folder."""
    if card and not os.path.isdir(os.path.expanduser(card)) and os.sep not in card:
        base = os.path.join(VOLUMES, card)
    else:
        base = os.path.abspath(os.path.expanduser(card or os.getcwd()))
    return base, os.path.basename(base)


def _spruce(base, name, card, dry_run):
    if dry_run:
        applied.show(spruce_settings.entries(card, base) + spruce_wifi.entries(base) + spruce_syncthing.entries(card, base), True)
        return 0
    failed = spruce_settings.install(name, "spruce", base, False)
    failed += spruce_wifi.install(name, "spruce", base, False)
    failed += spruce_syncthing.run(name, "spruce", base, False)
    return failed


def run(card_arg, dry_run):
    cards = store.load_cards()
    if card_arg and (os.path.isdir(os.path.expanduser(card_arg)) or not android.is_android(store.saved_card(card_arg, cards))) or \
            not card_arg and os.path.basename(os.getcwd()) in cards:
        base, name = _mounted(card_arg, cards)
        saved = store.saved_card(name, cards)
        if not saved:
            ui.fail(f"No card named {name!r}. Set it up with `sync-roms cards new {name} --device ID|full --layout NAME`", 2)
        if android.is_android(saved):
            ui.fail(f"Android cards are applied over adb: run `sync-roms config apply {name}` without a folder", 2)
        layout = saved.get("layout")
        if layout != "spruce":
            ui.fail(f"config apply supports spruce cards and Android devices, not {layout}", 2)
        if not os.path.isdir(base):
            ui.fail(f"No folder {base}: give the card's mounted folder, e.g. `sync-roms config apply /Volumes/{name}`", 2)
        return 1 if _spruce(base, name, name, dry_run) else 0
    if not ui.has_terminal():
        ui.fail("`config apply` needs a terminal to pick the device from", 2)
    catalog = store.load_catalog()
    if not card_arg:
        adb.require(mounted=True)
    try:
        target = android.resolve(card_arg, cards, catalog["layouts"]["esde"]["roms_dir"])
        setup = picker.saved_setup(cards[target.card], catalog["devices"], catalog["layouts"], target.card)
        if not setup:
            ui.fail(f"{target.card!r} has no usable layout. Set it with `sync-roms cards set {target.card} --layout NAME`", 2)
        return android_settings.apply(target, catalog["layouts"][setup[1]], catalog["systems"], dry_run)
    except adb.AdbError as e:
        ui.fail(f"Lost the connection to the device: {e}", 1)
