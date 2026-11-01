import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sync_roms import chd, cli, commands, diff, edit, m3u, picker, runtime, s3, scrape_files, store, ui, upload, usersettings  # noqa: E402
from test_edit import EditFlow  # noqa: E402

ENV = ("ROMS_BUCKET", "ROMS_ENDPOINT", "ROMS_PROFILE", "ROMS_WRITE_PROFILE")


class Isolated(unittest.TestCase):
    """Runs cli.sync() with a given argv and settings.json, leaving the process-wide settings as they were."""
    def setUp(self):
        for name in ("BUCKET", "ENDPOINT", "PROFILE", "WRITE_PROFILE"):
            p = mock.patch.object(runtime, name, getattr(runtime, name))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ)
        p.start()
        self.addCleanup(p.stop)
        for name in ENV:
            os.environ.pop(name, None)
        runtime.OVERRIDES.clear()
        self.addCleanup(runtime.OVERRIDES.clear)

    def sync(self, argv, settings=None, **patches):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(sys, "argv", ["sync-roms"] + argv))
            st.enter_context(mock.patch.object(usersettings, "load_settings", lambda: dict(settings or {})))
            for target, name, value in patches.values():
                st.enter_context(mock.patch.object(target, name, value))
            st.enter_context(contextlib.redirect_stdout(out))
            st.enter_context(contextlib.redirect_stderr(err))
            try:
                code = cli.sync()
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()


if __name__ == "__main__":
    unittest.main()
