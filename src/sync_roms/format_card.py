"""Erase an SD card on macOS as exFAT or FAT32 with a picked label."""
import re
import sys

from . import flash, picker, runtime, store, ui

FILESYSTEMS = [("exFAT", "ExFAT"), ("FAT32", "FAT32")]  # shown name, diskutil name
MAX_LENGTH = {"exFAT": 15, "FAT32": 11}
BAD_CHARS = {"exFAT": r'["*/:<>?\\|\x00-\x1f\x7f]', "FAT32": r'["*+,./:;<=>?\[\\\]|\x00-\x1f\x7f]'}
TYPE_LABEL = "✏️  Type a label…"


def clean_label(label, fs):
    """The label without surrounding whitespace; FAT32 labels are uppercase."""
    label = label.strip()
    return label.upper() if fs == "FAT32" else label


def label_problem(label, fs):
    """None when the (cleaned) label is valid for the filesystem, else a short reason."""
    if not label.strip():
        return "the label is empty"
    if len(label) > MAX_LENGTH[fs]:
        return f"{fs} labels are at most {MAX_LENGTH[fs]} characters"
    bad = re.search(BAD_CHARS[fs], label)
    return f"{fs} labels can't contain {bad.group()!r}" if bad else None


def label_choices(fs):
    """Card names (sorted), then layout names uppercased, as valid {fs} labels without repeats."""
    names = sorted(store.load_cards(), key=str.casefold) + [k.upper() for k in store.repo_json("layouts")]
    found = []
    for name in names:
        name = clean_label(name, fs)
        if label_problem(name, fs) is None and name not in found:
            found.append(name)
    return found


def erase_command(disk_id, fs, label):
    return ["diskutil", "eraseDisk", dict(FILESYSTEMS)[fs], label, "MBR", disk_id]


def _pick_label(fs):
    """The picked or typed label, or None on Esc or an empty typed label."""
    choices = label_choices(fs)
    i = picker.filter_list("🏷️  Which label?", choices + [TYPE_LABEL], hint=flash.HINT)
    if i is None:
        return None
    if i < len(choices):
        return choices[i]
    while True:
        label = clean_label(ui.ask("Label: "), fs)
        if not label:
            return None
        problem = label_problem(label, fs)
        if problem is None:
            return label
        ui.failure(ui.red(f"❌ {problem}"))


def run(args):
    """Pick an SD card, a filesystem and a label, erase the card. 0 on success, dry run or Esc; 1 on any failure."""
    if sys.platform != "darwin":
        ui.failure(ui.red("❌ format needs macOS"))
        return 1
    exclude = flash.disks_of("/")
    if not exclude:  # "/" sits on a local disk, so finding none means diskutil failed
        ui.failure(ui.red("❌ couldn't tell which disk holds /: not formatting"))
        return 1
    if runtime.ROOT:
        exclude |= flash.disks_of(runtime.ROOT)
    cards = flash.external_disks(exclude)
    if not cards:
        ui.failure(ui.red("❌ no SD card found"))
        return 1
    if args.dry_run:
        print(ui.yellow("🧪 Dry run: nothing is erased"))
    i = picker.filter_list("🃏 Which SD card?", [flash._disk_label(d) for d in cards], hint=flash.HINT)
    if i is None:
        return 0
    disk = cards[i]
    i = picker.filter_list("💽 Which filesystem?", [name for name, _ in FILESYSTEMS], hint=flash.HINT)
    if i is None:
        return 0
    fs = FILESYSTEMS[i][0]
    label = _pick_label(fs)
    if label is None:
        return 0
    size = "?" if disk.size is None else ui.human_size(disk.size)
    volumes = f": {', '.join(disk.volumes)}" if disk.volumes else ""
    info = f"{disk.id} ({size}, {disk.name}{volumes})"
    print(ui.yellow(f"⚠️  {info} would be erased and formatted {fs} named {label}." if args.dry_run
                    else f"⚠️  Everything on {info} will be erased and formatted {fs} named {label}."))
    prompt = (f"Type {disk.id} to see the rest of the dry run (nothing is erased): " if args.dry_run
              else f"Type {disk.id} to format it: ")
    if ui.ask(prompt).strip() != disk.id:
        ui.failure(ui.red("❌ Not formatted"))
        return 0
    command = erase_command(disk.id, fs, label)
    if args.dry_run:
        print(f"Would run: {' '.join(command)}")
        return 0
    if not flash._sudo():
        return 1
    if not any(flash._same(disk, d) for d in flash.external_disks(exclude)):  # disk numbers are reused: a swapped card could be another drive
        ui.failure(ui.red(f"❌ {disk.id} changed since you picked it: not formatted"))
        return 1
    r = flash._run(["sudo", *command])
    if r.returncode != 0:
        ui.failure(ui.red(f"❌ format failed: {(r.stderr or r.stdout).strip()}"))
        return 1
    print(ui.green(f"✅ Formatted {disk.id} as {fs} named {label}"))
    return 0
