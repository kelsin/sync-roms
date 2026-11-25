"""Serve the collections page on the tailnet (`sync-roms collections share`): only its own folder, through tailscale serve."""
import json
import os
import shutil
import subprocess

from . import collections_page, ui

PATH = "/collections"
CLIPBOARD = (["pbcopy"], ["clip"], ["wl-copy"], ["xclip", "-selection", "clipboard"])


def SHARE_DIR():
    """The only folder tailscale serve is given: the folder of the page, never the data folder."""
    return os.path.dirname(collections_page.DEFAULT_PATH())


def _tailscale(*args):
    if not shutil.which("tailscale"):
        ui.fail("tailscale isn't installed or not on PATH", 1)
    try:
        done = subprocess.run(["tailscale", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    except subprocess.TimeoutExpired:
        ui.fail("tailscale didn't answer within 60 s", 1)
    except OSError as e:
        ui.fail(f"couldn't run tailscale: {e}", 1)
    if done.returncode != 0:
        ui.fail(f"tailscale {args[0]} failed: {done.stderr.strip()}", 1)
    return done.stdout


def serving():
    """True when tailscale serve already has a handler at PATH (unreadable or unexpected output: not serving)."""
    out = _tailscale("serve", "status", "--json").strip()
    try:
        web = (json.loads(out) if out else {}).get("Web") or {}
        return any(PATH in (site.get("Handlers") or {}) for site in web.values())
    except (ValueError, AttributeError, TypeError):
        return False


def _dns_name():
    try:
        return (json.loads(_tailscale("status", "--json") or "{}").get("Self") or {}).get("DNSName").rstrip(".")
    except (ValueError, AttributeError, TypeError):
        return ""


def share():
    """Write the page when missing and serve it. Returns (link, built, started)."""
    page = os.path.join(SHARE_DIR(), "index.html")
    built = not os.path.exists(page)
    if built:
        collections_page.write_page(page)
    started = not serving()
    if started:
        _tailscale("serve", "--bg", "--set-path", PATH, SHARE_DIR())
    name = _dns_name()
    if not name:
        ui.fail("Couldn't read this machine's tailnet name from tailscale status", 1)
    return f"https://{name}{PATH}/", built, started


def unshare():
    """Turn off the handler at PATH, only that one. False when it wasn't served."""
    if not serving():
        return False
    _tailscale("serve", "--https=443", "--set-path", PATH, "off")
    return True


def copy_to_clipboard(text):
    """Copy text with the first clipboard command found; False when none is or it fails."""
    for argv in CLIPBOARD:
        if shutil.which(argv[0]):
            try:
                return subprocess.run(argv, input=text, text=True, capture_output=True, timeout=10).returncode == 0
            except (OSError, subprocess.SubprocessError):
                return False
    return False
