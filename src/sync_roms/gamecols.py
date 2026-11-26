"""Name, System and Year columns for game lists: cells, sort values and the poll that fills in release years as each
system's scraped metadata arrives."""
import os

from . import gamemeta, picker, store

NO_YEAR = "  —"


class GameColumns:
    """rows: (system bucket, title, bucket key or None) per list row. A None key is a save's game: its year is that of
    the one metadata entry whose ROM file stem equals the title. extra_values(i, col_id): sort values of the caller's
    own columns (extra_columns, shown after Year)."""

    def __init__(self, rows, extra_columns=(), extra_values=None):
        names = {s["bucket"]: store.short_name(s) for s in store.repo_json("systems")}
        self.rows, self.extra_columns, self.extra_values = list(rows), list(extra_columns), extra_values
        self.systems = [names.get(bucket, bucket) for bucket, _, _ in self.rows]
        self.names = [store.sort_key(title) for _, title, _ in self.rows]
        self.casefolded = [s.casefold() for s in self.systems]
        self.years = [None] * len(self.rows)
        self.shown = None  # the extras lists handed to filter_list, which poll updates in place
        self.pending = {}  # system bucket -> its Metadata, until its answer has arrived
        for bucket, _, _ in self.rows:
            if bucket not in self.pending:
                self.pending[bucket] = gamemeta.Metadata(bucket)
        self.poll()

    def poll(self, then=None):
        """Take the metadata that has arrived since the last call; cheap once every system has answered."""
        if self.pending:
            for bucket, meta in list(self.pending.items()):
                index = meta.get()
                if index is gamemeta.LOADING:
                    continue
                del self.pending[bucket]
                if index:
                    self.fill(bucket, index)
        if then:
            then()

    def fill(self, bucket, index):
        stems = None  # ROM file stem -> [years of the paths with it]; only built when a save's game needs it
        for i, (system, title, key) in enumerate(self.rows):
            if system != bucket:
                continue
            if key is not None:
                year = next(iter(index.get(key, {}).get("year", ())), None)
            else:
                if stems is None:
                    stems = {}
                    for path, fields in index.items():
                        stems.setdefault(os.path.splitext(os.path.basename(path))[0], []).append(next(iter(fields.get("year", ())), None))
                found = stems.get(title, [])
                year = found[0] if len(found) == 1 else None
            if year:
                self.years[i] = year
                if self.shown is not None:
                    self.shown[i][1] = (f"  {year}", "dim")

    def cells(self, i):
        year = self.years[i]
        return [("  " + self.systems[i], "dim"), (f"  {year}" if year else NO_YEAR, "dim")]

    def sort_value(self, i, col_id):
        if col_id == "name":
            return self.names[i]
        if col_id == "system":
            return self.casefolded[i]
        if col_id == "year":
            return self.years[i]
        return self.extra_values(i, col_id) if self.extra_values else None

    def kwargs(self, extras=None, poll=None):
        """filter_list's columns, extras, sort, sort_value and poll arguments."""
        self.shown = [self.cells(i) + (list(extras[i]) if extras else []) for i in range(len(self.rows))]
        return {"columns": [picker.Column("name", "Name", True), picker.Column("system", "System", True),
                            picker.Column("year", "Year", True), *self.extra_columns],
                "extras": self.shown, "sort": picker.GAMES_SORT, "sort_value": self.sort_value,
                "poll": lambda: self.poll(poll)}
