"""The adb binary: the only module that runs it."""
import shlex
import shutil
import subprocess
from collections import namedtuple

from . import ui

Device = namedtuple("Device", "serial state model")


class AdbError(Exception):
    pass


def require():
    """The adb path, or exit with how to install it."""
    path = shutil.which("adb")
    if not path:
        ui.fail("adb isn't installed: brew install android-platform-tools (or install Android platform-tools)", 2)
    return path


def run(*args, serial=None, check=True, timeout=60):
    """Run adb and return its stdout; a failure raises AdbError when check."""
    cmd = [require()] + (["-s", serial] if serial else []) + list(args)
    try:
        done = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise AdbError("timed out") from None
    if check and done.returncode:
        raise AdbError((done.stderr or done.stdout).strip())
    return done.stdout


def devices():
    out = []
    for line in run("devices", "-l").splitlines()[1:]:
        words = line.split()
        if len(words) < 2:
            continue
        model = next((w[6:].replace("_", " ") for w in words[2:] if w.startswith("model:")), "")
        out.append(Device(words[0], words[1], model))
    return out


def shell(serial, *words, check=True):
    return run("shell", " ".join(shlex.quote(w) for w in words), serial=serial, check=check)


def shell_ok(serial, *words):
    try:
        shell(serial, *words, check=True)
    except AdbError:
        return False
    return True


def prop(serial, name):
    return shell(serial, "getprop", name).strip()


def mdns_services():
    """(name, kind, "host:port") of the services adb discovered."""
    out = []
    for line in run("mdns", "services").splitlines()[1:]:
        fields = line.split()
        if len(fields) == 3:
            out.append(tuple(fields))
    return out


def pair(addr, code):
    run("pair", addr, code)


def connect(addr):
    return "connected to" in run("connect", addr, check=False)


def pull(serial, remote, local):
    run("pull", "-a", remote, local, serial=serial)


def push(serial, local, remote):
    run("push", local, remote, serial=serial)
