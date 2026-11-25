"""The adb binary: the only module that runs it."""
import re
import shlex
import shutil
import subprocess
from collections import namedtuple

from . import ui

Device = namedtuple("Device", "serial state model")


class AdbError(Exception):
    pass


def require(mounted=False):
    """The adb path, or exit with how to install it (and, when mounted, how to use a mounted card instead)."""
    path = shutil.which("adb")
    if not path:
        ui.fail("adb isn't installed (brew install android-platform-tools); for a mounted card, pass its folder or "
                "run from it" if mounted else
                "adb isn't installed: brew install android-platform-tools (or install Android platform-tools)", 2)
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


def is_dir(serial, path):
    """Whether the device has the folder; a failed adb raises AdbError rather than reading as missing."""
    return shell(serial, "sh", "-c", 'test -d "$1" && echo y || echo n', "_", path).strip() == "y"


def is_file(serial, path):
    """Whether the device has the file; a failed adb raises AdbError rather than reading as missing."""
    return shell(serial, "sh", "-c", 'test -f "$1" && echo y || echo n', "_", path).strip() == "y"


def forward(serial, remote_port):
    """Forward a free local port to the device's remote_port and return the local port."""
    return int(run("forward", "tcp:0", f"tcp:{remote_port}", serial=serial).strip())


def forward_remove(serial, local_port):
    run("forward", "--remove", f"tcp:{local_port}", serial=serial, check=False)


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
    run("pull", "-a", remote, local, serial=serial, timeout=None)


def push(serial, local, remote):
    run("push", local, remote, serial=serial, timeout=None)


def exec_out(serial, *words):
    """The binary stdout of a command run on the device; a failure raises AdbError."""
    cmd = [require(), "-s", serial, "exec-out", " ".join(shlex.quote(w) for w in words)]
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise AdbError("timed out") from None
    if done.returncode:
        raise AdbError((done.stderr or done.stdout).decode(errors="replace").strip())
    return done.stdout


def install(serial, local, replace=False):
    """Install the APK on the device (replace: upgrade in place, keeping data); a failure raises AdbError."""
    run("install", *(["-r"] if replace else []), local, serial=serial, timeout=None)


def installed_version(serial, pkg):
    """The installed package's versionCode (dumpsys's first), or None when it isn't shown."""
    found = re.search(r"versionCode=(\d+)", shell(serial, "dumpsys", "package", pkg))
    return int(found.group(1)) if found else None
