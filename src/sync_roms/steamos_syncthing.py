"""Syncthing on SteamOS: uses the one already there (any kind), installs the official binary as a systemd user service only
when there is none, and adds the server and the RetroArch save and state folders through its REST API."""
import hashlib
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import namedtuple

from . import android_syncthing, applied, github, spruce_syncthing, ui

Install = namedtuple("Install", "config flatpak")  # config.xml's path, the Flatpak app id or None

# The Syncthing Flatpaks on Flathub (github.com/flathub: SyncThingy, Syncthing GTK, Syncthing Tray). Each runs Syncthing
# with its default home, so its config is under the app's XDG folders (as decky-syncthing-watchdog's checks.rs looks).
# The Decky Syncthing plugin (theCapypara/steamdeck-decky-syncthing) has no Syncthing of its own: it drives one of these
# or a systemd one, so it has no path here.
FLATPAKS = ("com.github.zocker_160.SyncThingy", "me.kozec.syncthingtk", "io.github.martchus.syncthingtray")
FLATPAK_CONFIGS = (".local/state/syncthing/config.xml", "config/syncthing/config.xml")  # under ~/.var/app/<id>/
CONFIGS = (".local/state/syncthing/config.xml", ".config/syncthing/config.xml")  # under ~
REPO = "syncthing/syncthing"
SUMS = ("sha256sum.txt", "sha256sum.txt.asc")  # releases ship the clearsigned .asc
ARCHES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
WHERE = "Syncthing"
UNIT = "etc/linux-systemd/user/syncthing.service"


def _flatpak_of(path, home):
    """The Flatpak app id whose ~/.var/app/<id>/ holds path, or None."""
    rel = os.path.relpath(path, os.path.join(home, ".var", "app"))
    return None if rel.startswith("..") or os.path.isabs(rel) else rel.split(os.sep)[0]


def _running():
    """The folder a running syncthing was given with --home or --config, or None."""
    try:
        result = subprocess.run(["pgrep", "-a", "syncthing"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None
    for line in result.stdout.splitlines():
        args = line.split()[1:]
        if not args or os.path.basename(args[0]) != "syncthing":
            continue
        for i, arg in enumerate(args[1:], 1):
            match = re.fullmatch(r"--?(?:home|config)(?:=(.+))?", arg)
            if match:
                folder = match.group(1) or (args[i + 1] if i + 1 < len(args) else None)
                if folder:
                    return folder
    return None


def find(home):
    """The Syncthing install to use, or None when there is none."""
    folder = _running()
    if folder:
        path = os.path.join(folder, "config.xml")
        return Install(path, _flatpak_of(path, home))
    candidates = [(os.path.join(home, rel), None) for rel in CONFIGS]
    candidates += [(os.path.join(home, ".var", "app", app, rel), app) for app in FLATPAKS for rel in FLATPAK_CONFIGS]
    return next((Install(path, app) for path, app in candidates if os.path.isfile(path)), None)


def read_config(text):
    """(API key, GUI port, "http"|"https") from config.xml's text, or why it can't be used."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return "can't be parsed"
    gui = root.find("gui")
    key = (root.findtext("gui/apikey") or "").strip()
    if gui is None or not key:
        return "has no API key"
    match = re.search(r":(\d+)$", (root.findtext("gui/address") or "").strip())
    scheme = "https" if (gui.get("tls") or "").lower() == "true" else "http"
    return key, int(match.group(1)) if match else 8384, scheme


def _covers(grant, folder, home):
    grant, _, mode = grant.partition(":")
    if mode == "ro" or grant.startswith("!"):
        return False
    if grant == "host":
        return True
    if grant == "home" or grant == "~":
        grant = home
    elif grant.startswith("~/"):
        grant = os.path.join(home, grant[2:])
    if not grant.startswith("/"):
        return False  # xdg-*, host-os, host-etc
    grant = grant.rstrip("/") or "/"
    return folder == grant or folder.startswith(grant.rstrip("/") + "/")


def flatpak_entries(app, folders, permissions):
    """An entry per folder the app's `flatpak info --show-permissions` output doesn't let it write."""
    line = next((line for line in permissions.splitlines() if line.startswith("filesystems=")), "filesystems=")
    grants = [g for g in line.partition("=")[2].split(";") if g]
    home = os.path.realpath(os.path.expanduser("~"))
    return [applied.Entry(f"Flatpak {app}", f"filesystem {folder}", None, "allowed", False)
            for folder in folders if not any(_covers(g, folder, home) for g in grants)]


def _fetch(url):
    with github.get(url) as r:
        return r.read()


def install(home):
    """Install the latest official Syncthing as a systemd user service; returns its config.xml path once written."""
    arch = ARCHES.get(platform.machine().lower())
    if not arch:
        raise ValueError(f"no Syncthing build for {platform.machine()}")
    release = github.json(f"https://api.github.com/repos/{REPO}/releases/latest")
    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    name = next((n for n in assets if re.fullmatch(rf"syncthing-linux-{arch}-v.+\.tar\.gz", n)), None)
    sums = next((assets[n] for n in SUMS if n in assets), None)
    if not name or not sums:
        raise ValueError(f"the latest Syncthing release has no {arch} tarball or sha256sum.txt")
    wanted = next((m.group(1) for m in re.finditer(r"^([0-9a-f]{64})\s+\*?(\S+)\s*$", _fetch(sums).decode(), re.M)
                   if m.group(2) == name), None)
    if not wanted:
        raise ValueError(f"sha256sum.txt doesn't list {name}")
    data = _fetch(assets[name])
    if hashlib.sha256(data).hexdigest() != wanted:
        raise ValueError(f"{name} doesn't match its sha256sum.txt checksum")
    cache = os.path.join(home, ".cache")
    os.makedirs(cache, exist_ok=True)
    binary = os.path.join(home, ".local", "bin", "syncthing")
    unit_path = os.path.join(home, ".config", "systemd", "user", "syncthing.service")
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
        archive = os.path.join(tmp, name)
        with open(archive, "wb") as f:
            f.write(data)
        out = os.path.join(tmp, "x")
        with tarfile.open(archive) as tar:
            tar.extractall(out, filter="data")
        tops = os.listdir(out)
        top = os.path.join(out, tops[0]) if len(tops) == 1 else out
        with open(os.path.join(top, UNIT)) as f:
            unit = f.read()
        os.makedirs(os.path.dirname(binary), exist_ok=True)
        staged = binary + ".new"
        shutil.copyfile(os.path.join(top, "syncthing"), staged)
        os.chmod(staged, 0o755)
        os.replace(staged, binary)
    os.makedirs(os.path.dirname(unit_path), exist_ok=True)
    with open(unit_path, "w") as f:
        f.write(re.sub(r"^ExecStart=\S+", lambda _: f"ExecStart={binary}", unit, flags=re.M))
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "syncthing"], check=True)
    config = os.path.join(home, *CONFIGS[0].split("/"))
    deadline = time.monotonic() + 30
    while not os.path.isfile(config):
        if time.monotonic() >= deadline:
            raise OSError(f"Syncthing didn't write {config} within 30 seconds")
        time.sleep(1)
    return config


def _flatpak_access(app, folders, dry_run):
    """entries for the save folders the Flatpak can't write, overridden unless a dry run."""
    permissions = subprocess.run(["flatpak", "info", "--show-permissions", app],
                                 capture_output=True, text=True, check=True).stdout
    entries = flatpak_entries(app, folders, permissions)
    if not dry_run:
        for entry in entries:
            folder = entry.key.removeprefix("filesystem ")
            subprocess.run(["flatpak", "override", "--user", f"--filesystem={folder}", app], check=True)
    return entries


def apply(paths, dry_run, failed):
    """Make sure one Syncthing runs and give it the server and the folders at `paths` ({"saves", "states"})."""
    if not spruce_syncthing.enabled():
        return
    try:
        home = os.path.expanduser("~")
        found = find(home)
        if found is None:
            if dry_run:
                print(ui.dim("🧪 Dry run: no Syncthing found; would install the official one as a systemd user service "
                             "and add the server and folders"))
                return
            found = Install(install(home), None)
        with open(found.config, encoding="utf-8") as f:
            config = read_config(f.read())
        if isinstance(config, str):
            ui.warn(f"Syncthing's {found.config} {config}; the server and folders aren't set")
            return
        key, port, scheme = config
        entries = _flatpak_access(found.flatpak, list(paths.values()), dry_run) if found.flatpak else []
        srv = spruce_syncthing.server()
        if srv:
            if android_syncthing._up(port, key, scheme):
                entries += android_syncthing.configure(port, key, srv, paths, dry_run, scheme, where=WHERE,
                                                       mod_time_window=2, wait=False) or []
            else:
                ui.warn(f"Syncthing ({found.config}) doesn't answer on port {port}: start it, then run config apply again")
        applied.show(entries, dry_run)
        if found.flatpak and any(e.where.startswith("Flatpak") for e in entries) and not dry_run:
            print(ui.yellow(f"Quit and restart {found.flatpak} so its Syncthing can see the save folders"))
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        ui.warn(f"Syncthing: {e}")
        failed.append("Syncthing")
