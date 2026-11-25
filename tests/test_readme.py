import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate  # noqa: E402,F401

from sync_roms import commands  # noqa: E402

README = os.path.join(os.path.dirname(__file__), "..", "README.md")


def readme():
    with open(README, encoding="utf-8") as f:
        return f.read()


def readme_flags():
    """The flags in the first column of the Options table."""
    text = readme()
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


class ReadmeCommands(unittest.TestCase):
    def rows(self):
        table = readme().split("| Command | Does | Aliases |", 1)[1].split("\n\n", 1)[0]
        return [[c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))] for line in table.splitlines()[2:]]

    def test_commands_table_aliases_match(self):
        from sync_roms import cli
        found, names = {}, set()
        for cells in self.rows():
            word = re.findall(r"`([\w-]+)", cells[0])[0]
            names.add(word)
            for alias in re.findall(r"`([\w-]+)`", cells[-1]):
                found[alias] = word
        self.assertEqual(found, cli.ALIASES)
        self.assertEqual(sorted(set(cli.SUBCOMMANDS) - names), [], "commands missing from the README Commands table")


class ReadmeLayouts(unittest.TestCase):
    def test_layouts_table_and_saves_table_name_every_layout(self):
        with open(README, encoding="utf-8") as f:
            text = f.read()
        with open(os.path.join(os.path.dirname(__file__), "..", "src", "sync_roms", "data", "layouts.json")) as f:
            layouts = json.load(f)
        firmware = text.split("| Firmware | ROMs / BIOS folders", 1)[1].split("\n\n", 1)[0]
        saves = text.split("| Layout | RetroArch folder", 1)[1].split("\n\n", 1)[0]
        scrape = text.split("| Firmware | Media | Metadata", 1)[1].split("\n\n", 1)[0]
        for name in layouts:
            with self.subTest(name=name):
                self.assertIn(f"`{name}`", firmware)
                self.assertIn(f"`{name}`", saves)
                self.assertIn(f"`{name}`", scrape)


class ReadmeSettings(unittest.TestCase):
    def test_config_set_names_every_setting(self):
        from sync_roms import cli
        text = readme()
        section = text.split("### Settings (`config`)", 1)[1].split("\n## ", 1)[0]
        for name in commands.CONFIG_KINDS:
            with self.subTest(name=name):
                self.assertIn(f"`{name}`", section)
                self.assertIn(name, cli.TOPICS["config"])


if __name__ == "__main__":
    unittest.main()
