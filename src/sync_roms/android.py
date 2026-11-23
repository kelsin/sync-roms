"""An Android device over adb: its SD card, RetroArch and RetroArch's save folders."""
import time
from collections import namedtuple

from . import adb, picker, store, ui

Folders = namedtuple("Folders", "saves states sort_saves sort_states")
Target = namedtuple("Target", "serial model volume card")

DEFAULT_SAVES = "/storage/emulated/0/RetroArch/saves"
DEFAULT_STATES = "/storage/emulated/0/RetroArch/states"
NOT_SUPPORTED = (
    ("savefiles_in_content_dir", "Save files in the content folder"),
    ("savestates_in_content_dir", "Save states in the content folder"),
    ("sort_savefiles_by_content_enable", "Sort save files into folders by content directory"),
    ("sort_savestates_by_content_enable", "Sort save states into folders by content directory"),
)


def is_android(entry):
    return entry.get("layout") == "esde" and entry.get("device") != "windows-pc"


def card_volumes(serial, roms_dir):
    """The ids of the SD cards and USB drives that hold the ROM folder."""
    ids = [i for i in adb.shell(serial, "ls", "/storage").split() if i not in ("emulated", "self")]
    return [i for i in ids if adb.shell_ok(serial, "test", "-d", f"/storage/{i}/{roms_dir}")]


def retroarch_package(serial):
    out = adb.shell(serial, "pm", "list", "packages")
    pkgs = [line[8:].strip() for line in out.splitlines() if line.startswith("package:com.retroarch")]
    if not pkgs:
        model = next((d.model for d in adb.devices() if d.serial == serial and d.model), serial)
        ui.fail(f"No RetroArch installed on {model}", 2)
    if len(pkgs) == 1:
        return pkgs[0]
    pick = picker.filter_list("🕹️  Which RetroArch?", pkgs)
    if pick is None:
        raise SystemExit(0)
    return pkgs[pick]


def parse_config(text):
    out = {}
    for line in text.splitlines():
        key, eq, value = line.partition("=")
        if eq:
            out[key.strip()] = value.strip().strip('"')
    return out


def ra_folders(cfg):
    for key, label in NOT_SUPPORTED:
        if cfg.get(key) == "true":
            ui.fail(f"RetroArch's \"{label}\" ({key}) is on: turn it off in RetroArch's settings", 2)

    def folder(key, default):
        value = cfg.get(key, "")
        return default if value in ("", "default") else value.rstrip("/")
    return Folders(folder("savefile_directory", DEFAULT_SAVES), folder("savestate_directory", DEFAULT_STATES),
                   cfg.get("sort_savefiles_enable") == "true", cfg.get("sort_savestates_enable") == "true")


def read_folders(serial, pkg):
    path = f"/storage/emulated/0/Android/data/{pkg}/files/retroarch.cfg"
    try:
        text = adb.shell(serial, "cat", path)
    except adb.AdbError as e:
        ui.fail(f"Can't read RetroArch's settings at {path}: {e}", 2)
    return ra_folders(parse_config(text))


def running(serial, pkg):
    return adb.shell_ok(serial, "pidof", pkg)


def wait_closed(serial, pkg):
    while running(serial, pkg):
        print("RetroArch is open on the device: save in-game, then close RetroArch on the device.")
        if not ui.confirm("Closed it? (Enter checks again)", default=True):
            print(ui.yellow("↩️  Stopped: RetroArch is still open"))
            raise SystemExit(0)


def reconnect():
    """Connect the wireless devices adb sees on the network that aren't connected yet."""
    try:
        serials = [d.serial for d in adb.devices()]
        for name, kind, addr in adb.mdns_services():
            if kind == "_adb-tls-connect._tcp" and not any(s.startswith(name) for s in serials):
                adb.connect(addr)
    except adb.AdbError:
        pass


def setup_device():
    print("On the Android device:")
    print("  1. Settings → About → tap Build number 7 times")
    print("  2. Developer options → turn Wireless debugging on (same Wi-Fi as this computer)")
    print("  3. Wireless debugging → Pair device with pairing code")
    try:
        addr = ""
        for _ in range(30):
            addr = next((a for _, kind, a in adb.mdns_services() if kind == "_adb-tls-pairing._tcp"), "")
            if addr:
                break
            time.sleep(1)
        addr = addr or ui.ask("Pairing IP:port shown on the device: ").strip()
        code = ui.ask("6-digit pairing code: ").strip() if addr else ""
        if not code:
            return
        before = {d.serial for d in adb.devices() if d.state == "device"}
        adb.pair(addr, code)
        reconnect()
        for _ in range(10):
            if any(d.state == "device" and d.serial not in before for d in adb.devices()):
                return
            time.sleep(1)
        addr = ui.ask("IP:port under Wireless debugging (not the pairing one): ").strip()
        if addr:
            adb.connect(addr)
    except adb.AdbError as e:
        print(ui.yellow(f"⚠️  {e}"))


def holder(cards, volume):
    return next((name for name, c in cards.items() if is_android(c) and c.get("android_volume") == volume), None)


def pick_device(cards, roms_dir):
    """A connected device, picked from the list; Esc exits and the last row pairs a new one."""
    while True:
        devs = adb.devices()
        for d in devs:
            if d.state != "device":
                hint = "offline — reconnect Wireless debugging" if d.state == "offline" else \
                    "unauthorized — accept the prompt on the device"
                print(ui.dim(f"  {d.serial}: {hint}"))
        ready = [d for d in devs if d.state == "device"]
        labels = []
        for d in ready:
            card = next((holder(cards, v) for v in card_volumes(d.serial, roms_dir) if holder(cards, v)), None)
            labels.append(f"{d.model or 'Android'}  ({d.serial})  {card or 'new card'}")
        pick = picker.filter_list("📱 Which device?", labels + ["➕ Set up a new device"],
                                  hint="Wireless debugging must be on")
        if pick is None:
            raise SystemExit(0)
        if pick < len(ready):
            return ready[pick]
        setup_device()


def resolve(card, cards, roms_dir="ROMs"):
    """The device, its SD card's volume and the card name for a saves command; the volume is remembered."""
    adb.require()
    reconnect()
    volume = (cards.get(card) or {}).get("android_volume") if card else None
    if volume:
        for d in adb.devices():
            if d.state == "device" and volume in card_volumes(d.serial, roms_dir):
                return Target(d.serial, d.model, volume, card)
    dev = pick_device(cards, roms_dir)
    model = dev.model or "Android"
    vols = card_volumes(dev.serial, roms_dir)
    if not vols:
        ui.fail(f"No SD card with {roms_dir}/ in {model}", 2)
    if len(vols) == 1:
        vol = vols[0]
    else:
        vol = next((v for v in vols if card and holder(cards, v) == card), None) or \
            next((v for v in vols if holder(cards, v)), None)
        if not vol:
            pick = picker.filter_list("💾 Which SD card?", vols)
            if pick is None:
                raise SystemExit(0)
            vol = vols[pick]
    owner = holder(cards, vol)
    if card and owner and owner != card:
        ui.fail(f"{model}'s SD card is {owner}, not {card}", 2)
    name = owner or card
    if not name:
        names = store.load_catalog()["devices"]
        android = {n: c for n, c in cards.items() if is_android(c)}
        if not android:
            ui.fail("No Android cards: make one with sync-roms cards new", 2)
        label = {d["id"]: d["name"] for d in names}
        opts = sorted(android, key=lambda n: label.get(android[n].get("device")) != model)
        pick = picker.filter_list("🃏 Which card is this?", opts)
        if pick is None:
            raise SystemExit(0)
        name = opts[pick]
    saved = store.load_cards()
    if name in saved and saved[name].get("android_volume") != vol:
        for c in saved.values():
            if c.get("android_volume") == vol:
                c.pop("android_volume")
        saved[name]["android_volume"] = vol
        store.write_cards(saved)
    for n, c in cards.items():
        if n != name and c.get("android_volume") == vol:
            c.pop("android_volume")
    if name in cards:
        cards[name]["android_volume"] = vol
    return Target(dev.serial, model, vol, name)
