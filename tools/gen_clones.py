#!/usr/bin/env python3
"""Regenerate src/sync_roms/data/clones.json from MAME's -listxml output and FBNeo's arcade DAT.

    tools/gen_clones.py MAME.xml FBNEO.dat

Per system ("mame", "fbneo"): {"parents": {ROM name: title}, "clones": {ROM name: [parent ROM name, title]}}.
Only parents that have clones are kept. MAME's non-arcade machines (computers, consoles, devices, BIOS sets)
are left out.
"""
import json
import os
import sys
import xml.etree.ElementTree as ET

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "sync_roms", "data", "clones.json")


def is_arcade(el):
    if el.get("isdevice") == "yes" or el.get("isbios") == "yes" or el.get("runnable") == "no":
        return False
    inp = el.find("input")
    return inp is not None and int(inp.get("coins") or 0) > 0


def read(path, tag, keep):
    titles, parent_of = {}, {}
    for _, el in ET.iterparse(path):
        if el.tag not in tag:
            continue
        if keep(el):
            titles[el.get("name")] = (el.findtext("description") or "").strip()
            if el.get("cloneof"):
                parent_of[el.get("name")] = el.get("cloneof")
        el.clear()
    return titles, parent_of


def build(titles, parent_of):
    clones = {n: [p, titles[n]] for n, p in sorted(parent_of.items()) if p in titles and titles[n]}
    parents = {p: titles[p] for p in sorted({p for p, _ in clones.values()}) if titles[p]}
    return {"parents": parents, "clones": {n: c for n, c in clones.items() if c[0] in parents}}


def main(mame_xml, fbneo_dat):
    data = {"mame": build(*read(mame_xml, ("machine", "game"), is_arcade)),
            "fbneo": build(*read(fbneo_dat, ("game",), lambda el: True))}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    for system, d in data.items():
        print(f"{system}: {len(d['clones'])} clones of {len(d['parents'])} parents")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
