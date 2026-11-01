import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sync_roms import commands  # noqa: E402

README = os.path.join(os.path.dirname(__file__), "..", "README.md")
def readme_flags():
    """The flags in the first column of the Options table."""
    text = open(README, encoding="utf-8").read()
    table = text.split("### Options", 1)[1].split("| Environment variable", 1)[0]
    found = set()
    for row in re.findall(r"^\| (.+?) \|", table, re.M):
        found.update(re.findall(r"`(-{1,2}[\w-]+)", row))
    return found


class ReadmeOptions(unittest.TestCase):
    def test_options_table_matches_parser(self):
        parser, readme = set(commands.all_flags()), readme_flags()
        self.assertEqual(sorted(parser - readme), [], "flags missing from the README Options table")
        self.assertEqual(sorted(readme - parser), [], "README Options flags the parser doesn't accept")


if __name__ == "__main__":
    unittest.main()
