import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from sync_roms import collections, collections_page, custom_themes, inventory, pages_site, pixel_art_page, runtime, scrape_plan, tags, usersettings  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com"}


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


REAL_PIXEL_ART_WRITE = pixel_art_page.write
REAL_WAIT_LIVE = pages_site.wait_live


def stub_pixel_art(out_dir, base_dir=None):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write("pixel art")


def git_ls_tree(repo, ref):
    """The files at ref in repo; [] when ref doesn't exist (or the repo is gone)."""
    result = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", ref], capture_output=True, text=True)
    return result.stdout.split() if result.returncode == 0 else []


class SiteCase(helpers.Cmd):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.dict(os.environ, GIT_ENV))
        self.enterContext(mock.patch.object(tags, "load", lambda: {"tags": {}, "games": {}, "declined": {}}))
        self.enterContext(mock.patch.object(inventory, "files", lambda prefix, sizes=True: {}))
        self.enterContext(mock.patch.object(scrape_plan, "load_metadata", lambda system, fresh=False: {}))
        self.enterContext(mock.patch.object(pixel_art_page, "write", stub_pixel_art))
        self.wait_live = self.enterContext(mock.patch.object(pages_site, "wait_live"))
        self.bare = os.path.join(self.tmpdir(), "site.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.bare], check=True)
        usersettings.save_settings({"pages_repo": self.bare})
        self.save_collection("Mario")

    def tmpdir(self):
        return self.enterContext(tempfile.TemporaryDirectory())

    def save_collection(self, name):
        collections.save_collection({"id": name.lower(), "name": name, "description": "d", "art": "mario",
                                     "games": [{"system": "snes", "bucket": "snes/Super Mario World (USA).zip", "title": "SMW"}]})



class Site(SiteCase):
    def test_build_layout(self):
        site = self.tmpdir()
        os.makedirs(os.path.join(site, "collections", "alice"))
        open(os.path.join(site, "collections", "alice", "index.html"), "w").close()
        os.makedirs(os.path.join(site, "collections", "nopage"))
        pages_site.build(site, "kelsin")
        self.assertEqual(read(site, "CNAME").strip(), "sync-roms.games")
        self.assertTrue(os.path.exists(os.path.join(site, ".nojekyll")))
        root = read(site, "index.html")
        self.assertIn('href="collections/alice/"', root)
        self.assertIn('href="collections/kelsin/"', root)
        self.assertNotIn("nopage", root)
        self.assertLess(root.index("alice"), root.index("kelsin"))
        self.assertIn(collections_page.CREDIT_URL, root)
        self.assertIn(collections_page.CREDIT_TEXT, root)
        self.assertIn('url=/', read(site, "collections", "index.html"))
        self.assertTrue(os.path.isfile(os.path.join(site, "collections", "kelsin", "page.js")))
        self.assertNotIn("Super Mario World (USA).zip", read(site, "collections", "kelsin", "index.html"))
        self.assertTrue(os.path.isfile(os.path.join(site, "pixel-art", "index.html")))
        self.assertIn('href="pixel-art/"', root)

    def test_publish_fails_without_base(self):
        self.enterContext(mock.patch.object(pixel_art_page, "write", REAL_PIXEL_ART_WRITE))
        self.enterContext(mock.patch.object(custom_themes, "fetch_base", side_effect=custom_themes.BaseMissing("SPRUCE")))
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as raised:
            pages_site.publish("kelsin")
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("The base theme SPRUCE isn't in storage, so nothing was published", err.getvalue())
        self.assertEqual(git_ls_tree(self.bare, "main"), [])

    def test_publish_fails_when_base_download_fails(self):
        self.enterContext(mock.patch.object(pixel_art_page, "write", REAL_PIXEL_ART_WRITE))
        self.enterContext(mock.patch.object(custom_themes, "fetch_base", side_effect=custom_themes.DownloadFailed("x")))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            pages_site.publish("kelsin")
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(git_ls_tree(self.bare, "main"), [])

    def test_invalid_users_refused(self):
        for name in ("Kelsin", "a b", "../x", "a/b", "", "-x", "a" * 40):
            self.assertFalse(pages_site.valid_user(name), name)
        for name in ("kelsin", "a", "a-b_c9", "a" * 39):
            self.assertTrue(pages_site.valid_user(name), name)
        code, _, err = self.run_cmd("collections", "publish", "--user", "../x")
        self.assertEqual(code, 2)
        self.assertIn("--user", err)

    def test_first_publish_to_empty_repo_then_no_change(self):
        changed, url = pages_site.publish("kelsin")
        self.assertTrue(changed)
        self.assertEqual(url, "https://sync-roms.games/collections/kelsin/")
        files = git_ls_tree(self.bare, "main")
        for name in ("collections/kelsin/index.html", "collections/index.html", "index.html", "CNAME", ".nojekyll"):
            self.assertIn(name, files)
        self.assertFalse(pages_site.publish("kelsin")[0])

    def test_other_users_folders_kept(self):
        pages_site.publish("alice")
        pages_site.publish("kelsin")
        files = git_ls_tree(self.bare, "main")
        self.assertIn("collections/alice/index.html", files)
        self.assertIn("collections/kelsin/index.html", files)
        root = subprocess.run(["git", "-C", self.bare, "show", "main:index.html"], capture_output=True, text=True).stdout
        self.assertIn('href="collections/alice/"', root)

    def test_changed_repo_setting_is_used(self):
        pages_site.publish("alice")
        second = os.path.join(self.tmpdir(), "second.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", second], check=True)
        usersettings.save_settings({"pages_repo": second})
        self.assertTrue(pages_site.publish("kelsin")[0])
        files = git_ls_tree(second, "main")
        self.assertIn("collections/kelsin/index.html", files)
        self.assertNotIn("collections/alice/index.html", files)  # the old repo's main isn't carried over
        self.assertNotIn("collections/kelsin/index.html", git_ls_tree(self.bare, "main"))

    def test_build_refuses_invalid_user(self):
        with self.assertRaises(ValueError):
            pages_site.build(self.tmpdir(), "../x")

    def test_login_name_unavailable(self):
        for error in (OSError("no login"), KeyError("no login"), ImportError("no pwd")):
            with mock.patch("getpass.getuser", side_effect=error):
                code, _, err = self.run_cmd("collections", "publish")
            self.assertEqual(code, 2, error)
            self.assertIn("--user", err)

    def test_dirty_clone_is_reset(self):
        pages_site.publish("kelsin")
        open(os.path.join(pages_site.CLONE_DIR(), "junk.txt"), "w").close()
        self.save_collection("Another")
        self.assertTrue(pages_site.publish("kelsin")[0])
        self.assertNotIn("junk.txt", git_ls_tree(self.bare, "main"))

    def test_dry_run_pushes_nothing(self):
        changed, _ = pages_site.publish("kelsin", dry_run=True)
        self.assertTrue(changed)
        self.assertEqual(git_ls_tree(self.bare, "main"), [])

    def test_failed_first_push_is_retried(self):
        hook = self.reject_pushes()
        code, _, _ = self.run_cmd("collections", "publish", "--user", "kelsin")
        self.assertEqual(code, 1)
        os.remove(hook)
        self.assertTrue(pages_site.publish("kelsin")[0])
        self.assertIn("collections/kelsin/index.html", git_ls_tree(self.bare, "main"))

    def reject_pushes(self):
        hook = os.path.join(self.bare, "hooks", "pre-receive")
        with open(hook, "w") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(hook, 0o755)
        return hook

    def test_failed_later_push_is_retried(self):
        pages_site.publish("kelsin")
        hook = self.reject_pushes()
        self.save_collection("Another")
        self.assertEqual(self.run_cmd("collections", "publish", "--user", "kelsin")[0], 1)
        os.remove(hook)
        self.assertTrue(pages_site.publish("kelsin")[0])
        page = subprocess.run(["git", "-C", self.bare, "show", "main:collections/kelsin/index.html"],
                              capture_output=True, text=True).stdout
        self.assertIn("Another", page)

    def test_unreachable_storage_publishes_nothing(self):
        pages_site.publish("kelsin")
        before = subprocess.run(["git", "-C", self.bare, "rev-parse", "main"], capture_output=True, text=True).stdout
        self.save_collection("Another")
        with mock.patch.object(tags, "load", side_effect=SystemExit(3)):
            code, _, err = self.run_cmd("collections", "publish", "--user", "kelsin")
        self.assertEqual(code, 1)
        self.assertIn("Storage isn't reachable", err)
        after = subprocess.run(["git", "-C", self.bare, "rev-parse", "main"], capture_output=True, text=True).stdout
        self.assertEqual(before, after)

    def test_unmounted_storage_folder_publishes_nothing(self):
        self.enterContext(mock.patch.object(runtime, "ROOT", os.path.join(self.tmp.name, "unmounted")))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            pages_site.publish("kelsin")
        self.assertEqual(git_ls_tree(self.bare, "main"), [])

    def test_push_failure_exits_nonzero(self):
        pages_site.publish("kelsin")
        shutil.rmtree(self.bare)
        code, _, err = self.run_cmd("collections", "publish", "--user", "kelsin")
        self.assertNotEqual(code, 0)
        self.assertIn("git", err)

    def test_command_publishes_as_the_login_user(self):
        with mock.patch("getpass.getuser", return_value="kelsin"):
            code, out, _ = self.run_cmd("collections", "publish")
            self.assertEqual(code, 0)
            self.assertIn("Published https://sync-roms.games/collections/kelsin/", out)
            self.assertIn("collections/kelsin/index.html", git_ls_tree(self.bare, "main"))
            code, out, _ = self.run_cmd("collections", "publish")
        self.assertEqual(code, 0)
        self.assertIn("Already up to date: https://sync-roms.games/collections/kelsin/", out)

    def test_command_dry_run(self):
        code, out, _ = self.run_cmd("collections", "publish", "--user", "kelsin", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Would publish https://sync-roms.games/collections/kelsin/", out)
        self.assertIn("collections/kelsin/index.html", out)
        self.assertEqual(git_ls_tree(self.bare, "main"), [])
        self.run_cmd("collections", "publish", "--user", "kelsin")
        code, out, _ = self.run_cmd("collections", "publish", "--user", "kelsin", "--dry-run")
        self.assertIn("Nothing to publish", out)

    def test_default_repo(self):
        self.assertEqual(pages_site.DEFAULT_REPO, "git@github.com:kelsin/sync-roms.games.git")
        self.assertEqual(pages_site.CLONE_DIR(), os.path.join(self.tmp.name, "cache", "pages"))

    def test_command_waits_only_after_a_push(self):
        self.run_cmd("collections", "publish", "--user", "kelsin", "--dry-run")
        self.wait_live.assert_not_called()
        code, _, _ = self.run_cmd("collections", "publish", "--user", "kelsin", "--no-wait")
        self.assertEqual(code, 0)
        self.wait_live.assert_not_called()
        self.save_collection("Another")
        code, out, _ = self.run_cmd("collections", "publish", "--user", "kelsin")
        self.assertEqual(code, 0)
        self.wait_live.assert_called_once_with("kelsin")
        self.assertIn("Published", out)
        self.run_cmd("collections", "publish", "--user", "kelsin")
        self.wait_live.assert_called_once()  # nothing changed, nothing to wait for

    def test_github_repo(self):
        for repo in ("git@github.com:o/r.git", "git@github.com:o/r", "https://github.com/o/r.git",
                     "https://github.com/o/r", "ssh://git@github.com/o/r.git"):
            self.assertEqual(pages_site.github_repo(repo), "o/r", repo)
        for repo in ("git@gitlab.com:o/r.git", "/tmp/site.git", "https://github.com/o"):
            self.assertIsNone(pages_site.github_repo(repo), repo)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def completed(returncode=0, stdout=""):
    return subprocess.CompletedProcess([], returncode, stdout, "")


class WaitLive(SiteCase):
    def setUp(self):
        super().setUp()
        for name, value in (("RUN_POLL", 0), ("RUN_WAIT", 0), ("PAGE_POLL", 0), ("PAGE_WAIT", 60)):
            self.enterContext(mock.patch.object(pages_site, name, value))
        self.enterContext(mock.patch("time.sleep"))
        pages_site.publish("kelsin")
        with open(os.path.join(pages_site.CLONE_DIR(), "collections", "kelsin", "index.html"), "rb") as f:
            self.page = f.read()
        self.sha = subprocess.run(["git", "-C", self.bare, "rev-parse", "main"], capture_output=True, text=True).stdout.strip()
        self.fetched = []

    def serve(self, *bodies):
        """urlopen answering with bodies in turn (an exception is raised), the last one from then on."""
        def urlopen(link, timeout):
            self.fetched.append(link)
            body = bodies[min(len(self.fetched), len(bodies)) - 1]
            if isinstance(body, Exception):
                raise body
            return Response(body)
        return self.enterContext(mock.patch("urllib.request.urlopen", urlopen))

    def on_github(self, gh):
        usersettings.save_settings({"pages_repo": "git@github.com:o/r.git"})
        self.enterContext(mock.patch("shutil.which", return_value="/usr/bin/gh"))
        return self.enterContext(mock.patch.object(pages_site, "_gh", side_effect=gh))

    def wait(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            REAL_WAIT_LIVE("kelsin")
        return out.getvalue()

    def test_live_after_retries(self):
        import urllib.error
        self.serve(urllib.error.URLError("down"), b"old page", self.page)
        out = self.wait()
        self.assertIn("Waiting for GitHub Pages", out)
        self.assertIn("isn't on GitHub", out)
        self.assertEqual(len(self.fetched), 3)
        self.assertEqual(self.fetched[0], f"https://sync-roms.games/collections/kelsin/?v={self.sha}")

    def test_watches_the_deploy_run(self):
        self.serve(self.page)
        calls = []

        def gh(*args):
            calls.append(args)
            if args[:2] == ("run", "list"):
                return completed(stdout="[]" if len(calls) < 3 else '[{"databaseId": 7, "url": "https://x/7"}]')
            return completed()
        self.on_github(gh)
        self.enterContext(mock.patch.object(pages_site, "RUN_WAIT", 60))
        self.wait()
        self.assertEqual(calls[0], ("auth", "status"))
        self.assertIn(("--commit", self.sha), list(zip(calls[1], calls[1][1:])))
        self.assertIn("pages-build-deployment", calls[1])
        self.assertEqual(calls[-1], ("run", "watch", "7", "-R", "o/r", "--exit-status"))

    def test_failed_deploy_exits_1(self):
        self.serve(self.page)
        self.on_github(lambda *args: completed(1) if args[:2] == ("run", "watch")
                       else completed(stdout='[{"databaseId": 7, "url": "https://x/7"}]'))
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as e:
            self.wait()
        self.assertEqual(e.exception.code, 1)
        self.assertIn("The Pages deploy failed: https://x/7", err.getvalue())
        self.assertEqual(self.fetched, [])

    def test_no_gh_polls_the_page(self):
        self.serve(b"old", self.page)
        usersettings.save_settings({"pages_repo": "https://github.com/o/r"})
        self.enterContext(mock.patch("shutil.which", return_value=None))
        gh = self.enterContext(mock.patch.object(pages_site, "_gh"))
        out = self.wait()
        gh.assert_not_called()
        self.assertIn("gh isn't installed or logged in", out)
        self.assertEqual(len(self.fetched), 2)

    def test_gh_logged_out_or_no_run_polls_the_page(self):
        self.serve(self.page)
        gh = self.on_github(lambda *args: completed(1))
        self.assertIn("gh isn't installed or logged in", self.wait())
        gh.side_effect = lambda *args: completed(stdout="[]")
        self.assertIn("No Pages deploy run", self.wait())

    def test_timeout_exits_1(self):
        self.enterContext(mock.patch.object(pages_site, "PAGE_WAIT", 0))
        self.serve(b"old page")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as e:
            self.wait()
        self.assertEqual(e.exception.code, 1)
        self.assertIn("https://sync-roms.games/collections/kelsin/ isn't live", err.getvalue())
