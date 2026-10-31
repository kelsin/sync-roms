"""CHD conversion and archive extraction."""
import os
import re
import shutil
import tempfile
import threading
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from types import SimpleNamespace

from . import downloads, external, m3u, store, ui


def chd_folders(systems):
    """{lowercase folder name: system} for the systems with a chd setting, over every layout's folder name."""
    return {f.lower(): s for s in systems if s.get("chd") for f in s["folders"].values() if f}


def sheet_tracks(path):
    """Names of the track files a .cue/.gdi/.toc sheet points at."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if path.lower().endswith(".gdi"):
        names = re.findall(r'^[ \t]*\d+[ \t]+\d+[ \t]+\d+[ \t]+\d+[ \t]+("[^"]+"|\S+)', text, re.M)
        return [n.strip('"') for n in names]
    return re.findall(r'(?:FILE|DATAFILE|AUDIOFILE)\s+"([^"]+)"', text, re.I)


def disc_images(paths):
    """[(image, files it owns)]: each cue/gdi/toc sheet with its tracks, then each .iso no sheet uses."""
    images, used = [], set()
    for p in sorted(paths):
        if p.lower().endswith(external.SHEET_EXTS):
            tracks = [os.path.join(os.path.dirname(p), t) for t in sheet_tracks(p)]
            images.append((p, [p] + tracks))
            used.update(tracks)
    return images + [(p, [p]) for p in sorted(paths) if p.lower().endswith(".iso") and p not in used]


def chd_system(root, dirpath, folders):
    """(system, its outermost folder) for a folder under root: the first path part that names a chd system."""
    rel = os.path.relpath(dirpath, root)
    path = os.path.dirname(root)
    for part in [os.path.basename(root)] + ([] if rel == "." else rel.split(os.sep)):
        path = os.path.join(path, part)
        if part.lower() in folders:
            return folders[part.lower()], path
    return None, None


def plan_chd(root, folders):
    """[(system, system folder, file, owned)] to convert under root: owned is None for an archive, else the
    loose disc image's files (sheet and tracks, or the iso). Extract-only systems have archives only."""
    jobs = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not external.own_temp(d))
        system, sysroot = chd_system(root, dirpath, folders)
        if not system:
            continue
        files = [os.path.join(dirpath, f) for f in sorted(files) if not external.own_temp(f)]
        jobs += [(system, sysroot, f, None) for f in files if f.lower().endswith(external.ARCHIVE_EXTS)]
        if system["chd"]["mode"] != "extract":
            jobs += [(system, sysroot, img, owned) for img, owned in disc_images(files)]
    return jobs


def chd_command_line(chdman, cfg, image, out, np):
    dvd = cfg["mode"] == "dvd" and image.lower().endswith(".iso")
    return [chdman, "createdvd" if dvd else "createcd", "-i", image, "-o", out, "-np", str(np)] + (cfg.get("args", []) if dvd else [])


_chd_locks = defaultdict(threading.Lock)  # one per output path: two jobs for the same disc take turns


def make_chd(tools, cfg, image, out, report=None):
    """Create out from image (an existing out is only verified); None on success, else the error.

    The chd is built under a hidden .part name and renamed once it verifies, so out is never half written.
    report(fraction) gets 0-1 progress: creating is the first 90%, verifying the last 10%.
    """
    chdman = tools["chdman"]

    def stage(start, width):
        return (lambda percent: report(start + percent / 100 * width)) if report else None

    part = os.path.join(os.path.dirname(out), "." + os.path.basename(out) + ".part")
    with _chd_locks[out]:
        if os.path.exists(out):
            return external.run_tool([chdman, "verify", "-i", out], stage(0, 1))
        if os.path.exists(part):  # left by a run that was killed
            os.remove(part)
        error = (external.run_tool(chd_command_line(chdman, cfg, image, part, tools["np"]), stage(0, 0.9))
                 or external.run_tool([chdman, "verify", "-i", part], stage(0.9, 0.1)))
        if error:
            if os.path.exists(part):
                os.remove(part)
            return error
        os.replace(part, out)


def chd_archive(tools, cfg, path, report=None):
    """Extract an archive next to itself, then convert its discs (or, for extract-only systems, move its files out).
    The archive goes only once everything is done; None on success, else the error."""
    folder = os.path.dirname(path)
    tmp = tempfile.mkdtemp(prefix=".chd-", dir=folder)
    try:
        error = external.run_tool([tools["7z"], "x", "-y", "-bso0", "-bsp0", f"-o{tmp}", path])
        if error:
            return error
        extracted = [os.path.join(dp, f) for dp, _, fns in os.walk(tmp) for f in sorted(fns)]
        if cfg["mode"] == "extract":
            names = [os.path.join(folder, os.path.basename(f)) for f in extracted]
            clash = next((n for n in names if os.path.exists(n)), None)
            if clash:
                return f"{os.path.basename(clash)} already exists"
            for f, n in zip(extracted, names):
                shutil.move(f, n)
        else:
            images = disc_images(extracted)
            if not images:
                return "no disc image in the archive"
            for image, _ in images:
                error = make_chd(tools, cfg, image, os.path.join(folder, os.path.splitext(os.path.basename(image))[0] + ".chd"), report)
                if error:
                    return error
        os.remove(path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def chd_image(tools, cfg, image, owned, report=None):
    """Convert one loose disc image and remove its files once the chd verifies; None on success, else the error."""
    error = make_chd(tools, cfg, image, os.path.splitext(image)[0] + ".chd", report)
    if not error:
        for f in owned:
            if os.path.exists(f):
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
            tool = next((t for name in external.TOOL_NAMES["7z"] for t in [shutil.which(name)] if t), None)
            if not tool:
                return "needs 7z to extract (see --install-tools)"
            error = external.run_tool([tool, "x", "-y", "-bso0", "-bsp0", f"-o{tmp}", path])
            if error:
                return error
        for dirpath, _, names in os.walk(tmp):
            for name in sorted(names):
                shutil.move(os.path.join(dirpath, name), os.path.join(folder, name))
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


def remove_stale_chd_temp(root):
    """Delete the .chd-* extraction folders a killed run left behind."""
    for dirpath, dirs, _ in os.walk(root):
        for d in [d for d in dirs if d.startswith(".chd-")]:
            shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)
            dirs.remove(d)


def chd_roots(root, folders):
    """{system folder: system} for every system folder under root: where the m3u playlists get fixed."""
    roots = {}
    for dirpath, dirs, _ in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not external.own_temp(d))
        system, sysroot = chd_system(root, dirpath, folders)
        if system:
            roots[sysroot] = system
    return roots


def fix_playlists(roots, dry_run):
    """Run the --m3u pass on each system folder that has playlists."""
    for sysroot, system in roots.items():
        if system["chd"]["mode"] != "extract" and system["chd"].get("m3u", True):
            m3u.m3u_command(SimpleNamespace(m3u=sysroot, dry_run=dry_run))


def chd_command(args):
    root = os.path.abspath(os.path.expanduser(args.chd or os.getcwd()))
    if not os.path.isdir(root):
        raise SystemExit(ui.red(f"❌ {root} is not a folder"))
    print(ui.bold("💿 chd") + ui.dim(f"  {root}"))
    folders = chd_folders(store.repo_json("systems"))
    roots = chd_roots(root, folders)
    jobs = plan_chd(root, folders)
    if not jobs:
        print(ui.green("✅ Nothing to convert"))
        if not roots:
            print(ui.yellow("⚠️  No folder here is named after a system with a chd setting, so every file was skipped."))
            print(ui.dim(f"   --chd only looks inside folders named: {', '.join(sorted(folders))}"))
    for system, _, path, owned in jobs:
        what = "extract" if system["chd"]["mode"] == "extract" else "convert"
        print(f"  {'📦' if owned is None else '💿'} {what} {os.path.relpath(path, root)}")
    if args.dry_run:
        fix_playlists(roots, True)
        print(ui.yellow("\n🧪 Dry run — nothing changed"))
        return 0
    if not jobs:
        fix_playlists(roots, False)
        return 0
    tools = {}
    for tool, needed in (("7z", any(j[3] is None for j in jobs)), ("chdman", any(j[0]["chd"]["mode"] != "extract" for j in jobs))):
        tools[tool] = external.find_tool(tool)
        if needed and not tools[tool]:
            raise SystemExit(ui.red(f"❌ {tool} not found; run sync-roms --install-tools"))
    remove_stale_chd_temp(root)
    cpus = os.cpu_count() or 1
    workers = min(cpus, len(jobs))
    tools["np"] = max(1, cpus // workers)  # cores left for each chdman once the jobs share them
    print(ui.dim(f"  {workers} at a time, {tools['np']} core(s) each"))

    progress = [0.0] * len(jobs)  # each job's 0-1 progress; the bar is their mean

    def convert(i):
        system, _, path, owned = jobs[i]

        def report(fraction):
            progress[i] = max(progress[i], fraction)

        try:
            if owned:
                return chd_image(tools, system["chd"], path, owned, report)
            return chd_archive(tools, system["chd"], path, report)
        finally:
            progress[i] = 1.0

    bar = ui.ProgressBar(len(jobs), lambda: sum(progress) / len(jobs))
    say = bar.say

    def draw_bar():
        bar.draw(sum(1 for p in progress if p >= 1))

    converted, failed = 0, 0
    pool = ThreadPoolExecutor(workers)
    futures = [pool.submit(convert, i) for i in range(len(jobs))]
    try:
        for job, future in zip(jobs, futures):
            while True:
                try:
                    error = future.result(timeout=0.25)
                    break
                except FutureTimeout:
                    draw_bar()
            name = os.path.relpath(job[2], root)
            if error:
                failed += 1
                say(ui.red(f"  ❌ {name}: {error}") + ui.dim(" (kept)"))
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
        print(ui.yellow(f"  {converted} done, nothing half-converted; run --chd again to continue"))
        return 130
    pool.shutdown()
    bar.clear()
    fix_playlists(roots, False)
    print((ui.red if failed else ui.green)(f"🎉 Done: {converted} converted, {failed} failed"))
    return 1 if failed else 0
