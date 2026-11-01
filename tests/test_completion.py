import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sync_roms import commands  # noqa: E402

STUB = """#!/bin/sh
# stands in for sync-roms: `completion list WHAT`
case "$3" in
  cards) echo "SD One"; echo RGSP;;
  systems) echo gba; echo gbc; echo snes;;
  devices) echo full; echo rg35xx-sp;;
  layouts) echo knulli; echo muos;;
esac
"""


def script_for(shell):
    out = mock.MagicMock()
    with mock.patch("builtins.print", out):
        commands.completion_cmd(mock.Mock(shell=shell, what=None))
    return "".join(c.args[0] if c.args else "\n" for c in out.call_args_list)


@unittest.skipUnless(shutil.which("bash"), "bash not installed")
class BashCompletion(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        stub = os.path.join(self.dir, "sync-roms")
        with open(stub, "w") as f:
            f.write(STUB)
        os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)
        with open(os.path.join(self.dir, "comp.bash"), "w") as f:
            f.write(script_for("bash"))

    def complete(self, *words):
        """What bash would offer with the cursor on the last word."""
        quoted = " ".join("'%s'" % w for w in words)
        code = (f'source {self.dir}/comp.bash; COMP_WORDS=({quoted}); COMP_CWORD={len(words) - 1}; '
                'COMPREPLY=(); _sync_roms; printf "%s\\n" "${COMPREPLY[@]}"')
        env = dict(os.environ, PATH=self.dir + os.pathsep + os.environ["PATH"])
        out = subprocess.run([shutil.which("bash"), "-c", code], capture_output=True, text=True, env=env, cwd=self.dir)
        self.assertEqual(out.stderr, "")
        return out.stdout.splitlines()

    def test_syntax(self):
        self.assertEqual(subprocess.run([shutil.which("bash"), "-n", f"{self.dir}/comp.bash"]).returncode, 0)

    def test_values(self):
        self.assertEqual(self.complete("sync-roms", "--layout", "m"), ["muos"])
        self.assertEqual(self.complete("sync-roms", "--device", "f"), ["full"])
        self.assertIn("RGSP", self.complete("sync-roms", "--card", "R"))

    def test_systems_is_a_comma_list(self):
        self.assertEqual(self.complete("sync-roms", "--systems", "g"), ["gba", "gbc"])
        self.assertEqual(self.complete("sync-roms", "--systems", "gba,sn"), ["gba,snes"])
        self.assertEqual(self.complete("sync-roms", "--systems", "gba,gb"), ["gba,gba", "gba,gbc"])

    def test_commands_and_flags(self):
        self.assertIn("games", self.complete("sync-roms", ""))
        self.assertIn("--profile", self.complete("sync-roms", "--pro"))
        self.assertEqual(self.complete("sync-roms", "check", "--bucket-"), ["--bucket-keys"])

    def test_subcommands(self):
        self.assertIn("sets", self.complete("sync-roms", "games", ""))
        self.assertEqual(self.complete("sync-roms", "upload", "r"), ["roms"])
        self.assertEqual(self.complete("sync-roms", "games", "add", "gb"), ["gba", "gbc"])


class OtherShells(unittest.TestCase):
    def test_zsh_loads_bash_script(self):
        self.assertTrue(script_for("zsh").startswith("autoload -U +X bashcompinit && bashcompinit\n_sync_roms()"))

    def test_fish_completes_values_and_every_flag(self):
        text = script_for("fish")
        self.assertIn('-l card -x -a "(sync-roms completion list cards)"', text)
        self.assertIn('-l systems -x -a "all (sync-roms completion list systems)"', text)
        for flag in commands.all_flags():
            if flag.startswith("--"):
                self.assertIn(f"-l {flag[2:]}", text)


if __name__ == "__main__":
    unittest.main()
