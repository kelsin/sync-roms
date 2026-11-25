"""Share the collections page on the tailnet (`sync-roms collections share`): a local http.server for its own folder
only, which tailscale serve proxies to at /collections."""
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

from . import collections_page, store, ui

PATH = "/collections"
MOUNTS = (PATH, PATH + "/")
DEFAULT_PORT = 8737
SERVE_TIMEOUT = 30
NOT_ENABLED = "Serve is not enabled on your tailnet"
CLIPBOARD = (["pbcopy"], ["clip"], ["wl-copy"], ["xclip", "-selection", "clipboard"])


def SHARE_DIR():
    """The only folder the local server serves: the folder of the page, never the data folder."""
    return os.path.dirname(collections_page.DEFAULT_PATH())


def STATE_FILE():
    """The running server's {"pid", "port"}: in the data folder, never inside SHARE_DIR, so it's never served."""
    return os.path.join(store.data_dir(), "share-server.json")


def _text(out):
    return out.decode(errors="replace") if isinstance(out, bytes) else (out or "")


def _not_enabled(*outputs):
    text = "".join(_text(o) for o in outputs)
    if NOT_ENABLED in text:
        url = re.search(r"https://\S+", text.split(NOT_ENABLED, 1)[1])
        ui.fail(f"Tailscale Serve isn't enabled on your tailnet. Enable it at {url.group(0) if url else 'the Tailscale admin console'}, then run this again", 1)


def _tailscale(*args, timeout=60):
    if not shutil.which("tailscale"):
        ui.fail("tailscale isn't installed or not on PATH", 1)
    try:
        done = subprocess.run(["tailscale", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        _not_enabled(e.stdout, e.stderr)
        ui.fail(f"tailscale didn't answer within {timeout} s", 1)
    except OSError as e:
        ui.fail(f"couldn't run tailscale: {e}", 1)
    _not_enabled(done.stdout, done.stderr)
    if done.returncode != 0:
        ui.fail(f"tailscale {args[0]} failed: {done.stderr.strip()}", 1)
    return done.stdout


def serving():
    """(host:443 key, mount, proxy) of tailscale serve's handler at /collections or /collections/, else None
    (unreadable or unexpected output: not serving)."""
    out = _tailscale("serve", "status", "--json").strip()
    try:
        web = (json.loads(out) if out else {}).get("Web") or {}
        for key, site in web.items():
            if not key.endswith(":443"):
                continue
            handlers = site.get("Handlers") or {}
            for mount in MOUNTS:
                if mount in handlers:
                    handler = handlers[mount]
                    return key, mount, handler.get("Proxy") if isinstance(handler, dict) else None
    except (ValueError, AttributeError, TypeError):
        pass
    return None


def _dns_name():
    try:
        return (json.loads(_tailscale("status", "--json") or "{}").get("Self") or {}).get("DNSName").rstrip(".")
    except (ValueError, AttributeError, TypeError):
        return ""


def _alive(pid):
    if os.name == "nt":  # os.kill(pid, 0) terminates the process on Windows: rely on the port check there
        return True
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _accepts(port, timeout=1):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _free_port():
    """DEFAULT_PORT when it's free on 127.0.0.1, else a free port the system picks."""
    for port in (DEFAULT_PORT, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return s.getsockname()[1]


def _running():
    """(pid, port) of the server an earlier share started, when its pid is alive and its port answers; else None."""
    try:
        with open(STATE_FILE(), encoding="utf-8") as f:
            state = json.load(f)
        pid, port = state["pid"], state["port"]
    except (OSError, ValueError, TypeError, KeyError):
        return None
    if not all(type(v) is int for v in (pid, port)):
        return None
    return (pid, port) if _alive(pid) and _accepts(port) else None


def _start_server():
    """Start the page server on a free port, save its state, and wait for it to listen. Returns the port."""
    port = _free_port()
    try:
        proc = subprocess.Popen([sys.executable, "-I", "-m", "http.server", "--bind", "127.0.0.1", "--directory", SHARE_DIR(), str(port)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                                cwd=SHARE_DIR())
    except OSError:
        ui.fail("The local page server didn't start", 1)
    store.write_json(STATE_FILE(), {"pid": proc.pid, "port": port})
    deadline = time.monotonic() + 3
    while not _accepts(port):
        if proc.poll() is not None or time.monotonic() > deadline:
            ui.fail("The local page server didn't start", 1)
        time.sleep(0.1)
    return port


def share():
    """Write the page when missing or out of date, run its local server and have tailscale serve proxy to it. Returns (link, built,
    started): started when the server or the serve entry had to be set up."""
    page = os.path.join(SHARE_DIR(), "index.html")
    built = collections_page.update_page(page)
    found = serving()
    running = _running()
    port = running[1] if running else _start_server()
    target = f"http://127.0.0.1:{port}"
    started = not running
    if not found or (found[2] or "").rstrip("/") != target:
        if found:
            _tailscale("serve", "--https=443", "--set-path", found[1], "off")
        _tailscale("serve", "--bg", "--yes", "--https=443", "--set-path", PATH, target, timeout=SERVE_TIMEOUT)
        started = True
    name = _dns_name()
    if not name:
        ui.fail("Couldn't read this machine's tailnet name from tailscale status", 1)
    return f"https://{name}{PATH}/", built, started


def unshare():
    """Turn off the handler found at /collections (only that one) and stop the local server. False when neither was
    there."""
    found = serving()
    if found:
        _tailscale("serve", "--https=443", "--set-path", found[1], "off")
    running = _running()
    if running:
        try:
            os.kill(running[0], signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        os.remove(STATE_FILE())
    except FileNotFoundError:
        pass
    return bool(found or running)


def copy_to_clipboard(text):
    """Copy text with the first clipboard command found; False when none is or it fails."""
    for argv in CLIPBOARD:
        if shutil.which(argv[0]):
            try:
                return subprocess.run(argv, input=text, text=True, capture_output=True, timeout=10).returncode == 0
            except (OSError, subprocess.SubprocessError):
                return False
    return False
