"""The public collections site on GitHub Pages: a clone of its repo in the cache, rebuilt and pushed by `collections publish`."""
import html
import http.client
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request

from . import collections_page, custom_themes, pixel_art_page, s3, store, ui, usersettings

DOMAIN = "sync-roms.games"
DEFAULT_REPO = "git@github.com:kelsin/sync-roms.games.git"
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pages-site")
USER = re.compile(r"[a-z0-9][a-z0-9_-]{0,38}")
GITHUB = re.compile(r"(?:git@github\.com:|ssh://git@github\.com/|https://github\.com/)([^/]+/[^/]+?)(?:\.git)?/?")
RUN_POLL, RUN_WAIT = 5, 120  # seconds between looks for the Pages deploy run, and how long it may take to appear
PAGE_POLL, PAGE_WAIT = 5, 600  # seconds between fetches of the live page, and how long it may take to go live


def CLONE_DIR():
    """The local clone of the Pages repo."""
    return os.path.join(store.data_dir(), "cache", "pages")


def valid_user(name):
    """True when name can be a user's folder: lowercase letters, digits, `-` and `_`, starting with a letter or digit, at most 39."""
    return bool(USER.fullmatch(name))


def url(user):
    return f"https://{DOMAIN}/collections/{user}/"


def _template(name):
    with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as f:
        return f.read()


def build(site_dir, user):
    """Write user's public page into site_dir/collections/<user>/, the pixel art page into site_dir/pixel-art/ and the
    site's shared files: CNAME, .nojekyll, the `collections/` redirect to the root, and the root list of every user
    with a page. ValueError for an invalid user."""
    if not valid_user(user):
        raise ValueError(f"invalid user name: {user!r}")
    collections_dir = os.path.join(site_dir, "collections")
    collections_page.write_public(os.path.join(collections_dir, user), home="/")
    pixel_art_page.write(os.path.join(site_dir, "pixel-art"))
    store.write_text(os.path.join(site_dir, "CNAME"), DOMAIN + "\n")
    store.write_text(os.path.join(site_dir, ".nojekyll"), "")
    store.write_text(os.path.join(collections_dir, "index.html"), _template("redirect.html"))
    users = sorted(name for name in os.listdir(collections_dir)
                   if os.path.isfile(os.path.join(collections_dir, name, "index.html")))
    items = "\n".join(f'    <li><a href="collections/{html.escape(name)}/">{html.escape(name)}</a></li>' for name in users)
    credit = f'<p class="credit"><a href="{html.escape(collections_page.CREDIT_URL)}" rel="noopener">{html.escape(collections_page.CREDIT_TEXT)}</a></p>'
    store.write_text(os.path.join(site_dir, "index.html"), _template("index.html").replace("<!-- users -->", items, 1).replace("<!-- credit -->", credit, 1))


def git(*args, cwd=None, check=True):
    """Run git with args; its stdout. Exits 1 when it isn't installed or, with check, when it fails; without check,
    None when it fails."""
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        ui.fail("git isn't installed", 1)
    if result.returncode:
        if not check:
            return None
        ui.fail(f"git {' '.join(args)} failed: {result.stderr.strip()}", 1)
    return result.stdout


def changes():
    """The clone's staged changes, as `git status --porcelain` lines."""
    return git("status", "--porcelain", cwd=CLONE_DIR()).splitlines()


def publish(user, dry_run=False):
    """Bring the clone to the repo's main (made when the repo is empty), rebuild user's page in it and, unless dry_run,
    commit and push when anything changed. (changed, url); after a dry run, `changes()` lists what would change."""
    repo = usersettings.load_settings().get("pages_repo") or DEFAULT_REPO
    clone = CLONE_DIR()
    if not os.path.isdir(os.path.join(clone, ".git")):
        os.makedirs(os.path.dirname(clone), exist_ok=True)
        git("clone", "-q", "--", repo, clone)
    git("remote", "set-url", "origin", repo, cwd=clone)  # pages_repo may have changed since the clone was made
    git("fetch", "-q", "--prune", "origin", cwd=clone)  # --prune: a former repo's main isn't taken for this one's
    has_main = git("rev-parse", "-q", "--verify", "refs/remotes/origin/main", cwd=clone, check=False) is not None
    if has_main:
        git("checkout", "-q", "-B", "main", "origin/main", cwd=clone)
        git("reset", "-q", "--hard", "origin/main", cwd=clone)
    else:  # an empty repo: start main afresh, dropping a local commit an earlier failed push left
        git("symbolic-ref", "HEAD", "refs/heads/main", cwd=clone)
        git("update-ref", "-d", "refs/heads/main", cwd=clone)
        git("read-tree", "--empty", cwd=clone)
    git("clean", "-q", "-fdx", cwd=clone)
    try:
        build(clone, user)
    except custom_themes.BaseMissing as e:  # the clone is reset at the next publish
        ui.fail(f"The base theme {e.base} isn't in storage, so nothing was published (the pixel art page needs it)", 1)
    except (SystemExit, custom_themes.DownloadFailed, *s3.ERRORS) as e:
        detail = f": {e}" if not isinstance(e, SystemExit) else ""
        ui.fail(f"Storage isn't reachable, so nothing was published (the page would lack tags, sizes and scraped names){detail}", 1)
    git("add", "-A", cwd=clone)
    if not changes():
        return False, url(user)
    if not dry_run:
        git("commit", "-q", "-m", f"publish collections for {user}", cwd=clone)
        git("push", "-q", "origin", "main", cwd=clone)
    return True, url(user)


def github_repo(repo):
    """`owner/repo` of a GitHub git URL (ssh or https); None for any other URL."""
    match = GITHUB.fullmatch(repo)
    return match and match.group(1)


def _gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def _watch_deploy(repo, sha):
    """Watch the Pages deploy run of sha with gh until it ends; exits 1 when it failed. A dim note when gh can't."""
    if not shutil.which("gh") or _gh("auth", "status").returncode:
        print(ui.dim("  gh isn't installed or logged in, so the deploy run isn't watched"))
        return
    deadline = time.monotonic() + RUN_WAIT
    while True:
        result = _gh("run", "list", "-R", repo, "--commit", sha, "--workflow", "pages-build-deployment",
                     "--json", "databaseId,url", "-L", "1")
        try:
            runs = json.loads(result.stdout) if not result.returncode else []
        except ValueError:
            runs = []
        if runs:
            break
        if time.monotonic() >= deadline:
            print(ui.dim("  No Pages deploy run showed up for the push"))
            return
        time.sleep(RUN_POLL)
    if _gh("run", "watch", str(runs[0]["databaseId"]), "-R", repo, "--exit-status").returncode:
        ui.fail(f"The Pages deploy failed: {runs[0]['url']}", 1)


def _fetch(link):
    """The body at link; None on a network error."""
    try:
        with urllib.request.urlopen(link, timeout=30) as response:
            return response.read()
    except (OSError, http.client.HTTPException):
        return None


def wait_live(user):
    """After a push: watch the Pages deploy run (on GitHub, with gh), then fetch user's page until it is the one
    pushed; exits 1 when the run failed or the page isn't live within PAGE_WAIT."""
    print("Waiting for GitHub Pages to deploy…")
    clone = CLONE_DIR()
    sha = git("rev-parse", "HEAD", cwd=clone).strip()
    repo = github_repo(usersettings.load_settings().get("pages_repo") or DEFAULT_REPO)
    if repo:
        _watch_deploy(repo, sha)
    else:
        print(ui.dim("  pages_repo isn't on GitHub, so the deploy run isn't watched"))
    with open(os.path.join(clone, "collections", user, "index.html"), "rb") as f:
        expected = f.read()
    link = f"{url(user)}?v={sha}"
    deadline = time.monotonic() + PAGE_WAIT
    while _fetch(link) != expected:
        if time.monotonic() >= deadline:
            ui.fail(f"{url(user)} isn't live after {round(PAGE_WAIT / 60)} minutes; check the repo's Pages settings", 1)
        time.sleep(PAGE_POLL)
