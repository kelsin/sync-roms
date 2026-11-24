"""The WiFi networks saved in settings.json's wifi_networks, merged by SSID into a spruce card's Saves/spruce/wpa_supplicant.conf
(shared by every spruceOS device using the card) in spruceOS's own format, keeping networks added on the device."""
import os
import re

from . import applied, cardfs, ui, usersettings

FILE = os.path.join("Saves", "spruce", "wpa_supplicant.conf")
HEADER = "ctrl_interface=/var/run/wpa_supplicant\nupdate_config=1\n\n"


RAW_PSK = re.compile(r"[0-9a-fA-F]{64}")


def wanted():
    """[(ssid, psk)] of the well-formed wifi_networks entries (psk "" for an open network); the bad ones are warned about once."""
    saved = usersettings.load_settings().get("wifi_networks")
    if not saved:
        return []
    if not isinstance(saved, list):
        ui.warn('wifi_networks in settings.json must be a list of {"ssid", "psk"?}; ignored')
        return []
    result, bad = [], []
    for i, entry in enumerate(saved, 1):
        ssid = entry.get("ssid") if isinstance(entry, dict) else None
        psk = entry.get("psk") if isinstance(entry, dict) else None
        if isinstance(ssid, str) and ssid and (psk is None or isinstance(psk, str)):
            if psk and not RAW_PSK.fullmatch(psk) and not 8 <= len(psk) <= 63:
                ui.warn(f"wifi_networks in settings.json: the {ssid} psk must be 8 to 63 characters or 64 hex digits; skipped")
                continue
            result.append((ssid, psk or ""))
        else:
            bad.append(str(i))
    if bad:
        ui.warn(f'wifi_networks in settings.json: entry {", ".join(bad)} isn\'t {{"ssid": text, "psk"?: text}}; skipped')
    return result


def broken(text):
    """True when spruceOS would set the file aside: blank, no ctrl_interface, or unbalanced network blocks."""
    if not text.strip() or "ctrl_interface" not in text:
        return True
    opens = closes = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("network={"):
            opens += 1
        elif line == "}":
            closes += 1
    return opens != closes


def blocks(lines):
    """[(start, end)] line ranges (end exclusive) of the network={ ... } blocks."""
    found, start = [], None
    for i, line in enumerate(lines):
        line = line.strip()
        if start is None and line.startswith("network={"):
            start = i
        elif start is not None and line == "}":
            found.append((start, i + 1))
            start = None
    return found


def body(ssid, psk):
    secret = psk if RAW_PSK.fullmatch(psk) else f'"{psk}"'
    return [f'ssid="{ssid}"', f"psk={secret}" if psk else "key_mgmt=NONE"]


def merge(text, ssid, psk):
    """(new text, "add" | "update" | None) with the network set as spruceOS's wpa_conf_save_network would write it."""
    lines = text.split("\n")
    mine = [(s, e) for s, e in blocks(lines)
            if any(line.strip() == f'ssid="{ssid}"' for line in lines[s:e])]
    if len(mine) == 1:
        s, e = mine[0]
        if [line.strip() for line in lines[s + 1:e - 1] if line.strip()] == body(ssid, psk):
            return text, None
    for s, e in reversed(mine):
        if s and not lines[s - 1].strip():
            s -= 1  # the blank line spruceOS put before the block
        del lines[s:e]
    text = "\n".join(lines)
    if text and not text.endswith("\n"):
        text += "\n"
    text += "\nnetwork={\n" + "".join(f"    {line}\n" for line in body(ssid, psk)) + "}\n"
    return text, "update" if mine else "add"


def entries(base):
    """[Entry] per saved network: the old value is "present" when the card has the network with the same password,
    "different" when it has it with another, None when it's missing. The password is never in an entry."""
    path = os.path.join(base, FILE)
    text = cardfs.text(path) if os.path.isfile(path) else ""
    shown = FILE.replace(os.sep, "/")
    networks = wanted()
    if networks and os.path.isfile(path) and broken(text):
        ui.warn(f"{shown} couldn't be parsed; it would be replaced (the old one is kept as {os.path.basename(path)}.broken)")
        text = ""
    states = {None: "present", "update": "different", "add": None}
    return [applied.Entry(shown, f"network {ssid}", states[merge(text, ssid, psk)[1]], "present", False) for ssid, psk in networks]


def install(card, layout_name, base, dry_run):
    """Merge the saved WiFi networks into a spruce card's wpa_supplicant.conf. The failure count."""
    if layout_name != "spruce":
        return 0
    networks = wanted()
    if not networks:
        return 0
    path = os.path.join(base, FILE)
    shown = FILE.replace(os.sep, "/")
    old = cardfs.text(path) if os.path.isfile(path) else ""
    text = old
    if os.path.isfile(path) and broken(old):
        ui.warn(f"{shown} couldn't be parsed; replacing it (the old one is kept as {os.path.basename(path)}.broken)")
        text = ""
    if not text:
        text = HEADER
    changes = []
    for ssid, psk in networks:
        text, change = merge(text, ssid, psk)
        changes.append((ssid, change))
    if text != old and not dry_run:
        try:
            if old and broken(old):
                cardfs.write_text(path + ".broken", old)
            cardfs.write_text(path, text)
        except OSError as e:
            ui.warn(f"Couldn't write {shown}: {e}")
            return 1
    for ssid, change in changes:
        if not change:
            print(ui.dim(f"📶 The {ssid} WiFi network is already on the card"))
        elif dry_run:
            print(ui.dim(f"🧪 Dry run: would {change} the {ssid} WiFi network {'to' if change == 'add' else 'in'} {shown}"))
        else:
            print(f"📶 {'Adding' if change == 'add' else 'Updating'} the {ssid} WiFi network → {shown}")
    return 0
