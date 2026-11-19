#!/usr/bin/env python3
"""Copy the device list from src/sync_roms/data/devices.json into src/sync_roms/data/setup-guide.html.

    tools/update_setup_guide.py
"""
import json
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DEVICES = os.path.join(ROOT, "src", "sync_roms", "data", "devices.json")
GUIDE = os.path.join(ROOT, "src", "sync_roms", "data", "setup-guide.html")
KEYS = ("id", "name", "soc", "screen", "screen2", "firmwares")
BLOCK = re.compile(r'(<script type="application/json" id="devices-data">\n)(.*?)(\n</script>)', re.S)


def devices_json():
    """The guide's device block: one device per line, only the fields the guide shows."""
    with open(DEVICES) as f:
        devices = json.load(f)
    rows = [json.dumps({k: d[k] for k in KEYS if k in d}, ensure_ascii=False) for d in devices]
    return "[\n" + ",\n".join(rows) + "\n]"


def embedded(html):
    return BLOCK.search(html).group(2)


def main():
    with open(GUIDE) as f:
        html = f.read()
    new = BLOCK.sub(lambda m: m.group(1) + devices_json() + m.group(3), html)
    with open(GUIDE, "w") as f:
        f.write(new)


if __name__ == "__main__":
    main()
