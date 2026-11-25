"""PortMaster on spruce: the card paths it uses, which devices and systems it covers, and the picked ports sync
stages in its autoinstall folder."""
import contextlib
import json
import os

from . import downloads, inventory, s3, store, ui

PORTS = "ports"  # the system id and storage folder of the port zips
CONTROL = "Persistent/portmaster/PortMaster"
AUTOINSTALL = CONTROL + "/autoinstall"
LIBS = CONTROL + "/libs"
CARD_PORTS = "Roms/PORTS"  # where PortMaster installs ports
RUNTIMES = "os/portmaster/runtimes/"


def enabled(device, layout_name):
    """Whether PortMaster is set up on this card: a spruce card of a device flagged "portmaster"."""
    return layout_name == "spruce" and bool(device) and device.get("portmaster") is True


def owns_folder(system):
    """Whether PortMaster owns the system's ROM folder: sync never sweeps, cleans or prunes it, on any layout."""
    return system["bucket"] == PORTS


def installed(base):
    """{port folder: its parsed port.json} for each Roms/PORTS/<folder>/port.json on the card."""
    found = {}
    ports = os.path.join(base, CARD_PORTS)
    with contextlib.suppress(OSError):
        for entry in sorted(os.scandir(ports), key=lambda e: e.name):
            path = os.path.join(entry.path, "port.json")
            if not entry.is_dir() or not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError) as e:
                ui.warn(f"Skipping {path}: {e}")
                continue
            if not isinstance(data, dict) or not isinstance(data.get("attr"), dict):
                ui.warn(f"Skipping {path}: not a PortMaster port.json")
                continue
            found[entry.name] = data
    return found


def _names(folder):
    """The casefolded names in a card folder (none when it isn't there)."""
    try:
        return {n.casefold() for n in os.listdir(folder)}
    except OSError:
        return set()


def is_installed(zip_name, facts, ports_on_card, base):
    """Whether the port is on the card: an installed port.json names the zip, or every one of its items is in Roms/PORTS."""
    if any(isinstance(p.get("name"), str) and p["name"].casefold() == zip_name.casefold() for p in ports_on_card.values()):
        return True
    items = [i.strip("/") for i in facts.get("items") or [] if isinstance(i, str) and i.strip("/")]
    on_card = _names(os.path.join(base, CARD_PORTS))
    return bool(items) and all(i.casefold() in on_card for i in items)


def stage(card, device, layout_name, base, picked, dry_run, keep):
    """Put the picked ports that aren't installed, and the runtimes they need, in PortMaster's autoinstall folder.
    (failure count, titles of the ports waiting there). keep (--no-delete): leave staged ports no longer picked."""
    from . import scrape_plan  # it imports this module back
    if not enabled(device, layout_name):
        return 0, []
    saved = store.saved_card(card)
    staged = {n for n in saved.get("portmaster_staged") or [] if isinstance(n, str) and n and "/" not in n}
    if not picked and not staged:
        return 0, []
    if not os.path.isdir(os.path.join(base, CONTROL)):
        print(ui.yellow("🧩 Boot the device once so spruceOS sets up PortMaster, then sync again"))
        return 0, []
    autoinstall, libs = os.path.join(base, AUTOINSTALL), os.path.join(base, LIBS)
    waiting, in_libs = _names(autoinstall), _names(libs)
    try:
        metadata = scrape_plan.load_metadata(PORTS)
    except (ValueError, *s3.ERRORS) as e:
        ui.warn(f"Couldn't read the ports' metadata: {e}")
        return 1, []
    zips = inventory.files(PORTS + "/")
    runtimes = inventory.files(RUNTIMES)
    ports_on_card = installed(base)
    jobs, waiting_ports, wanted = [], [], set()  # waiting_ports: (zip, title) of the picks to stage
    for zip_name in picked:
        entry = metadata.get(zip_name)
        facts = entry.get("portmaster") if isinstance(entry, dict) else None
        if not isinstance(facts, dict):
            ui.warn(f"{zip_name} has no PortMaster facts in storage: run sync-roms ports download --update {zip_name}")
            continue
        if is_installed(zip_name, facts, ports_on_card, base):
            continue
        key = f"{PORTS}/{zip_name}"
        if key not in zips:
            ui.warn(f"{key} isn't in storage")
            continue
        wanted.add(zip_name)
        waiting_ports.append((zip_name, entry.get("name") or zip_name))
        target = os.path.join(autoinstall, zip_name)
        if not (os.path.isfile(target) and os.path.getsize(target) == zips[key]):
            jobs.append((key, target, zips[key]))
        for rt in facts.get("runtime") or []:
            if not isinstance(rt, str) or rt.casefold() in in_libs or rt in wanted:
                continue
            wanted.add(rt)
            if rt.casefold() in waiting:
                continue
            if RUNTIMES + rt not in runtimes:
                ui.warn(f"{rt}, a runtime of {zip_name}, isn't in storage: run sync-roms ports download {zip_name}")
                continue
            jobs.append((RUNTIMES + rt, os.path.join(autoinstall, rt), runtimes[RUNTIMES + rt]))
    stale = sorted(n for n in staged if n.endswith(".zip") and n not in wanted and n.casefold() in waiting)
    if dry_run:
        for key, _, size in jobs:
            print(ui.dim(f"🧪 Dry run: would stage {os.path.basename(key)} ({ui.human_size(size)}) for PortMaster"))
        if stale:
            done = "keep (--no-delete)" if keep else "delete"
            print(ui.dim(f"🧪 Dry run: would {done} the staged ports no longer picked: {', '.join(stale)}"))
        return 0, [t for _, t in waiting_ports]
    failures = []
    failed = downloads.run_downloads(jobs, "PortMaster", "🧩", base, failures) if jobs else 0
    for key, reason in failures:
        ui.warn(f"Couldn't stage {key} for PortMaster: {reason}")
    if not keep:
        for n in stale:
            with contextlib.suppress(OSError):
                os.remove(os.path.join(autoinstall, n))
    copied = {os.path.basename(t) for k, t, _ in jobs if k not in {f for f, _ in failures}}
    now = _names(autoinstall)
    field = sorted(n for n in staged | copied if n.casefold() in now)
    if field:
        store.update_card(card, portmaster_staged=field)
    else:
        store.drop_card_field(card, "portmaster_staged")
    titles = [t for z, t in waiting_ports if z.casefold() in now]
    if titles:
        print(ui.bold(f"🧩 Open PortMaster on the device to install: {', '.join(titles)}"))
    return failed, titles
