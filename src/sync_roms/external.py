"""External tools (7z, chdman, extract-xiso): lookup, running and install."""
import re
import shutil
import subprocess
import threading

from . import ui


ARCHIVE_EXTS = (".zip", ".7z")
SHEET_EXTS = (".cue", ".gdi", ".toc")  # chdman reads these; the sheet names the track files
TOOL_FORMULAE = {"7z": "sevenzip", "chdman": "rom-tools"}  # Homebrew formula that provides each tool
MANUAL_TOOLS = {"extract-xiso": "build it from https://github.com/XboxDev/extract-xiso (git clone, cmake -B build, cmake --build build) and put the binary on your PATH"}  # no Homebrew formula
TOOL_NAMES = {"7z": ("7zz", "7z", "7za"), "chdman": ("chdman",), "extract-xiso": ("extract-xiso",)}


def find_tool(tool):
    return next((p for p in map(shutil.which, TOOL_NAMES[tool]) if p), None)


def own_temp(name):
    """True for what --chd itself leaves hidden (extraction folders, .part files) and macOS ._ junk; other dot names are real."""
    return name.startswith((".chd-", ".xiso-", ".unzip-", "._")) or name.endswith(".part")


_tool_procs = set()  # running tools, so an interrupt can stop them
_tool_lock = threading.Lock()
_tools_stopped = False


def stop_tools():
    """Terminate the running tools; run_tool starts no new ones afterwards."""
    global _tools_stopped
    with _tool_lock:
        _tools_stopped = True
        for proc in _tool_procs:
            proc.terminate()


PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)% complete")


def run_tool(cmd, progress=None):
    """None on success, else the last line the tool printed; progress(percent) is called as chdman reports it."""
    with _tool_lock:
        if _tools_stopped:
            return "interrupted"
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        _tool_procs.add(proc)
    last = ""
    try:
        for line in proc.stderr:  # chdman ends its progress updates with \r, which text mode reads as a line end
            match = PERCENT_RE.search(line)
            if match and progress:
                progress(float(match.group(1)))
            elif line.strip():
                last = line.strip()
        proc.wait()
    finally:
        with _tool_lock:
            _tool_procs.discard(proc)
    if proc.returncode:
        return last or f"exit code {proc.returncode}"


def install_tools_command():
    brew = shutil.which("brew")
    if not brew:
        raise SystemExit(ui.red("❌ Homebrew (brew) not found; install it from https://brew.sh"))
    wanted = [formula for tool, formula in TOOL_FORMULAE.items() if not find_tool(tool)]
    code = 0
    if wanted:
        print(ui.bold("🍺 brew install ") + " ".join(wanted))
        code = subprocess.run([brew, "install", *wanted]).returncode
    manual = [tool for tool in MANUAL_TOOLS if not find_tool(tool)]
    for tool in manual:
        print(ui.yellow(f"⚠️  {tool} has no Homebrew formula: {MANUAL_TOOLS[tool]}"))
    if not wanted and not manual:
        print(ui.green("✅ 7z, chdman and extract-xiso are already installed"))
    return code
