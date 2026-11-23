"""A card's picks as the card editor edits them: the card loaded once, each system's games listed from storage when
first shown, and every edit saved to cards.json together."""
from . import collections as colls, edit, listedit, m3u, names, store, vita


class SystemPicks:
    """One system's games on a card as edited so far: every file of its storage folder (in_storage) as rows, the
    card's direct picks (games) and exclusions, and the games its collections and surprises bring (locked_from, by
    label): the card's current surprises stay on (surprise), the other collection games are on unless excluded
    (collected)."""

    def __init__(self, system, in_storage, games, excluded, locked_from, surprise):
        self.system, self.bucket, self.in_storage = system, system["bucket"], in_storage
        self.games, self.excluded, self.locked_from = games, excluded, locked_from
        self.surprise = set(surprise)
        self.collected = set(locked_from) - self.surprise
        self.rows = edit.system_rows({**system, "games": games}, in_storage)
        self.titles = {k: title for _, k, title, _ in self.rows}
        self.groups = m3u.file_groups(in_storage)  # a multi-disc game's files are switched on and off together
        self.playlist_of = {k: g[0] for g in listedit.playlist_groups(in_storage).values() for k in g[1:]}
        self.bundled = vita.extras(in_storage, in_storage)  # a Vita game's DLC and update sync with it

    def states(self, notes):
        """{bucket key: synced} for every row, from the card as edited so far: a surprise, or picked directly, by a
        referenced set or by a collection, and not excluded (as sync does)."""
        direct = {g.get("bucket") for g in self.games}
        return {k: k in self.surprise or (k in notes or k in direct or k in self.collected) and k not in self.excluded
                for _, k, _, _ in self.rows}

    def changes(self, keys, base, state):
        """{bucket key: synced} for what one pass switched, each switched file's whole multi-disc game with it (the
        files the pass didn't show too)."""
        out = {}
        for key, want in zip(keys, state):
            if want != base[key]:
                for k in self.groups.get(key, [key]):
                    out.setdefault(k, want)
        return out

    def apply(self, keys, notes, base, state):
        """Fold one pass's on/off states into the card being edited. On: not excluded, and picked directly unless a
        referenced set or a collection covers it. Off: not picked directly, and excluded only while a referenced set or
        a collection covers it. Surprises stay as they are."""
        direct, off = {g.get("bucket") for g in self.games}, set()
        for key, want in self.changes(keys, base, state).items():
            if want == base[key] or key in self.surprise:
                continue
            if want:
                self.excluded.discard(key)
                if key not in notes and key not in direct and key not in self.collected:
                    self.games.append({"title": self.titles[key], "bucket": key})
                    direct.add(key)
            else:
                off.add(key)
                if key in notes or key in self.collected:
                    self.excluded.add(key)
                else:
                    self.excluded.discard(key)
        if off:
            self.games = [g for g in self.games if g.get("bucket") not in off]

    def keep(self, keys, notes):
        """Switch each of keys on; how many were off before and are on now."""
        base = self.states(notes)
        keys = [k for k in keys if k in base]  # a key with no row (a Vita DLC or update) can't be picked here
        before = sum(base[k] for k in keys)
        self.apply(keys, notes, base, [True] * len(keys))
        return sum(self.states(notes)[k] for k in keys) - before


class CardPicks:
    """A card's games as edited so far, over every system: the ones shown (system()) and working copies of the others
    a variant changed. setup: (device or None for Full, layout) being edited; cards: cards.json already loaded."""

    def __init__(self, name, setup, cards=None):
        self.name, self.setup = name, setup
        self.cards = store.load_cards() if cards is None else cards
        self.raw = store.card_games(name, self.cards)
        self.sets_on = list(store.list_sets(self.raw))
        self.before_excluded = store.card_excluded(name, self.cards)
        sets = store.load_sets()
        self.sets_by_id = {x["id"]: x for x in sets}
        self.variants, self.parents = store.variant_index(sets)
        self.system_names = {x["bucket"]: x["name"] for x in store.repo_json("systems")}
        locked = store.card_locked_games(self._entry(), {c["id"]: c for c in colls.load_collections()})
        self.locked_from = {b: {g["bucket"]: g["from"] for g in games} for b, games in locked.items()}
        # the current surprises' keys by system, whatever label locked_from gave them (a collection's comes first)
        self.surprises = {b: {g["bucket"] for g in games} for b, games in store.card_locked_games(self._entry(), {}).items()}
        self._systems = {}  # {system bucket: SystemPicks}
        self._picks = {}  # {system bucket: [games]}: direct picks on a system not shown, once a variant changes them
        self._excluded = {}  # {system bucket: {keys}}: exclusions on a system not shown, as edited

    def _entry(self):
        from . import cardedit  # cardedit imports cardpicks
        return cardedit.card_entry(self.name, self.setup, self.cards)

    def system(self, system):
        """The SystemPicks of a system, listed from storage on first use (names only: without a storage cache, a
        folder's sized listing stats every file). s3.ERRORS propagate."""
        bucket = system["bucket"]
        if bucket not in self._systems:
            in_storage = store.folder_keys(bucket)
            games = self.picks_of(bucket, writing=True)
            excluded = self.excluded_of(bucket)
            self._picks.pop(bucket)
            self._excluded.pop(bucket)
            self._systems[bucket] = SystemPicks(system, in_storage, games, excluded, self.locked_from.get(bucket, {}),
                                                self.surprises.get(bucket, ()))
        return self._systems[bucket]

    def cover(self):
        """{bucket key: note} of the games the card's set references sync."""
        return edit.cover_notes(self.sets_by_id, self.sets_on)

    def full(self, bucket):
        """Whether the card syncs that system whole."""
        entry = self.raw.get(bucket)
        return isinstance(entry, dict) and bool(entry.get("full_system"))

    def picks_of(self, bucket, writing=False):
        """The card's direct picks on a system as edited so far; writing makes a system not shown a working copy,
        saved with the rest."""
        if bucket in self._systems:
            return self._systems[bucket].games
        entry = self.raw.get(bucket)
        mine = [dict(g) for g in entry if isinstance(g, dict)] if isinstance(entry, list) else []
        return self._picks.setdefault(bucket, mine) if writing else self._picks.get(bucket, mine)

    def excluded_of(self, bucket):
        """The card's exclusions on a system as edited so far (a working copy for a system not shown)."""
        if bucket in self._systems:
            return self._systems[bucket].excluded
        return self._excluded.setdefault(bucket, set(self.before_excluded.get(bucket, ())))

    def on_card(self, key):
        """Whether a variant's bucket key is synced by the card as edited so far."""
        bucket = key.partition("/")[0]
        if bucket in self._systems:
            return self._systems[bucket].states(self.cover()).get(key, False)
        if key in self.surprises.get(bucket, ()):
            return True
        return self.full(bucket) or ((any(g.get("bucket") == key for g in self.picks_of(bucket)) or key in self.cover()
                                      or key in self.locked_from.get(bucket, {})) and key not in self.excluded_of(bucket))

    def toggle_variant(self, variant):
        """Add or remove a variant (and its files) as a direct pick; one the card syncs whole or through a set or
        collection stays as it is."""
        key = variant["bucket"]
        bucket = key.partition("/")[0]
        own = [key, *variant.get("files", ())]
        if self.on_card(key):
            if self.full(bucket) or all(g.get("bucket") != key for g in self.picks_of(bucket)):
                return
            picks = self.picks_of(bucket, writing=True)
            picks[:] = [g for g in picks if g.get("bucket") not in own]
        else:
            picks = self.picks_of(bucket, writing=True)
            picks.extend({"title": names.title(k), "bucket": k} for k in own
                         if all(g.get("bucket") != k for g in picks))
            self.excluded_of(bucket).difference_update(own)

    def _games(self):
        """The card's games list as edited so far, without the set references."""
        games = {k: v for k, v in self.raw.items() if k != store.SETS_KEY}
        for bucket, picks in [*self._picks.items(), *((b, sp.games) for b, sp in self._systems.items())]:
            if picks:
                games[bucket] = picks
            else:
                games.pop(bucket, None)
        return games

    def _excluded_now(self):
        """The card's exclusions as edited so far, {system bucket: [keys]} without empty ones. A system not shown keeps
        its saved order."""
        out = {b: list(k) for b, k in self.before_excluded.items()}
        for bucket, keys in self._excluded.items():
            saved = out.get(bucket, [])
            out[bucket] = [k for k in saved if k in keys] + sorted(keys - set(saved))
        for bucket, sp in self._systems.items():
            out[bucket] = sorted(sp.excluded)
        return {b: k for b, k in out.items() if k}

    def card(self):
        """card_entry with the edits so far: games, set references and exclusions."""
        entry = self._entry()
        games = {**self._games(), store.SETS_KEY: list(self.sets_on)}
        return {**entry, "games": {k: v for k, v in games.items() if v or k == store.SETS_KEY},
                "excluded": self._excluded_now()}

    def save(self):
        """Write every edit to cards.json; returns whether anything changed."""
        games = self._games()
        if self.sets_on:
            games[store.SETS_KEY] = self.sets_on
        excluded = self._excluded_now()
        changed = store.sorted_list(games) != store.sorted_list(self.raw) or excluded != self.before_excluded
        if changed:
            store.update_card(self.name, games=store.sorted_list(games),
                              **({"excluded": excluded} if excluded or self.before_excluded else {}))
        return changed
