"""An Android app's battery-optimization exemption and storage access over adb: what's set, and setting it."""
import re

from . import adb, applied


def entries(serial, package, where):
    """[(Entry, [adb shell words, ...] that set it)]: battery exemption and storage access."""
    whitelist = adb.shell(serial, "dumpsys", "deviceidle", "whitelist")
    result = [(applied.Entry(where, "battery optimization", "exempt" if package in whitelist else "on", "exempt", False),
               [["dumpsys", "deviceidle", "whitelist", f"+{package}"]])]
    if int(adb.shell(serial, "getprop", "ro.build.version.sdk").strip() or 0) >= 30:
        out = adb.shell(serial, "appops", "get", package, "MANAGE_EXTERNAL_STORAGE")
        mode = re.search(r"MANAGE_EXTERNAL_STORAGE:\s*(\w+)", out)
        old = "allow" if "allow" in out else mode.group(1) if mode else "default"
        result.append((applied.Entry(where, "all files access", old, "allow", False),
                       [["appops", "set", package, "MANAGE_EXTERNAL_STORAGE", "allow"]]))
    else:
        granted = "android.permission.WRITE_EXTERNAL_STORAGE: granted=true" in adb.shell(serial, "dumpsys", "package", package)
        result.append((applied.Entry(where, "storage permission", "granted" if granted else None, "granted", False),
                       [["pm", "grant", package, f"android.permission.{permission}"]
                        for permission in ("READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE")]))
    return result


def apply(serial, access):
    """Run the commands of the changed entries of `entries`."""
    for entry, commands in access:
        if applied.changed(entry):
            for words in commands:
                adb.shell(serial, *words)
