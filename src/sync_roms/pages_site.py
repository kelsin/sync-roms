"""The public collections site on GitHub Pages: a clone of its repo in the cache, rebuilt and pushed by `collections publish`."""
import html
import os
import re
import subprocess

from . import collections_page, store, ui, usersettings

DOMAIN = "sync-roms.games"
DEFAULT_REPO = "git@github.com:kelsin/sync-roms.games.git"
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pages-site")
USER = re.compile(r"[a-z0-9][a-z0-9_-]{0,38}")


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
    """Write user's public page into site_dir/collections/<user>/ and the site's shared files: CNAME, .nojekyll, the
    `collections/` redirect to the root, and the root list of every user with a page. ValueError for an invalid user."""
    if not valid_user(user):
        raise ValueError(f"invalid user name: {user!r}")
    collections_dir = os.path.join(site_dir, "collections")
    collections_page.write_public(os.path.join(collections_dir, user), home="/")
    store.write_text(os.path.join(site_dir, "CNAME"), DOMAIN + "\n")
    store.write_text(os.path.join(site_dir, ".nojekyll"), "")
    store.write_text(os.path.join(collections_dir, "index.html"), _template("redirect.html"))
    users = sorted(name for name in os.listdir(collections_dir)
                   if os.path.isfile(os.path.join(collections_dir, name, "index.html")))
    items = "\n".join(f'    <li><a href="collections/{html.escape(name)}/">{html.escape(name)}</a></li>' for name in users)
    store.write_text(os.path.join(site_dir, "index.html"), _template("index.html").replace("<!-- users -->", items, 1))


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
    build(clone, user)
    git("add", "-A", cwd=clone)
    if not changes():
        return False, url(user)
    if not dry_run:
        git("commit", "-q", "-m", f"publish collections for {user}", cwd=clone)
        git("push", "-q", "origin", "main", cwd=clone)
    return True, url(user)
