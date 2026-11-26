import importlib.util
import os
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
spec = importlib.util.spec_from_file_location("run_tests", os.path.join(ROOT, "tools", "run_tests.py"))
run_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_tests)


class PlanTests(unittest.TestCase):
    def test_every_module_is_planned_exactly_once(self):
        names = sorted(f[:-3] for f in os.listdir(os.path.dirname(os.path.abspath(__file__))) if f.startswith("test_") and f.endswith(".py"))
        self.assertEqual(names, run_tests.modules())
        units = [u for proc in run_tests.plan(names) for u in proc]
        whole = [u for u in units if "@" not in u]
        self.assertEqual(len(whole), len(set(whole)))
        shards = {}
        for u in units:
            if "@" in u:
                name, part = u.split("@")
                shards.setdefault(name, []).append(part)
        self.assertEqual(set(shards), set(run_tests.SHARDS))
        for name, k in run_tests.SHARDS.items():
            self.assertEqual(sorted(shards[name]), sorted(f"{i}/{k}" for i in range(k)))
        self.assertEqual(sorted(whole + list(shards)), names)

    def test_shard_partition_drops_and_repeats_nothing(self):
        class Small(unittest.TestCase):
            def test_a(self): pass
            def test_b(self): pass
            def test_c(self): pass
            def test_d(self): pass
            def test_e(self): pass
        tests = list(run_tests.flatten(unittest.defaultTestLoader.loadTestsFromTestCase(Small)))
        self.assertEqual(len(tests), 5)
        picked = [t for i in range(3) for t in run_tests.shard(tests, i, 3)]
        self.assertEqual(sorted(t.id() for t in picked), sorted(t.id() for t in tests))


if __name__ == "__main__":
    unittest.main()
