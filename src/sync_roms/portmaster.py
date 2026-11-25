"""PortMaster on spruce: the card paths it uses, which devices and systems it covers, and the picked ports sync
stages in its autoinstall folder."""
import contextlib
import json
import os
import shlex

from . import downloads, inventory, portmaster_catalog, portmaster_needed, s3, store, ui

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


def skip(system, layout_name):
    """Whether the system is the port zips on spruce: never files in Roms/PORTS, so Surprise, collections, scrapes and
    the editor's sizes leave it out."""
    return layout_name == "spruce" and system["bucket"] == PORTS


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
    missed = 0  # picks that can't be staged: still picked, so what an earlier sync staged for them stays
    for zip_name in picked:
        entry = metadata.get(zip_name)
        facts = entry.get("portmaster") if isinstance(entry, dict) else None
        if not isinstance(facts, dict):
            ui.warn(f"{zip_name} has no PortMaster facts in storage: run sync-roms ports download --update {zip_name}")
            wanted.add(zip_name)
            missed += 1
            continue
        if is_installed(zip_name, facts, ports_on_card, base):
            continue
        key = f"{PORTS}/{zip_name}"
        wanted.add(zip_name)
        if key not in zips:
            ui.warn(f"{key} isn't in storage")
            missed += 1
            continue
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
        return missed, [t for _, t in waiting_ports]
    failures = []
    failed = missed + (downloads.run_downloads(jobs, "PortMaster", "🧩", base, failures) if jobs else 0)
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


GAMEDATA = portmaster_needed.GAMEDATA


def _folder_of(facts):
    """The port folder a port's facts name, or None."""
    folder = facts.get("folder")
    return folder.strip("/") if isinstance(folder, str) and folder.strip("/") else None


def pending(base, picked, ports_on_card):
    """{zip: metadata entry} of the picked ports not installed yet (stage already warned about any it couldn't read)."""
    from . import scrape_plan  # it imports this module back
    try:
        metadata = scrape_plan.load_metadata(PORTS)
    except (ValueError, *s3.ERRORS):
        return {}
    found = {}
    for zip_name in picked:
        entry = metadata.get(zip_name)
        facts = entry.get("portmaster") if isinstance(entry, dict) else None
        if isinstance(facts, dict) and not is_installed(zip_name, facts, ports_on_card, base):
            found[zip_name] = entry
    return found


def game_data(card, base, ports_on_card, picked_facts, dry_run):
    """Copy the game data storage has for the card's installed ports that need it (once per card and port, never over a
    card file), and list the ones storage has none for, with the picked ports not installed yet that need it, in the
    needed list. (failure count, [(port folder, needed entry, True when PortMaster hasn't installed it yet)])."""
    saved = store.saved_card(card)
    done = {n.casefold() for n in saved.get("portmaster_data") or [] if isinstance(n, str)}
    entries = portmaster_needed.load()
    had_file = os.path.exists(portmaster_needed.path())
    failed, jobs, copies, needing, waiting = 0, [], {}, [], []  # copies: {folder: (title, its jobs)}

    def stored(folder):
        """{key: size} of storage's game data for the port, or None when storage can't be read."""
        try:
            return inventory.files(f"{GAMEDATA}{folder}/")
        except s3.ERRORS as e:
            ui.warn(f"Couldn't list the game data of {folder} in storage: {e}")
            return None

    def wait(folder, title, zip_name, inst, later):
        if any(w[0].casefold() == folder.casefold() for w in waiting):
            return
        portmaster_needed.add(entries, folder, title, zip_name, inst, card)
        waiting.append((folder, entries[folder], later))

    for folder, port in ports_on_card.items():
        attr = port["attr"]
        if attr.get("rtr") is not False:
            continue
        needing.append(folder)
        if folder.casefold() in done:
            continue
        files = stored(folder)
        if files is None:
            failed += 1
            continue
        title = attr.get("title") or folder
        if not files:
            wait(folder, title, port.get("name") or "", attr.get("inst") or "", False)
            continue
        prefix = f"{GAMEDATA}{folder}/"
        todo = [(k, os.path.join(base, CARD_PORTS, folder, *k[len(prefix):].split("/")), size) for k, size in sorted(files.items())]
        todo = [j for j in todo if not os.path.exists(j[1])]
        copies[folder] = (title, todo)
        jobs += todo
    for zip_name, entry in picked_facts.items():
        facts = entry["portmaster"]
        folder = _folder_of(facts)
        if facts.get("rtr") is not False or not folder or folder.casefold() in done:
            continue
        files = stored(folder)
        if files is None:
            failed += 1
        elif not files:
            wait(folder, entry.get("name") or zip_name, zip_name, facts.get("inst") or "", True)
    if dry_run:
        for folder, (title, todo) in copies.items():
            if todo:
                size = sum(j[2] or 0 for j in todo)
                print(ui.dim(f"🧪 Dry run: would copy {len(todo)} game data file(s) ({ui.human_size(size)}) for {title}"))
        return failed, waiting
    failures = []
    failed += downloads.run_downloads(jobs, "PortMaster game data", "🧩", base, failures) if jobs else 0
    for key, reason in failures:
        ui.warn(f"Couldn't copy {key}: {reason}")
    bad = {k for k, _ in failures}
    copied = [f for f, (_, todo) in copies.items() if not any(j[0] in bad for j in todo)]
    if copied:
        store.update_card(card, portmaster_data=sorted({n for n in saved.get("portmaster_data") or [] if isinstance(n, str)} | set(copied)))
    if sorted(needing) != saved.get("portmaster_ports"):
        if needing:
            store.update_card(card, portmaster_ports=sorted(needing))
        else:
            store.drop_card_field(card, "portmaster_ports")
    gone = portmaster_needed.prune(entries)
    if gone:
        print(ui.green(f"🧩 Storage now has the game data of: {', '.join(gone)}"))
    if entries or had_file:
        portmaster_needed.save(entries)
    return failed, waiting


def summary(card, waiting):
    """The ports waiting for game data, each with its instructions and where its data goes in storage."""
    if not waiting:
        return
    print(ui.bold("\n🧩 Ports waiting for game data"))
    for folder, entry, later in sorted(waiting, key=lambda w: (w[1].get("title") or w[0]).casefold()):
        text = portmaster_needed.block(entry, folder)
        if later:
            first, _, rest = text.partition("\n")
            text = f"{first} (after PortMaster installs it)\n{rest}"
        print(text)
    folder = waiting[0][0] if len(waiting) == 1 else "<folder>"
    print(f"Already on the card? sync-roms ports done {shlex.quote(card)} {folder}")
    print("All of them: sync-roms ports needed")


def updates(base, ports_on_card):
    """Note the installed ports PortMaster has a newer version of, from the cached catalogue (never fetched here)."""
    catalog = portmaster_catalog.load(fetch=False)
    if not catalog or not ports_on_card:
        return
    by_zip = {z.casefold(): e for z, e in portmaster_catalog.ports(catalog).items() if isinstance(e, dict)}
    titles = []
    for folder, port in ports_on_card.items():
        name, status = port.get("name"), port.get("status")
        md5 = status.get("md5") if isinstance(status, dict) else None
        entry = by_zip.get(name.casefold()) if isinstance(name, str) else None
        latest = (entry.get("source") or {}).get("md5") if entry else None
        if md5 and latest and md5 != latest:
            titles.append(port["attr"].get("title") or folder)
    if titles:
        print(ui.bold(f"🧩 Updates available in PortMaster on the device: {', '.join(sorted(titles, key=str.casefold))}"))
