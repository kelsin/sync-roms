#!/usr/bin/env python3
"""Copy the device list from src/sync_roms/data/devices.json and each device's tier and systems from
src/sync_roms/data/device-systems.json into src/sync_roms/data/setup-guide.html.

    tools/update_setup_guide.py
"""
import json
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DEVICES = os.path.join(ROOT, "src", "sync_roms", "data", "devices.json")
SYSTEMS = os.path.join(ROOT, "src", "sync_roms", "data", "device-systems.json")
GUIDE = os.path.join(ROOT, "src", "sync_roms", "data", "setup-guide.html")
KEYS = ("id", "name", "soc", "screen", "screen2", "firmwares", "gpu", "network")
BLOCK = re.compile(r'(<script type="application/json" id="devices-data">\n)(.*?)(\n</script>)', re.S)
SYSTEMS_BLOCK = re.compile(r'(<script type="application/json" id="systems-data">\n)(.*?)(\n</script>)', re.S)


def devices_json():
    """The guide's device block: one device per line, only the fields the guide shows."""
    with open(DEVICES) as f:
        devices = json.load(f)
    rows = [json.dumps({k: d[k] for k in KEYS if k in d}, ensure_ascii=False) for d in devices]
    return "[\n" + ",\n".join(rows) + "\n]"


def systems_json():
    """Each device's tier and supported systems (repo defaults, no personal overlay), one device per line.

    The first tier lists systems and each later one adds to the tier before it."""
    with open(SYSTEMS) as f:
        data = json.load(f)
    cumulative, by_tier = [], {}
    for t in data["tiers"]:
        cumulative = cumulative + [s for s in t.get("systems", []) + t.get("add", []) if s not in cumulative]
        by_tier[t["id"]] = cumulative
    rows = [f'{json.dumps(d)}: {json.dumps({"tier": v["tier"], "systems": by_tier[v["tier"]]})}'
            for d, v in data["devices"].items()]
    return "{\n" + ",\n".join(rows) + "\n}"


def embedded(html, block=BLOCK):
    return block.search(html).group(2)


def main():
    with open(GUIDE) as f:
        html = f.read()
    new = BLOCK.sub(lambda m: m.group(1) + devices_json() + m.group(3), html)
    new = SYSTEMS_BLOCK.sub(lambda m: m.group(1) + systems_json() + m.group(3), new)
    with open(GUIDE, "w") as f:
        f.write(new)


if __name__ == "__main__":
    main()
