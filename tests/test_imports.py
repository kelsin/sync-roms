import glob
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


class StandaloneImportTest(unittest.TestCase):
    def test_every_module_imports_on_its_own(self):
        """Each module in a fresh interpreter: an import cycle that only works when another module happens to be
        imported first (as the CLI and test discovery do) fails here."""
        modules = sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(SRC, "sync_roms", "*.py")))
        modules = [m for m in modules if not m.startswith("__")]  # __main__ runs the CLI
        self.assertIn("cardedit", modules)
        env = {**os.environ, "PYTHONPATH": SRC}
        procs = [(m, subprocess.Popen([sys.executable, "-c", f"import sync_roms.{m}"], env=env, stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)) for m in modules]
        failed = []
        for m, proc in procs:
            err = proc.communicate()[1]
            if proc.returncode:
                failed.append(f"{m}: {err.strip().splitlines()[-1] if err.strip() else proc.returncode}")
        self.assertFalse(failed, "\n" + "\n".join(failed))


if __name__ == "__main__":
    unittest.main()
