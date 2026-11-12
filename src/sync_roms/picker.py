"""Interactive pickers: full-screen list screens (Textual)."""
import functools
import os
import unicodedata

from . import ui


def pick_device(devices, cursor=0):
    """Returns a device dict, "full", or None on Esc."""
    ui.require_terminal("pick a device and firmware", "--device ID --layout NAME")
    options = [(f"📟 {d['name']}", d) for d in devices] + [("🌍 Full (every system)", "full")]
    i = filter_list("🎯 Which device?", [label for label, _ in options], cursor=cursor,
                    hint="/ filter · j/k move · Enter continue · Esc quit")
    return None if i is None else options[i][1]


def pick_layout(layouts, default):
    """Returns a layout (firmware) name, or None on Esc. default: layout name the cursor starts on."""
    names = list(layouts)
    labels = [f"{l['label']}  ({l['roms_dir']}/ {l['bios_dir']}/)" for l in layouts.values()]
    i = filter_list("🗂️  Which firmware?", labels, cursor=names.index(default) if default in names else 0,
                    hint="/ filter · j/k move · Enter continue · Esc back")
    return None if i is None else names[i]


def device_layouts(device, layouts):
    """The layouts (firmwares) a device can run, in its own order: the first is its default."""
    return {name: layouts[name] for name in device["firmwares"]}


def saved_setup(saved, devices, layouts, card=None):
    """(device dict or None for Full, layout name) from a card's saved entry, or None if it no longer applies (with a warning saying why)."""
    if not isinstance(saved, dict):
        return None
    who = f"Saved setup for {card!r}" if card else "Saved setup"
    layout = saved.get("layout")
    if layout not in layouts:
        ui.warn(f"{who} ignored: its layout {layout!r} doesn't exist (known: {', '.join(layouts)})")
        return None
    if saved.get("device") == "full":
        return None, layout
    device = next((d for d in devices if d["id"] == saved.get("device")), None)
    if not device:
        ui.warn(f"{who} ignored: its device {saved.get('device')!r} doesn't exist")
        return None
    if layout not in device["firmwares"]:
        ui.warn(f"{who} ignored: {device['id']} doesn't run the {layout!r} firmware (has: {', '.join(device['firmwares'])})")
        return None
    return device, layout


def choose_setup(manifest, current=None):
    """Ask for the device, then its firmware (Esc steps back; a single firmware isn't asked).
    current: a (device dict or None for Full, layout name) the cursors start on.
    Returns (device dict or None for Full, layout name)."""
    devices, layouts = manifest["devices"], manifest["layouts"]
    while True:
        cursor = 0
        if current:
            cursor = next((i for i, d in enumerate(devices) if d is current[0]), len(devices))
        choice = pick_device(devices, cursor)
        if choice is None:
            print(ui.yellow("👋 Cancelled."))
            raise SystemExit(0)
        device = choice if isinstance(choice, dict) else None
        offered = device_layouts(device, layouts) if device else layouts
        if len(offered) == 1:
            return device, next(iter(offered))
        layout = pick_layout(offered, current[1] if current else next(iter(offered)))
        if layout is not None:
            return device, layout


SINGLE_HINT = "Enter select · Esc back · j/k ^N/^P move · / filter"
MULTI_HINT = "Space toggle · Enter done · Esc back · / filter · a all · o view · u revert"
TYPING_HINT = "Enter keep filter · Esc clear · ^N/^P move · ^A/^E ^B/^F ^K ^W ^U edit"


def help_lines(multi, hint, hidden_count=False, has_note=False):
    """Every key a filter_list accepts, then this screen's own hint entries."""
    lines = ["j/k ↑/↓ ^N/^P   move", "g/G             top / bottom", "^D/^U           half page",
             "^F/^B PgDn/PgUp page", "/               filter (Enter keeps it, Esc clears it)",
             "Enter           " + ("done" if multi else "pick"), "Esc/q/^G        clear the filter, then go back"]
    if multi:
        lines += ["Space/Tab       toggle the row", "a               toggle all shown", "o               view: all / on / changed",
                  "u               revert this list"]
        if has_note:
            lines.append("w               edit the row's note")
    if hidden_count:
        lines.append("z               show / hide hidden rows")
    lines.append("?               this help")
    extra = [e for e in hint.split(" · ") if e] if hint else []
    if extra:
        lines += ["", "This screen:"] + ["  " + e for e in extra]
    return lines


def cell_width(text):
    """Terminal cells text takes up (emoji and CJK are two wide)."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def line_key(text, pos, k):
    """Emacs-style single-line editing. Returns (text, cursor position), or None if k isn't an editing key.
    ^A/^E start/end · ^B/^F left/right · ^D delete char · ^K kill to end · ^U kill to start · ^W kill word."""
    if k in ("ctrl+a", "home"):
        return text, 0
    if k in ("ctrl+e", "end"):
        return text, len(text)
    if k in ("ctrl+b", "left"):
        return text, max(0, pos - 1)
    if k in ("ctrl+f", "right"):
        return text, min(len(text), pos + 1)
    if k in ("ctrl+d", "delete"):
        return text[:pos] + text[pos + 1:], pos
    if k in ("backspace", "ctrl+h"):  # ctrl+h: how Textual names ^H under the kitty keyboard protocol
        return (text[:pos - 1] + text[pos:], pos - 1) if pos else (text, pos)
    if k == "ctrl+k":
        return text[:pos], pos
    if k == "ctrl+u":
        return text[pos:], 0
    if k == "ctrl+w":
        start = text.rfind(" ", 0, len(text[:pos].rstrip())) + 1
        return text[:start] + text[pos:], start
    if k == "space":
        k = " "
    if len(k) == 1 and k.isprintable():
        return text[:pos] + k + text[pos:], pos + 1
    return None


def move_key(k, cur, last, view):
    """The new cursor row for a movement key (arrows, ^N/^P, PgUp/PgDn/^V, Home/End), or None if k isn't one."""
    if k in ("up", "ctrl+p"):
        return max(0, cur - 1)
    if k in ("down", "ctrl+n"):
        return min(last, cur + 1)
    if k == "pageup":
        return max(0, cur - view)
    if k in ("pagedown", "ctrl+v"):
        return min(last, cur + view)
    if k == "home":
        return 0
    if k == "end":
        return max(0, last)
    return None


POLL_MS = 200  # how often filter_list calls its poll while it waits for a key
NOTE_PROMPT = "Note (empty clears, Esc cancels): "
KEEP = object()  # _ListModel.key: the list stays open
HOTKEY_CHARS = {"space": " ", "tab": "\t"}  # keys callers name in hotkeys by their character


class _ListModel:
    """filter_list's state and what each key does to it, apart from drawing (the arguments are filter_list's)."""

    def __init__(self, title, labels, multi, initial, hint, cursor, extras, locked, locked_note, hotkeys, note_text,
                 on_note, esc_asks, hidden, status, diff_marks, session, poll, links, on_hotkey):
        self.title, self.labels, self.multi, self.hint, self.extras = title, labels, multi, hint, extras
        self.locked_note, self.hotkeys, self.note_text, self.on_note = locked_note, hotkeys, note_text, on_note
        self.esc_asks, self.status, self.diff_marks, self.poll = esc_asks, status, diff_marks, poll
        self.links, self.on_hotkey = links, on_hotkey
        self.lowered = [l.casefold() for l in labels]
        self.start = list(initial) if initial is not None else [False] * len(labels)
        self.locked = locked or [False] * len(labels)
        self.hidden = hidden or [False] * len(labels)
        self.hidden_count = sum(self.hidden)
        self.session = {} if session is None else session
        self.state = list(self.session["sel"]) if "sel" in self.session else list(self.start)
        self.view_mode = self.session.get("view_mode", 0)  # multi: 0 all rows, 1 only rows that are on, 2 only rows changed
        self.revealed = self.session.get("revealed", False)
        self.restore = self.session.get("row")
        self.query, self.qpos, self.typing = "", 0, False
        self.cur, self.top = cursor, 0
        self.notice = ""
        self.asking = False  # multi-mode Esc: waiting for keep or revert
        self.note = None  # (text, cursor position) while a note for row note_row is typed after w
        self.note_row = None
        self.help = None  # the help lines while they are shown
        self.height = 24  # screen rows; the app sets it
        self.update()

    def update(self):
        """Work out the shown rows (vis), keep the cursor on one and in view, save the session and work out the
        bottom row (line, see status_line)."""
        terms = self.query.casefold().split()
        vis = [i for i, l in enumerate(self.lowered) if (self.revealed or not self.hidden[i]) and all(t in l for t in terms)
               and (self.view_mode == 0 or (self.state[i] if self.view_mode == 1 else self.state[i] != self.start[i]))]
        vis.sort(key=lambda i: self.hidden[i])  # revealed rows go last; stable within each group
        try:
            self.cur = vis.index(self.restore)
        except ValueError:
            pass
        self.restore = None
        self.cur = max(0, min(self.cur, len(vis) - 1))
        self.vis = vis
        self.session.update(sel=self.state, view_mode=self.view_mode, revealed=self.revealed,
                            row=vis[self.cur] if vis else None)
        self.view = max(1, self.height - 4)
        if self.cur < self.top:
            self.top = self.cur
        elif self.cur >= self.top + self.view:
            self.top = self.cur - self.view + 1
        self.line = self.status_line()

    def linked(self, rows):
        """rows and the rows linked to them, without locked ones."""
        out = dict.fromkeys(rows)
        for i in rows:
            out.update(dict.fromkeys(self.links[i] if self.links else ()))
        return [i for i in out if not self.locked[i]]

    def pending(self):
        """(rows switched on, rows switched off) against initial."""
        return (sum(1 for a, b in zip(self.state, self.start) if a and not b),
                sum(1 for a, b in zip(self.state, self.start) if b and not a))

    def status_line(self):
        """The bottom row as (text, color or None, cursor index or None): the keep/revert question, the note being
        typed, or the status (a notice, the highlighted locked row's note, or the counts)."""
        added, removed = self.pending()
        if self.asking:
            return (f"Keep +{added} −{removed} pending change(s)?  y/Enter keep · u revert · any other key keeps editing",
                    "red", None)
        if self.note is not None:
            return NOTE_PROMPT + self.note[0], None, len(NOTE_PROMPT) + self.note[1]
        line, line_color = self.status(self.state) if self.status else f"{len(self.vis)}/{len(self.labels)} shown", None
        if isinstance(line, tuple):
            line, line_color = line
        if self.multi and self.diff_marks:
            line += f" · +{added} −{removed} pending"
        if self.multi and (self.diff_marks or self.view_mode):
            line += f" · view: {('all', 'on only', 'changed only')[self.view_mode]}"
        if not self.revealed and self.hidden_count:
            line += f" · {self.hidden_count} hidden (press z)"
        vis, cur = self.vis, self.cur
        if vis and self.locked[vis[cur]]:
            line = f"🔒 {self.locked_note[vis[cur]] if isinstance(self.locked_note, list) else self.locked_note}"
        if self.notice:
            line = self.notice
        return line, line_color, None

    def tick(self):
        """Call poll, unless help or a prompt is up (those wait for a key). Returns KEEP."""
        if self.poll and not self.help and not self.asking and self.note is None:
            self.poll()
            self.update()
        return KEEP

    def resize(self, height):
        """The screen is now height rows tall. Returns KEEP."""
        self.height = height
        self.update()
        return KEEP

    def key(self, k):
        """Act on one key: a Textual key name ("enter", "ctrl+a", ...) or a printable character.
        Returns the list's result once it is done, else KEEP."""
        self.notice = ""
        got = self.act(k)
        self.update()
        return got

    def act(self, k):
        if self.help:
            self.help = None
            return KEEP
        if self.asking:
            self.asking = False
            if k in ("y", "Y", "enter"):
                return self.state
            if k in ("u", "U"):
                return list(self.start)
            return KEEP
        if self.note is not None:
            if k == "enter":
                self.notice = self.on_note(self.note_row, self.note[0].strip())
                self.note = None
            elif k in ("escape", "ctrl+g"):
                self.note = None
            else:
                self.note = line_key(*self.note, k) or self.note
            return KEEP
        vis, cur = self.vis, self.cur
        if self.typing:
            edited = line_key(self.query, self.qpos, k)
            if k == "enter":
                self.typing = False
            elif k in ("escape", "ctrl+g"):
                self.query, self.qpos, self.typing = "", 0, False
                self.cur = self.top = 0
            elif edited:
                if edited[0] != self.query:
                    self.cur = self.top = 0
                self.query, self.qpos = edited
            else:
                moved = move_key(k, cur, len(vis) - 1, self.view)
                self.cur = cur if moved is None else moved
            return KEEP
        moved = move_key(k, cur, len(vis) - 1, self.view)
        hot = HOTKEY_CHARS.get(k, k)
        if hot in self.hotkeys and (vis or self.multi):
            if self.on_hotkey and self.on_hotkey(hot, vis[cur] if vis else None):
                return KEEP
            return hot, (vis[cur] if vis else None)
        if moved is not None:
            self.cur = moved
        elif k == "/":
            self.typing, self.qpos = True, len(self.query)
        elif k == "?":
            self.help = help_lines(self.multi, self.hint, self.hidden_count, bool(self.on_note))
        elif k == "j":
            self.cur = min(len(vis) - 1, cur + 1)
        elif k == "k":
            self.cur = max(0, cur - 1)
        elif k == "g":
            self.cur = 0
        elif k == "G":
            self.cur = len(vis) - 1
        elif k == "ctrl+d":
            self.cur = min(len(vis) - 1, cur + max(1, self.view // 2))
        elif k == "ctrl+u":
            self.cur = max(0, cur - max(1, self.view // 2))
        elif k == "ctrl+f":
            self.cur = min(len(vis) - 1, cur + self.view)
        elif k == "ctrl+b":
            self.cur = max(0, cur - self.view)
        elif k in ("escape", "q", "ctrl+g"):
            if self.query:
                self.query, self.qpos = "", 0
                self.cur = self.top = 0
                return KEEP
            if not self.multi or not self.esc_asks:
                return None
            if self.state == self.start:
                return self.state
            self.asking = True
        elif k == "enter":
            if self.multi:
                return self.state
            if vis:
                return vis[cur]
        elif k == "z" and self.hidden_count:
            self.revealed = not self.revealed
        elif not self.multi:
            pass
        elif k == "u":
            self.state = list(self.start)
            self.notice = "Reverted this list to how it was when opened"
        elif k in ("o", "ctrl+o"):
            self.view_mode = (self.view_mode + 1) % 3
            self.cur = self.top = 0
        elif k in ("tab", "space") and vis:
            if not self.locked[vis[cur]]:
                target = not self.state[vis[cur]]
                for i in self.linked([vis[cur]]):
                    self.state[i] = target
        elif k == "w" and vis and self.on_note and not self.locked[vis[cur]]:
            text = self.note_text(vis[cur]) if self.note_text else ""
            self.note, self.note_row = (text, len(text)), vis[cur]
        elif k in ("a", "ctrl+a") and vis:
            free = [i for i in vis if not self.locked[i]]
            target = not all(self.state[i] for i in free)
            for i in self.linked(free):
                self.state[i] = target
        return KEEP


def _key_name(event):
    """What _ListModel.key takes for a Textual key event: the character for printable keys (but "space"), else its name."""
    c = event.character
    return c if event.key != "space" and c and len(c) == 1 and c.isprintable() else event.key


def _with_cursor(text, at):
    """text with a reverse-video block at character at, where typing goes."""
    if at >= len(text):
        text.append(" ")
    text.stylize("reverse", at, at + 1)
    return text


@functools.cache
def _app_class():
    """The list's Textual app class, built on first use: importing Textual takes a while, and only a list needs it."""
    os.environ.setdefault("ESCDELAY", "25")  # read when Textual is imported: Esc acts at once
    from rich.text import Text
    from textual.app import App
    from textual.screen import Screen
    from textual.widget import Widget
    from textual.widgets import Static

    class _ListLines(Widget):
        """The list screen: title, filter, hint, the shown rows, and the status on the bottom row."""

        def on_resize(self, event):
            self.app.step(self.app.model.resize, event.size.height)

        def row(self, m, pos):
            i = m.vis[pos]
            style = ["reverse"] if pos == m.cur else []
            if m.locked[i]:
                line = f"🔒 {m.labels[i]}"
                style.append("dim")
            elif m.multi:
                if not m.diff_marks or m.state[i] == m.start[i]:
                    mark = "✅" if m.state[i] else "⬜"
                    style += ["green"] if m.state[i] and not m.diff_marks else []
                else:
                    mark = "➕" if m.state[i] else "➖"
                    style.append("green" if m.state[i] else "red")
                line = f"{mark} {m.labels[i]}"
            else:
                line = m.labels[i]
            if m.hidden[i]:
                style.append("dim")
            text = Text(line, " ".join(style))
            for part, color in (m.extras[i] if m.extras else []):
                text.append(part, " ".join(style + [color]))
            return text

        def render(self):
            m = self.app.model
            query = Text("🔎 " + m.query)
            lines = [Text(m.title, "bold cyan"), _with_cursor(query, 2 + m.qpos) if m.typing else query,
                     Text(TYPING_HINT if m.typing else m.hint or (MULTI_HINT if m.multi else SINGLE_HINT), "dim")]
            lines += [self.row(m, pos) for pos in range(m.top, min(len(m.vis), m.top + m.view))]
            text, color, at = m.line
            status = Text(text, f"bold {color}" if color else "bold")
            lines += [Text()] * max(0, self.size.height - len(lines) - 1) + [status if at is None else _with_cursor(status, at)]
            return Text("\n").join(lines)


    class _ListScreen(Screen):
        """The list; every key goes to the app's model."""

        def compose(self):
            yield _ListLines()

        def on_key(self, event):
            event.stop()
            self.app.feed(_key_name(event))

        def on_paste(self, event):
            event.stop()
            self.app.paste(event.text)


    class _HelpScreen(Screen):
        """The key list over the list; any key closes it."""

        def __init__(self, lines):
            super().__init__()
            self.lines = ["Keybindings", ""] + lines + ["", "Press any key to close"]

        def compose(self):
            yield Static(Text("\n").join([Text(self.lines[0], "bold")] + [Text(l) for l in self.lines[1:]]))

        def on_key(self, event):
            event.stop()
            self.app.feed(_key_name(event))


    class _ListApp(App, inherit_bindings=False):
        """filter_list full screen: draws a _ListModel, feeds it keys and polls it. No bindings of its own, so ^P, ^Q,
        Tab and the rest reach the list; Ctrl-C ends it (interrupted)."""
        ENABLE_COMMAND_PALETTE = False
        CSS = """
        _ListLines { height: 1fr; text-wrap: nowrap; text-overflow: clip; }
        _HelpScreen { align: center middle; }
        _HelpScreen Static { width: auto; }
        """

        def __init__(self, model):
            super().__init__(ansi_color=True)
            self.model = model
            self.done = False
            self.interrupted = False
            self.error = None  # what a step (a caller's callback, say) raised: filter_list raises it

        def get_default_screen(self):
            return _ListScreen()

        def on_mount(self):
            if self.model.poll:
                self.set_interval(POLL_MS / 1000, lambda: self.step(self.model.tick))

        def feed(self, k):
            if k == "ctrl+c":
                self.interrupted = True
                self.finish(None)
            else:
                self.step(self.model.key, k)

        def paste(self, text):
            """Pasted text goes into the filter or note being typed, a character at a time (newlines dropped)."""
            if self.model.typing or self.model.note is not None:
                for c in text.replace("\r", "").replace("\n", ""):
                    self.step(self.model.key, c)

        def step(self, act, *args):
            """Run one model step and redraw, or end the list with its result (or what it raised). The model is only
            called through here, so Textual never swallows a callback's error."""
            if self.done:
                return
            try:
                got = act(*args)
            except BaseException as error:
                self.error = error
                return self.finish(None)
            if got is not KEEP:
                return self.finish(got)
            if self.model.help and not isinstance(self.screen, _HelpScreen):
                self.push_screen(_HelpScreen(self.model.help))
            elif not self.model.help and isinstance(self.screen, _HelpScreen):
                self.pop_screen()
            self.screen_stack[0].query_one(_ListLines).refresh()

        def finish(self, result):
            self.done = True
            self.exit(result)

    return _ListApp


def _run(model):
    """Show the list full screen until it is done; returns its result. Ctrl-C raises KeyboardInterrupt."""
    app = _app_class()(model)
    result = app.run(mouse=False)
    if app.error:
        raise app.error
    if app.interrupted:
        raise KeyboardInterrupt
    return result


def filter_list(title, labels, multi=False, initial=None, hint="", cursor=0, extras=None, locked=None, locked_note="",
                hotkeys=(), note_text=None, on_note=None, esc_asks=True, hidden=None, status=None, diff_marks=True,
                session=None, poll=None, links=None, on_hotkey=None):
    """Modal list: vim keys for moving and acting, Emacs keys for editing the filter.

    Normal mode: j/k ↑/↓ ^N/^P move · g/G top/bottom · ^D/^U half page · ^F/^B/PgUp/PgDn/^V page · / filter ·
    Enter picks · Esc/q/^G clears the filter, then goes back. Multi mode adds Space/Tab toggle · a all/none shown ·
    o view (all / on / changed) · u revert · w note. After `/`, typed text filters (every
    space-separated term must appear in a label, case-insensitive); Enter keeps the filter, Esc clears it.

    Single mode returns the chosen index, or None on Esc. Multi mode returns the list of on/off states on Enter;
    Esc asks whether to keep or revert pending changes (esc_asks=False: it just returns None).
    cursor: index the highlight starts on.
    extras: per label, a list of (text, color) drawn after it (color: green, red, cyan or dim);
    they are not matched by the filter.
    locked: optional per-label flags; those rows are greyed out, can't be toggled, and show locked_note
    (one string, or one per label).
    on_note: optional callable(label index, text) -> message, called with a line typed after `w` on a row (multi mode);
    note_text(label index) gives the text to start from.
    hotkeys: normal-mode keys that return (key, label index) for the highlighted row instead of acting.
    hidden: optional per-label flags; those rows are left out (and drawn dim) until `z` reveals them.
    status(states) -> text, or (text, color): replaces the "N/M shown" status. diff_marks: show ➕/➖ against `initial`
    (else ✅/⬜ only).
    session: a dict the caller keeps so selection, view, revealed rows and cursor survive reopening the list.
    poll: optional callable, called on the list's thread every POLL_MS while it waits for a key; the list is then redrawn,
    so poll can update extras in place (and status can read what it changed).
    links: optional per-label lists of the label indexes switched together with it (multi mode): Space/Tab and `a`
    set them all to the toggled row's new state (locked ones excepted).
    on_hotkey: optional callable(key, label index) -> bool, tried first for a hotkey; True means it handled the key
    in place (the list stays open and is redrawn, so it can update extras), False returns (key, index) as usual.
    """
    return _run(_ListModel(title, labels, multi, initial, hint, cursor, extras, locked, locked_note, hotkeys, note_text,
                           on_note, esc_asks, hidden, status, diff_marks, session, poll, links, on_hotkey))
