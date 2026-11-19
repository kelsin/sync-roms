# `sync-roms flash`: write a Knulli image to an SD card

## Why

Knulli devices use a separate card for ROMs, so the OS card only ever needs a clean flash of a Knulli image from
storage. Today that's done by hand. The command picks the image, writes it safely and checks the write, so a bad
flash or the wrong disk can't happen silently.

## Goals

- Pick a Knulli device, then a Knulli image from storage's `os/`, then an SD card.
- Copy the image to a local temp folder first, so a network drop can't break a half-written card.
- Write with `sudo dd`, check the card against the image, and leave the card flushed, unmounted and ejected.
- Be fast: the card's write speed should be the only limit.

## Non-goals

- Non-Knulli firmwares, and Linux or Windows (macOS only, like the existing eject code).
- Registering the card in `cards.json`, or anything else about syncing. Nothing is written to storage.

## Anti-goals

- Ever writing to the internal disk, the disk holding the temp folder, or a disk the user didn't type the id of.
- Leaving the temp image, a mounted card, or a running `dd` behind, including on failure or Ctrl-C.

## Approaches

1. **Python subcommand (picked).** It reuses the pickers, `s3.download` (NAS folder or S3), `devices.json` and the
   `diskutil` code in `clean.py`.
2. A shell script in `tools/`. It would duplicate the storage access and device data.
3. Stream `gunzip | dd` straight from storage. It's fragile if the network drops, which is why a local copy is required.

## Design

New module `flash.py`, `sync-roms flash [--dry-run]`, added to `SUBCOMMANDS`, `TOPICS` and shell completion.

1. **Device.** The picker lists devices whose `firmwares` include `knulli`.
2. **Image.** These are the keys in `inventory.files("os/")` that match `knulli-*.img.gz`. Images whose device part
   matches the device id come first. Matching compares names with dashes removed and the vendor prefix dropped:
   `anbernic-rg35xxh` matches `knulli-h700-rg35xx-h-…`. Within each group the newest date comes first. Every image is
   listed, since one image serves several devices.
3. **Card.** The candidates come from `diskutil list -plist external physical`, each with its size and media name from
   `diskutil info -plist`. The disk holding the temp folder is left out, and the command refuses to go on if no card is
   left. You confirm by typing the disk id (e.g. `disk4`). Anything else aborts.
4. `--dry-run` stops here and prints what would happen.
5. **sudo.** `sudo -v` runs up front, so the password prompt doesn't break the progress lines.
6. **Copy.** The free space in the temp folder is checked first. Then `s3.download` copies the `.img.gz` into a
   `tempfile.TemporaryDirectory()`, with a progress line.
7. **Write.** `diskutil unmountDisk` runs, then Python decompresses the local `.gz` (`gzip`, 4 MiB chunks) and pipes it
   into `sudo dd of=/dev/rdiskN bs=4m`. While writing, it counts bytes and keeps a SHA-256 of the image, and shows
   progress. No decompressed copy is kept on disk.
8. **Flush.** `sync` runs, then `diskutil unmountDisk` again, because macOS remounts the new partitions.
9. **Check.** `sudo dd if=/dev/rdiskN bs=16m` reads back exactly the number of bytes written, and the SHA-256 of what
   it reads is compared with the image's. A mismatch is reported as a failed flash, with a non-zero exit.
10. **Clean up.** This runs in `finally` on success, failure or Ctrl-C. It kills `dd` if it is still running, removes
    the temp folder, runs `sync`, and then runs `diskutil eject` on the disk (or `unmountDisk` after a failure, so you
    can retry).

## Left to the builder

- Wording of the prompts and progress lines, following `ui`'s existing style.
- Tests for image matching and sorting, `diskutil` plist filtering, and the write/check hashing with fake streams.
  No real `dd` runs in tests.
