"""CHD, xiso and zar conversion and archive extraction."""
import filecmp
import os
import re
import shutil
import tempfile
import threading
import zipfile
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from types import SimpleNamespace

from . import downloads, external, inventory, m3u, runtime, store, ui


def chd_folders(systems):
    """{lowercase folder name: system} for the systems with a `chd` key in systems.json, over every layout's folder name."""
    return {f.lower(): s for s in systems if s.get("chd") for f in s["folders"].values() if f}


def sheet_tracks(path):
    """Names of the track files a .cue/.gdi/.toc sheet points at."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if path.lower().endswith(".gdi"):
        names = re.findall(r'^[ \t]*\d+[ \t]+\d+[ \t]+\d+[ \t]+\d+[ \t]+("[^"]+"|\S+)', text, re.M)
        return [n.strip('"') for n in names]
    return re.findall(r'(?:FILE|DATAFILE|AUDIOFILE)\s+"([^"]+)"', text, re.I)


def disc_images(paths, strict=True, skipped=None):
    """[(image, files it owns)]: each cue/gdi/toc sheet with its tracks, then each .iso no sheet uses.
    strict skips (and appends to skipped) sheets naming tracks outside their folder, since the owned files get deleted."""
    images, used = [], set()
    for p in sorted(paths):
        if p.lower().endswith(external.SHEET_EXTS):
            names = [t.replace("\\", "/") for t in sheet_tracks(p)]
            if strict and any(n != os.path.basename(n) or n in ("", ".", "..") for n in names):
                if skipped is not None:
                    skipped.append(p)
                continue  # a track outside the sheet's folder: don't convert it, and never own (delete) it
            tracks = [os.path.join(os.path.dirname(p), t) for t in names]
            images.append((p, [p] + tracks))
            used.update(tracks)
    return images + [(p, [p]) for p in sorted(paths) if p.lower().endswith(".iso") and p not in used]


CD_ARCHIVE_EXTS = external.ARCHIVE_EXTS + (".rar",)  # --cd also unpacks rars (PSN packs); a sync never does

XISO_TAG_OFFSET, XISO_TAG = 31337, b"in!xiso"  # extract-xiso marks the images it has optimized


def is_optimized_xiso(path):
    try:
        with open(path, "rb") as f:
            f.seek(XISO_TAG_OFFSET)
            return f.read(len(XISO_TAG)) == XISO_TAG
    except OSError:
        return False


def chd_system(root, dirpath, folders):
    """(system, its outermost folder) for a folder under root: the first path part that names a chd system."""
    rel = os.path.relpath(dirpath, root)
    path = os.path.dirname(root)
    for part in [os.path.basename(root)] + ([] if rel == "." else rel.split(os.sep)):
        path = os.path.join(path, part)
        if part.lower() in folders:
            return folders[part.lower()], path
    return None, None


def plan_chd(root, folders, skipped=None, roots=None, stale=None):
    """[(system, system folder, file, owned[, codec])] to convert under root: owned is None for an archive, else the
    loose disc image's files (sheet and tracks, or the iso). Extract-only systems have archives only.
    A .chd not using its system's `codec` is a job too, owning only itself, with the codec to recompress it to as a
    5th item (the chds are inspected in parallel after the walk).
    One walk also fills the out-parameters: skipped gets the sheets skipped for naming tracks outside their folder,
    roots the {system folder: system} for every system folder (where the m3u playlists get fixed), and stale the
    .chd-* and .xiso-* working folders a killed run left behind.
    """
    chdman = external.find_tool("chdman")
    jobs = []
    for dirpath, dirs, files in os.walk(root):
        if stale is not None:
            stale += [os.path.join(dirpath, d) for d in dirs if d.startswith((".chd-", ".xiso-"))]
        dirs[:] = sorted(d for d in dirs if not external.own_temp(d))
        system, sysroot = chd_system(root, dirpath, folders)
        if not system:
            continue
        if roots is not None:
            roots[sysroot] = system
        files = [os.path.join(dirpath, f) for f in sorted(files) if not external.own_temp(f)]
        jobs += [(system, sysroot, f, None) for f in files if f.lower().endswith(CD_ARCHIVE_EXTS)]
        if system["chd"]["mode"] == "xiso":
            jobs += [(system, sysroot, f, [f]) for f in files if f.lower().endswith(".iso") and not is_optimized_xiso(f)]
        elif system["chd"]["mode"] == "zar":
            jobs += [(system, sysroot, f, [f]) for f in files if f.lower().endswith(".iso")]
        elif system["chd"]["mode"] != "extract":
            jobs += [(system, sysroot, img, owned) for img, owned in disc_images(files, True, skipped)]
            if system["chd"].get("codec") and chdman:
                jobs += [(system, sysroot, f, [f], None) for f in files if f.lower().endswith(".chd")]  # codec filled in below
    checking = [i for i, job in enumerate(jobs) if len(job) > 4]
    with ThreadPoolExecutor(min(os.cpu_count() or 4, len(checking) or 1)) as ex:
        codecs = ex.map(lambda i: wrong_codec(chdman, jobs[i][0]["chd"], jobs[i][2]), checking)
        for i, codec in zip(checking, list(codecs)):
            jobs[i] = (*jobs[i][:4], codec) if codec else None
    return [job for job in jobs if job]


def codec_for(cfg, cd):
    """The codec a system's chds must use: its `codec`, which CD chds spell cdzl for zlib; None when unset."""
    codec = cfg.get("codec")
    return "cdzl" if codec == "zlib" and cd else codec


def chd_command_line(chdman, cfg, image, out, np):
    dvd = cfg["mode"] == "dvd" and image.lower().endswith(".iso")
    codec = codec_for(cfg, not dvd)
    return ([chdman, "createdvd" if dvd else "createcd", "-i", image, "-o", out, "-np", str(np)]
            + (cfg.get("args", []) if dvd else []) + (["-c", codec] if codec else []))


def wrong_codec(chdman, cfg, path):
    """The codec to recompress an existing chd to, or None when it already uses only the system's `codec`."""
    info = external.tool_output([chdman, "info", "-i", path])
    match = re.search(r"^Compression:\s*(.+)$", info or "", re.M)
    if not match:
        return None
    used = [c.split()[0] for c in match.group(1).split(",")]
    wanted = codec_for(cfg, "Tag='CH" in info)
    return wanted if wanted and used != [wanted] else None


_chd_locks = defaultdict(threading.Lock)  # one per output path: two jobs for the same disc take turns


def part_path(out):
    """The hidden name a file is written under until it is complete."""
    return os.path.join(os.path.dirname(out), "." + os.path.basename(out) + ".part")


def make_chd(tools, cfg, image, out, report=None):
    """Create out from image (an existing out is only verified, or recompressed if its codec is wrong);
    None on success, else the error.

    The chd is built under a hidden .part name and renamed once it verifies, so out is never half written.
    report(fraction) gets 0-1 progress: creating is the first 90%, verifying the last 10%.
    """
    chdman = tools["chdman"]

    def stage(start, width):
        return (lambda percent: report(start + percent / 100 * width)) if report else None

    part = part_path(out)
    with _chd_locks[out]:
        if os.path.exists(part):  # left by a run that was killed
            os.remove(part)
        if os.path.exists(out):
            codec = wrong_codec(chdman, cfg, out) if cfg.get("codec") else None
            if not codec:
                return external.run_tool([chdman, "verify", "-i", out], stage(0, 1))
            command = [chdman, "copy", "-i", out, "-o", part, "-c", codec, "-np", str(tools["np"])]
        else:
            command = chd_command_line(chdman, cfg, image, part, tools["np"])
        error = (external.run_tool(command, stage(0, 0.9))
                 or external.run_tool([chdman, "verify", "-i", part], stage(0.9, 0.1)))
        if error:
            if os.path.exists(part):
                os.remove(part)
            return error
        os.replace(part, out)


def make_xiso(tools, image, out, report=None, disposable=False):
    """Write image as an optimized xiso at out; None on success, else the error.

    extract-xiso rewrites the image into a hidden folder beside out, and the result replaces out only once it lists
    cleanly, so out (the image itself when converting in place) is never half written. The image is copied there first
    unless it is disposable (just unpacked), since the rewrite deletes it; a disposable image that is already
    optimized is moved there instead.
    """
    xiso = tools["extract-xiso"]
    work = tempfile.mkdtemp(prefix=".xiso-", dir=os.path.dirname(out))
    try:
        copy = os.path.join(work, os.path.basename(image))
        rewrite = image if disposable and not is_optimized_xiso(image) else copy
        if rewrite == copy:  # -r skips an image that is already optimized and writes nothing into -d
            (shutil.move if disposable else shutil.copyfile)(image, copy)
        if report:
            report(0.2)
        error = external.run_tool([xiso, "-q", "-D", "-d", work, "-r", rewrite])
        if report:
            report(0.8)
        error = error or external.run_tool([xiso, "-q", "-l", copy])
        if not error:
            os.replace(copy, out)
        return error
    except OSError as e:
        return str(e)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def make_zar(tools, image, out, report=None):
    """Compress image into the ZArchive out; None on success, else the error.

    iso2zar writes a hidden .part file, renamed once the tool succeeds and the file is not empty,
    so out is never half written. The tool has no verify option or progress output.
    """
    part = part_path(out)
    with _chd_locks[out]:
        try:
            if os.path.exists(part):  # left by a run that was killed
                os.remove(part)
            error = external.run_tool([tools["iso2zar"], image, part], tty=True)
            if not error and (not os.path.exists(part) or os.path.getsize(part) == 0):
                error = "iso2zar wrote nothing"
            if error:
                if os.path.exists(part):
                    os.remove(part)
                return error
            if report:
                report(0.9)
            os.replace(part, out)
        except OSError as e:
            return str(e)


def plan_moves(pairs):
    """([(src, dst)] still to move, error): a dst that already holds a file of the same content is a leftover of an
    interrupted run and is skipped; a duplicate dst or one holding something else is an error."""
    seen, moves = set(), []
    for src, dst in pairs:
        key = os.path.normcase(dst).lower()
        if key in seen:
            return None, f"{os.path.basename(dst)} appears more than once in the archive"
        seen.add(key)
        if not os.path.lexists(dst):
            moves.append((src, dst))
        elif os.path.islink(dst) or not os.path.isfile(dst) or not filecmp.cmp(src, dst, shallow=False):
            return None, f"{os.path.basename(dst)} already exists"
    return moves, None


def move_flat(pairs):
    """Move each (src, dst), skipping leftovers of an interrupted run (see plan_moves); None on success, else the error.
    Each file goes under its hidden .part name first (a copy when src is on another device) and is renamed once whole."""
    moves, error = plan_moves(pairs)
    if error:
        return error
    for src, dst in moves:
        part = part_path(dst)
        try:
            shutil.move(src, part)
            os.replace(part, dst)
        except OSError as e:
            if os.path.lexists(part):
                os.remove(part)
            return str(e)


def convert_all(pairs, clash, make, exists_ok=False):
    """make(image, out) for each (image, out), after checking no two outs are the same file (else the error clash) and
    (unless exists_ok) none exists yet; None on success, else the error."""
    outs = [out for _, out in pairs]
    if len({os.path.normcase(o).lower() for o in outs}) < len(outs):
        return clash
    for out in outs:
        if not exists_ok and os.path.lexists(out):
            return f"{os.path.basename(out)} already exists"
    for image, out in pairs:
        error = make(image, out)
        if error:
            return error


UNPACKED = 0.2  # an archive job's progress once it is unpacked; its discs share the rest
NESTED_DEPTH = 3  # archives inside archives (a PSN rar holding a rar) are extracted this many levels down


def extract_command(tools, path, out):
    """unar for a rar when it is installed (7-Zip can't decode some RAR 2.9 archives), else 7z."""
    if path.lower().endswith(".rar") and tools.get("unar"):
        return [tools["unar"], "-q", "-f", "-D", "-o", out, path]
    return [tools["7z"], "x", "-y", "-bso0", "-bsp0", f"-o{out}", "--", path]


def extracted_files(tmp):
    return [os.path.join(dp, f) for dp, _, fns in os.walk(tmp) for f in sorted(fns) if not os.path.islink(os.path.join(dp, f))]


def chd_archive(tools, cfg, path, report=None, scratch=None):
    """Extract an archive into scratch (default: next to itself), and the archives inside it, but not for extract-only
    systems, then convert its discs beside the archive (or, for extract-only systems, move its files out).
    The archive goes only once everything is done; None on success, else the error.
    report(fraction) gets 0-1 progress: UNPACKED once unpacked, then each disc converts its share of the rest."""
    folder = os.path.dirname(path)

    def disc(image):  # report for one disc of pairs, scaled to its share
        k = [i for i, _ in pairs].index(image)
        return (lambda f: report(UNPACKED + (1 - UNPACKED) * (k + f) / len(pairs))) if report else None

    tmp = tempfile.mkdtemp(prefix=f".chd-{os.getpid()}-", dir=scratch or folder)
    try:
        error = external.run_tool(extract_command(tools, path, tmp))
        if error:
            return error
        extracted = extracted_files(tmp)
        for _ in range(NESTED_DEPTH if cfg["mode"] != "extract" else 0):  # extract-only systems keep inner archives
            inner = [f for f in extracted if f.lower().endswith(CD_ARCHIVE_EXTS)]
            if not inner:
                break
            for f in inner:  # an old-style split rar's .r00, .r01, ... volumes beside it are read too
                out = tempfile.mkdtemp(prefix=".chd-", dir=os.path.dirname(f))
                error = external.run_tool(extract_command(tools, f, out))
                if error:
                    return f"{os.path.basename(f)} in the archive: {error}"
                os.remove(f)
            extracted = extracted_files(tmp)
        if report:
            report(UNPACKED)
        if cfg["mode"] == "extract":
            error = move_flat([(f, os.path.join(folder, os.path.basename(f))) for f in extracted])
        elif cfg["mode"] in ("xiso", "zar"):
            images = [f for f in extracted if f.lower().endswith(".iso")]
            if not images:
                return "no iso in the archive"
            if cfg["mode"] == "xiso":
                pairs = [(image, os.path.join(folder, os.path.basename(image))) for image in images]
                error = convert_all(pairs, "two isos in the archive would make the same file",
                                    lambda image, out: make_xiso(tools, image, out, disc(image), disposable=True))
            else:
                pairs = [(image, os.path.join(folder, os.path.splitext(os.path.basename(image))[0] + ".zar")) for image in images]
                error = convert_all(pairs, "two isos in the archive would make the same .zar",
                                    lambda image, out: make_zar(tools, image, out, disc(image)))
        else:
            images = disc_images(extracted, strict=False)
            kept = [f for f in extracted if f.lower().endswith(tuple(cfg.get("keep", ())))]
            if not images and not kept:
                return "no disc image in the archive"
            pairs = [(image, os.path.join(folder, os.path.splitext(os.path.basename(image))[0] + ".chd")) for image, _ in images]
            error = convert_all(pairs, "two discs in the archive would make the same .chd",
                                lambda image, out: make_chd(tools, cfg, image, out, disc(image)), exists_ok=True)
            if not error:
                error = move_flat([(f, os.path.join(folder, os.path.basename(f))) for f in kept])
        if error:
            return error
        os.remove(path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def unpacked_size(tools, path):
    """Bytes a .zip or .7z unpacks to, from its listing; None when that isn't known (a .rar, an archive inside it, which
    is unpacked too, or a listing that fails)."""
    try:
        if path.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                entries = [(i.filename, i.file_size) for i in z.infolist() if not i.is_dir()]
        elif path.lower().endswith(".7z"):
            listing = external.tool_output([tools["7z"], "l", "-slt", "--", path])
            if not listing or "\n----------\n" not in listing:
                return None
            blocks = [dict(re.findall(r"^(\w[\w ]*?) = (.*)$", b, re.M)) for b in listing.split("\n----------\n", 1)[1].split("\n\n")]
            entries = [(b["Path"], int(b.get("Size") or 0)) for b in blocks if "Path" in b and b.get("Folder") != "+"]
        else:
            return None
    except (OSError, ValueError, zipfile.BadZipFile):
        return None
    if any(name.lower().endswith(CD_ARCHIVE_EXTS) for name, _ in entries):
        return None
    return sum(size for _, size in entries)


def job_scratch(tools, jobs):
    """(per job, the folder its archive unpacks in, None for beside itself; how many jobs can run at once; per job, its size).

    A converting archive whose unpacked size is known unpacks in the system temp folder when that is on another device
    than the archive and has room for it plus a margin; plain extraction always unpacks beside the archive. Each job's scratch (its
    unpacked size, else the archive's size, or a loose image's size) counts on the volume it uses, and only as many jobs
    run as the biggest ones' scratch fits in each volume's free space, at least one. That scratch is also the job's size.
    """
    temp = tempfile.gettempdir()
    temp_dev = os.stat(temp).st_dev
    with ThreadPoolExecutor(min(os.cpu_count() or 4, len(jobs))) as ex:
        sizes = list(ex.map(lambda job: unpacked_size(tools, job[2]) if job[3] is None else None, jobs))
    temp_free = shutil.disk_usage(temp).free
    free = {temp_dev: temp_free}  # device: free bytes, from the first path seen on it
    needs = defaultdict(list)  # device: each of its jobs' scratch bytes
    scratch, job_sizes = [], []
    for (system, _, path, owned, *_), size in zip(jobs, sizes):
        dev = os.stat(os.path.dirname(path)).st_dev
        if dev not in free:
            free[dev] = shutil.disk_usage(os.path.dirname(path)).free
        local = (owned is None and system["chd"]["mode"] != "extract" and size is not None and dev != temp_dev
                 and size + max(temp_free // 10, 2 ** 30) <= temp_free)  # a margin: temp is often the system drive
        scratch.append(temp if local else None)
        if size is None:
            size = sum(os.path.getsize(f) for f in owned or [path] if os.path.isfile(f))
        needs[temp_dev if local else dev].append(size)
        job_sizes.append(size)
    fits = [len(n) for n in needs.values()]
    for dev, need in needs.items():
        total = 0
        for i, size in enumerate(sorted(need, reverse=True)):
            total += size
            if total > free[dev]:
                fits.append(i)
                break
    return scratch, max(1, min(fits)), job_sizes


def stale_local_scratch():
    """The .chd-<pid>-* folders in the system temp folder left by a convert run that is no longer running."""
    temp = tempfile.gettempdir()
    stale = []
    for name in os.listdir(temp):
        match = re.match(r"\.chd-(\d+)-", name)
        if match:
            try:
                os.kill(int(match.group(1)), 0)
            except ProcessLookupError:
                stale.append(os.path.join(temp, name))
            except OSError:
                pass  # running, as another user
    return stale


def chd_image(tools, cfg, image, owned, report=None):
    """Convert one loose disc image and remove its files once the chd verifies; None on success, else the error.
    An xiso system's iso is rewritten in place instead, and a zar system's iso becomes a .zar."""
    if cfg["mode"] == "xiso":
        return make_xiso(tools, image, image, report)
    if cfg["mode"] == "zar":
        out = os.path.splitext(image)[0] + ".zar"
        if os.path.lexists(out):
            return f"{os.path.basename(out)} already exists"
        error = make_zar(tools, image, out, report)
        if not error:
            os.remove(image)
        return error
    out = os.path.splitext(image)[0] + ".chd"
    error = make_chd(tools, cfg, image, out, report)
    if not error:
        for f in owned:
            if os.path.normcase(f).lower() != os.path.normcase(out).lower() and os.path.exists(f):
                os.remove(f)
    return error


def unzip_archive(path):
    """Extract an archive's files next to it, without subfolders, and delete it. None on success, else the error."""
    folder = os.path.dirname(path)
    tmp = tempfile.mkdtemp(prefix=".unzip-", dir=folder)
    try:
        if path.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                z.extractall(tmp)
        else:
            tool = external.find_tool("7z")
            if not tool:
                return "needs 7z to extract (see --install-tools)"
            error = external.run_tool([tool, "x", "-y", "-bso0", "-bsp0", f"-o{tmp}", "--", path])
            if error:
                return error
        error = move_flat([(os.path.join(dp, n), os.path.join(folder, n)) for dp, _, ns in os.walk(tmp)
                           for n in sorted(ns) if not os.path.islink(os.path.join(dp, n))])
        if error:
            return error
        os.remove(path)
    except (OSError, zipfile.BadZipFile) as e:
        return str(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def card_archives(dests):
    """Archives still sitting in the given ROM folders, e.g. left by an interrupted run."""
    return [os.path.join(root, f) for dest in dests if os.path.isdir(dest)
            for root, files in downloads.walk_roms(dest) for f in files if f.lower().endswith(external.ARCHIVE_EXTS)]


def unzip_roms(paths):
    """Extract the archives among the downloaded paths, a few at a time. Returns [(path, error)] for the ones that failed."""
    archives = [p for p in paths if p.lower().endswith(external.ARCHIVE_EXTS) and os.path.exists(p)]
    failures = []
    if archives:
        print(ui.bold(f"\n📦 Extracting {len(archives)} archive(s)"), flush=True)
    with ThreadPoolExecutor(min(4, len(archives) or 1)) as ex:
        for i, (path, error) in enumerate(zip(archives, ex.map(unzip_archive, archives)), 1):
            print(f"  {ui.dim(f'[{i}/{len(archives)}]')} {ui.red('❌') if error else '✅'} {os.path.basename(path)}", flush=True)
            if error:
                failures.append((path, error))
    return failures


def remove_stale_chd_temp(folders):
    """Delete the .chd-* and .xiso-* working folders a killed run left behind (as found by plan_chd and stale_local_scratch)."""
    for folder in folders:
        shutil.rmtree(folder, ignore_errors=True)


def fix_playlists(roots, dry_run):
    """Run the --m3u pass on each system folder that has playlists."""
    for sysroot, system in roots.items():
        if system["chd"].get("m3u", True):
            m3u.m3u_command(SimpleNamespace(m3u=sysroot, dry_run=dry_run))


def warn_on_card(root, dry_run):
    """Warn when root is inside a saved card's folder and, unless a dry run, ask to go on (default no; exits on no)."""
    cards = store.load_cards()
    card = next((part for part in root.split(os.sep) if part in cards), None)
    if not card:
        return
    ui.failure(ui.yellow(f"⚠️  {root} is on the card {card}: the next sync lists the converted files as not in the game list "
                         "and downloads the archives and images again. Convert before files go on a card."))
    if not dry_run and not ui.confirm("Convert on the card anyway?", default=False):
        ui.fail(f"Not converting on the card {card}", 1)


def chd_command(args):
    root = os.path.abspath(os.path.expanduser(args.chd or os.getcwd()))
    if not os.path.isdir(root):
        ui.fail(f"{root} is not a folder", 2)
    print(ui.bold("💿 cd") + ui.dim(f"  {root}"))
    folders = chd_folders(store.repo_json("systems"))
    roots, skipped, stale = {}, [], []
    jobs = plan_chd(root, folders, skipped, roots, stale)
    for sheet in skipped:
        print(ui.yellow(f"  ⚠️  skipped {os.path.relpath(sheet, root)}: it names tracks outside its own folder"))
    if not jobs:
        print(ui.green("✅ Nothing to convert"))
        if not roots:
            print(ui.yellow("⚠️  No folder here is named after a system that converts to CHD, so every file was skipped."))
            print(ui.dim(f"   --cd only looks inside folders named: {', '.join(sorted(folders))}"))
    for system, _, path, owned, *_ in jobs:
        what = "extract" if system["chd"]["mode"] == "extract" else "convert"
        print(f"  {'📦' if owned is None else '💿'} {what} {os.path.relpath(path, root)}")
    if jobs:
        warn_on_card(root, args.dry_run)
    if args.dry_run:
        fix_playlists(roots, True)
        print(ui.yellow("\n🧪 Dry run — nothing changed"))
        return 0
    if not jobs:
        fix_playlists(roots, False)
        return 0
    tools = {}
    modes = {j[0]["chd"]["mode"] for j in jobs}
    for tool, needed in (("7z", any(j[3] is None for j in jobs)), ("unar", False), ("chdman", bool(modes - {"extract", "xiso", "zar"})),
                         ("extract-xiso", "xiso" in modes), ("iso2zar", "zar" in modes)):
        tools[tool] = external.find_tool(tool)
        if needed and not tools[tool]:
            ui.fail(f"{tool} not found; " + (f"{external.MANUAL_TOOLS[tool]}" if tool in external.MANUAL_TOOLS else "run sync-roms --install-tools"), 3)
    remove_stale_chd_temp(stale + stale_local_scratch())
    cpus = os.cpu_count() or 1
    scratch, fit, sizes = job_scratch(tools, jobs)
    weights = [max(1, size) for size in sizes]
    total = sum(weights)
    workers = min(cpus, len(jobs), fit)
    tools["np"] = max(1, cpus // workers)  # cores left for each chdman once the jobs share them
    print(ui.dim(f"  {len(jobs)} to convert ({ui.human_size(total)}), {workers} at a time, {tools['np']} core(s) each" + (" (limited by free space)" if fit < min(cpus, len(jobs)) else "")))

    progress = [0.0] * len(jobs)  # each job's 0-1 progress; the bar weighs them by size

    def convert(i):
        system, _, path, owned, *_ = jobs[i]

        def report(fraction):
            progress[i] = max(progress[i], fraction)

        try:
            if owned:
                return chd_image(tools, system["chd"], path, owned, report)
            return chd_archive(tools, system["chd"], path, report, scratch[i])
        finally:
            progress[i] = 1.0

    bar = ui.ProgressBar(len(jobs), lambda: sum(p * w for p, w in zip(progress, weights)) / total, total)
    say = bar.say

    def draw_bar():
        bar.draw(sum(1 for p in progress if p >= 1))

    converted, failed = 0, 0
    pool = ThreadPoolExecutor(workers)
    futures = {pool.submit(convert, i): i for i in sorted(range(len(jobs)), key=lambda i: -weights[i])}  # biggest first
    pending = set(futures)
    try:
        while pending:
            finished, pending = wait(pending, timeout=ui.POLL, return_when=FIRST_COMPLETED)
            for future in finished:
                error = future.result()
                name = os.path.relpath(jobs[futures[future]][2], root)
                if error:
                    failed += 1
                    line = ui.red(f"  ❌ {name}: {error}") + ui.dim(" (kept)")
                    if ui.QUIET:
                        ui.failure(line)
                    else:
                        say(line)
                else:
                    converted += 1
                    say(f"  ✅ {name}")
            draw_bar()
    except KeyboardInterrupt:
        say(ui.yellow("🛑 Interrupted, stopping and cleaning up..."))
        for future in futures:
            future.cancel()
        while True:  # the running jobs remove their partial files as the tools stop
            external.stop_tools()
            try:
                pool.shutdown(wait=True)
                break
            except KeyboardInterrupt:
                pass
        print(ui.yellow(f"  {converted} done, nothing half-converted; run --cd again to continue"))
        hint_cache_update(root, converted)
        return 130
    pool.shutdown()
    bar.clear()
    fix_playlists(roots, False)
    if failed:
        ui.failure(ui.red(f"🎉 Done: {converted} converted, {failed} failed"))
    else:
        print(ui.green(f"🎉 Done: {converted} converted, {failed} failed"))
    hint_cache_update(root, converted)
    return 1 if failed else 0


def hint_cache_update(root, converted):
    """Say to refresh the storage cache when root is inside the storage folder and a job there succeeded, changing its files."""
    if converted and runtime.ROOT and os.path.commonpath([root, runtime.ROOT]) == runtime.ROOT:
        print(ui.yellow(f"⚠️  This is in the storage folder, so the storage cache is out of date: run {inventory.UPDATE_HINT}"))
