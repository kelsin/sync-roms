"""Interactive pickers: full-screen list screens (Textual)."""
import collections
import functools
import os
import queue
import re
import signal
import sys
import threading
import time
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
MULTI_HINT = "Space toggle · Enter done · / filter · a all · o view · u revert"
HELP_HINT = "? help · "  # starts every hint line, so a narrow list cuts it last
TYPING_HINT = "Enter keep filter · Esc clear · ^N/^P move · ^A/^E ^B/^F ^K ^W ^U edit"
SINGLE_TYPING_HINT = "Enter pick · Tab keep filter · Esc clear · ^N/^P move · ^A/^E ^K ^W ^U edit"
HELP_FOOTER = "j/k ↑/↓ PgUp/PgDn scroll · Esc/q/? close"
# under "Working..." in an editor session, after a Ctrl-C the editor has not got yet; the second line once it is true
STOPPING = "🛑 Ctrl-C: stopping when this step ends."
QUIT_NOW = "   Press Ctrl-C again to quit now: unsaved changes in the open editor are lost."
QUIT_AFTER = 1  # seconds after that Ctrl-C from which another one quits; sooner, it is the same press (a double tap, a held key)


def help_lines(multi, hint, hidden_count=False, has_note=False, key_help=None):
    """Every key a filter_list accepts, then this screen's own keys: key_help's (keys, what they do) pairs, or else
    the hint's entries. A key key_help describes is listed only there."""
    lines = ["j/k ↑/↓ ^N/^P   move", "g/G             top / bottom", "^D/^U           half page",
             "^F/^B PgDn/PgUp page",
             "/               filter (" + ("Enter or Tab keeps it" if multi else "Enter picks, Tab keeps it")
             + ", Esc clears it)",
             "Enter           " + ("done" if multi else "pick"), "Esc/q/^G        clear the filter, then go back"]
    if multi:
        lines += ["Space/Tab       toggle the row", "a               toggle all shown", "o               view: all / on / changed",
                  "u               revert this list"]
        if has_note:
            lines.append("w               edit the row's note")
    if hidden_count:
        lines.append("z               show / hide hidden rows")
    lines.append("?               this help")
    if key_help:
        def keys(text):
            return set(re.split(r"[/ ]", text)) - {""}
        described = set().union(*(keys(k) for k, _ in key_help))
        lines = [line for line in lines if not (own := keys(line[:16])) or not own <= described]  # the "/" line's key splits to nothing
        return lines + ["", "This screen:"] + [f"{k:<15} {what}" for k, what in key_help]
    extra = [e for e in hint.split(" · ") if e] if hint else []
    if extra:
        lines += ["", "This screen:"] + ["  " + e for e in extra]
    return lines


def cell_width(text):
    """Terminal cells text takes up (emoji and CJK are two wide)."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


MIN_LABEL = 20  # cells a cut row keeps of its label; past that, the row's end (its extras) is cut instead


def _cut(text, width):
    """Cut a Rich Text to width cells, ending in "…" (a wide character is never split)."""
    if text.cell_len > width:
        text.truncate(width - 1)
        text.rstrip()
        text.append("…")


def fit_row(label, extras, width):
    """A row of width cells (Rich Texts, cells as Textual counts them): label, then extras right-aligned. The label is
    cut with "…" to the room the extras leave, but keeps MIN_LABEL cells (all of a shorter one); a row still too wide
    is cut at its end."""
    label.rstrip()
    _cut(label, max(width - extras.cell_len, min(label.cell_len, MIN_LABEL)))
    label.append(" " * max(0, width - label.cell_len - extras.cell_len))  # in the row's style: the highlight spans it
    label.append_text(extras)
    _cut(label, width)
    return label


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
                 on_note, esc_asks, hidden, status, diff_marks, session, poll, links, on_hotkey, preview=None, row_note=None,
                 key_help=None, filters=""):
        self.preview, self.row_note, self.key_help, self.filters = preview, row_note, key_help, filters
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
        self.query = self.session.get("query", "")
        self.qpos, self.typing = len(self.query), False
        self.cur, self.top = cursor, self.session.get("top", 0)
        self.notice = ""
        self.asking = False  # multi-mode Esc: waiting for keep or revert
        self.note = None  # (text, cursor position) while a note for row note_row is typed after w
        self.note_row = None
        self.help = None  # the help lines while they are shown
        self.height = 24  # screen rows; the app sets it
        self.update()

    def preview_path(self):
        """The image file for the highlighted row, or None (no preview, no row shown, the row has none, or its file
        won't load: missing or corrupt, which would otherwise crash the image pane)."""
        path = self.preview(self.vis[self.cur]) if self.preview and self.vis else None
        return path if path and _image_loads(path) else None

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
        self.view = max(1, self.height - 4)
        self.top = max(0, min(self.top, len(vis) - self.view))  # a restored scroll leaves no blank rows below the list
        if self.cur < self.top:
            self.top = self.cur
        elif self.cur >= self.top + self.view:
            self.top = self.cur - self.view + 1
        self.session.update(sel=self.state, view_mode=self.view_mode, revealed=self.revealed,
                            row=vis[self.cur] if vis else None, query=self.query, top=self.top)
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
        typed, or the status (a notice, the highlighted locked row's note, its row note, or the counts)."""
        added, removed = self.pending()
        if self.asking:
            return (f"Keep +{added} −{removed} pending change(s)?  y/Enter keep · u revert · any other key keeps editing",
                    "red", None)
        if self.note is not None:
            return NOTE_PROMPT + self.note[0], None, len(NOTE_PROMPT) + self.note[1]
        line, line_color = self.status(self.state) if self.status else "", None
        if isinstance(line, tuple):
            line, line_color = line
        parts = [f"+{added} −{removed}"] if self.multi and self.diff_marks else []
        parts += [line] if line else []
        if self.multi and (self.diff_marks or self.view_mode):
            parts.append(f"view: {('all', 'on only', 'changed only')[self.view_mode]}")
        if not self.revealed and self.hidden_count:
            parts.append(f"{self.hidden_count} hidden (press z)")
        line = " · ".join(parts)
        vis, cur = self.vis, self.cur
        if vis and self.row_note and (text := self.row_note(vis[cur])):
            line = text
        if vis and self.locked[vis[cur]]:
            line = f"🔒 {self.locked_note[vis[cur]] if isinstance(self.locked_note, list) else self.locked_note}"
        if self.notice:
            line = self.notice
        return line, line_color, None

    def position(self, compact=False):
        """Where the cursor is and how many rows the filter shows, for the right end of the status row when it fits ("" while
        a prompt has the row). compact: the same numbers without words, for when the full form doesn't fit."""
        if self.asking or self.note is not None:
            return ""
        shown = f"{len(self.vis)}/{len(self.labels)}" + ("" if compact else " shown")
        return (f"{self.cur + 1} · " if compact else f"row {self.cur + 1} · ") + shown if self.vis else shown

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
            if k in ("escape", "q", "?", "ctrl+g"):
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
            if k in ("enter", "tab"):
                self.typing = False
                if k == "enter" and not self.multi and vis:
                    return vis[cur]
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
            self.help = help_lines(self.multi, self.hint, self.hidden_count, bool(self.on_note), self.key_help)
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
    from textual import events
    from textual._time import get_time  # the clock Textual stamps events with (pinned by TextualPrintHook tests)
    from textual.app import App
    from textual.containers import VerticalScroll
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
            text, extras = Text(line, " ".join(style)), Text()
            for part, color in (m.extras[i] if m.extras else []):
                extras.append(part, " ".join(style + [color]))
            if self.size.width < 1:  # not laid out yet
                return text.append_text(extras)
            return fit_row(text, extras, self.size.width)

        def render(self):
            m = self.app.model
            query = Text("🔎 " + m.query)
            if m.typing:
                hint = TYPING_HINT if m.multi else SINGLE_TYPING_HINT
            else:
                hint = HELP_HINT + (m.hint or (MULTI_HINT if m.multi else SINGLE_HINT))
            if m.typing:
                _with_cursor(query, 2 + m.qpos)
            if m.filters:
                query.append("  " + m.filters, "cyan")
            lines = [Text(m.title, "bold cyan"), query, Text(hint, "dim")]
            lines += [self.row(m, pos) for pos in range(m.top, min(len(m.vis), m.top + m.view))]
            text, color, at = m.line
            status = Text(text, f"bold {color}" if color else "bold")
            for position in (m.position(), m.position(compact=True)):  # on the right, the first form the status leaves room for
                if position and status.cell_len + 2 + len(position) <= self.size.width:
                    status.append(" " * (self.size.width - status.cell_len - len(position)) + position, "bold")
                    break
            lines += [Text()] * max(0, self.size.height - len(lines) - 1) + [status if at is None else _with_cursor(status, at)]
            return Text("\n").join(lines)


    class _ListScreen(Screen):
        """The list; every key goes to the app's model."""

        def compose(self):
            yield _ListLines()
            if self.app.model.preview:
                from textual_image.widget import Image  # already imported (and the terminal probed) by filter_list
                yield Image(self.app.model.preview_path(), id="preview")

        def on_mount(self):
            if self.app.session and self is self.app.list_screen:
                self.app.list_ready()

        def on_key(self, event):
            event.stop()
            self.app.feed(_key_name(event))

        def on_paste(self, event):
            event.stop()
            self.app.paste(event.text)


    class _HelpScreen(Screen):
        """The key list over the list, scrolled by the movement keys; the model closes it on Esc, q or ?."""
        SCROLL = {"j": "scroll_down", "down": "scroll_down", "ctrl+n": "scroll_down", "k": "scroll_up", "up": "scroll_up",
                  "ctrl+p": "scroll_up", "pagedown": "scroll_page_down", "ctrl+f": "scroll_page_down",
                  "ctrl+v": "scroll_page_down", "pageup": "scroll_page_up", "ctrl+b": "scroll_page_up",
                  "g": "scroll_home", "home": "scroll_home", "G": "scroll_end", "end": "scroll_end"}

        def __init__(self, lines):
            super().__init__()
            self.lines = lines

        def compose(self):
            with VerticalScroll():
                yield Static(Text("\n").join([Text("Keybindings", "bold"), Text()] + [Text(l) for l in self.lines]),
                             id="help-text")
            yield Static(Text(HELP_FOOTER, "dim"), id="help-footer")

        def on_key(self, event):
            event.stop()
            k = _key_name(event)
            if k in self.SCROLL:
                getattr(self.query_one(VerticalScroll), self.SCROLL[k])(animate=False)
            else:
                self.app.feed(k)


    class _WorkingScreen(Screen):
        """An editor session's screen between its lists, with the last line the editor printed and, after a Ctrl-C,
        what that does (its keys: _ListApp.session_input)."""

        def compose(self):
            yield Static(Text("Working...", "dim"))
            yield Static(id="last")
            yield Static(id="stopping")


    class _ListApp(App, inherit_bindings=False):
        """filter_list full screen: draws a _ListModel, feeds it keys and polls it. No bindings of its own, so ^P, ^Q,
        Tab and the rest reach the list; Ctrl-C ends it (interrupted). In an editor session (session: a _Session) it
        shows one list after another, and "Working..." between them, until the session ends it."""
        ENABLE_COMMAND_PALETTE = False
        CSS = """
        _ListLines { width: 1fr; height: 1fr; text-wrap: nowrap; text-overflow: clip; }
        _ListScreen { layout: horizontal; }
        _ListScreen #preview { width: auto; max-width: 34%; height: 100%; }
        _HelpScreen { align: center middle; }
        _HelpScreen VerticalScroll { width: auto; height: auto; max-height: 100%; }
        _HelpScreen #help-footer { dock: bottom; width: 100%; text-align: center; }
        _HelpScreen Static { width: auto; }
        """

        def __init__(self, model, session=None, reply=None):
            super().__init__(ansi_color=True)
            self.model = model
            self.session, self.reply = session, reply  # in a session: the queue that gets the list's (result, error)
            self.done = session is not None  # in a session no list is up until show
            self.interrupted = False
            self.error = None  # what a step (a caller's callback, say) raised: filter_list raises it
            self.timer = None
            self.keys_from = 0  # in a session: keys stamped earlier were read as the app suspended for a prompt
            self.ended_at = 0  # in a session: when the last list ended (keys stamped earlier were typed for it)
            self.ready = False  # in a session: the list screen is up and composed
            self.typeahead = []  # in a session: keys typed while no list was up yet, for the next one
            self.quit_timer = None  # in a session: shows the "quit now" line once another Ctrl-C would quit

        def get_default_screen(self):
            if self.session:
                return _WorkingScreen()
            self.list_screen = _ListScreen()
            return self.list_screen

        def on_mount(self):
            if self.session:
                self.request("list", self.model, self.reply)
            elif self.model.poll:
                self.set_interval(POLL_MS / 1000, lambda: self.step(self.model.tick))

        def show(self, model, reply):
            """Show the next list of the session; its (result, error) goes to reply when it is done."""
            if self.deliver(reply):  # a Ctrl-C since the worker asked (just after a prompt's answer, say)
                return
            if model.preview and self.session.draws is None:  # the terminal is asked once, on the normal screen
                with self.suspend():
                    self.suspending()
                    _, error = _outcome(lambda: self.session.at_terminal(self.session.probe, model))
                if error is not None:  # Ctrl-C while it asked: as in the list
                    return self.answer(reply, (None, error))
                if self.deliver(reply):  # a Ctrl-C as the app came back
                    return
            if not self.session.draws:
                model.preview = None
            self.model, self.reply = model, reply
            self.done, self.interrupted, self.error = False, False, None
            self.last_line("")
            self.timer = self.set_interval(POLL_MS / 1000, lambda: self.step(self.model.tick)) if model.poll else None
            self.ready = False
            self.list_screen = _ListScreen()
            self.push_screen(self.list_screen)

        def list_ready(self):
            """The list screen is composed: it takes keys now, the ones typed ahead first."""
            self.ready = True
            typed, self.typeahead = self.typeahead, []
            for event in typed:
                self.session_input(event)
                if not self.done and self.screen is not self.list_screen:  # it opened help: the rest is dropped
                    break

        def suspending(self):
            """The app has just suspended: what its input read as it stopped, and keys typed ahead, were typed before
            what the terminal now shows (a prompt, a command), so none of it reaches a list."""
            self.keys_from = get_time()
            self.typeahead = []

        async def on_event(self, event):
            """In a session every key and paste goes to session_input, in the order they came; outside one, as usual."""
            if self.session and isinstance(event, (events.Key, events.Paste)) and not event.is_forwarded:
                return self.session_input(event)
            await super().on_event(event)

        def post_message(self, message):
            """As Textual's. In a session, a Ctrl-C the app no longer takes (read as it closes: typed during the
            editor's last step) still counts for the session."""
            posted = super().post_message(message)
            if not posted and self.session and isinstance(message, events.Key) and _key_name(message) == "ctrl+c":
                self.session.interrupt()
            return posted

        def session_input(self, event):
            """A key or paste in a session (in arrival order, so a Ctrl-C right behind the key that ended a list is
            seen before that list's result is sent): dropped if typed before a prompt; for a list that has just
            ended, only a Ctrl-C counts (it makes that list's result an interrupt, as without a session); while no
            list is up, Ctrl-C is for the editor's next request (or, the second time, ends the session) and other
            keys wait for the next list."""
            if event.time < self.keys_from:
                return
            k = _key_name(event) if isinstance(event, events.Key) else None
            if event.time < self.ended_at:
                if k == "ctrl+c":
                    self.late_ctrl_c()
                return
            if self.done:
                if k == "ctrl+c":  # like a terminal's Ctrl-C, it also discards what was typed ahead
                    self.typeahead = []
                    self.session.interrupt()
                    self.stopping()
                elif k == "ctrl+z":
                    self.action_suspend_process()
                else:
                    self.typeahead.append(event)
            elif not self.ready:
                self.typeahead.append(event)
            elif k is None:
                self.paste(event.text)
            elif isinstance(self.screen, _HelpScreen) and k in _HelpScreen.SCROLL:
                getattr(self.screen.query_one(VerticalScroll), _HelpScreen.SCROLL[k])(animate=False)
            else:
                self.feed(k)

        def late_ctrl_c(self):
            """A Ctrl-C typed for the list that just ended."""
            if self.done and self.reply is not None:  # its result is not sent yet: it becomes the interrupt
                self.interrupted = True
            elif not self.done:  # the next list is already up: it ends with the interrupt
                self.interrupted = True
                self.finish(None)
            else:
                self.session.interrupt()
                self.stopping()

        def stopping(self, due=False):
            """Show where the session's Ctrl-C stands (_Session.interrupt): its line under "Working..." while the
            editor has not got it, and a second line from when another Ctrl-C would quit (due: that time has come);
            the end of the app once one abandoned the editor."""
            if self.session.abandoned:
                return self.exit()
            wait = self.session.quit_wait()
            text = "" if wait is None else STOPPING if wait and not due else STOPPING + "\n" + QUIT_NOW
            for line in self.screen_stack[0].query("#stopping"):  # none before the working screen is composed
                line.update(Text(text, "yellow"))
            if self.quit_timer:
                self.quit_timer.stop()
            self.quit_timer = self.set_timer(wait, lambda: self.stopping(True)) if wait and not due else None

        def deliver(self, reply):
            """Answer reply with the Ctrl-C that waits for the editor's next request, if one does."""
            delivered = self.session.deliver(reply)
            if delivered:
                self.stopping()
            return delivered

        def answer(self, reply, outcome, pressed=None):
            """Give the editor a list's outcome (_Session.answer); a Ctrl-C that still waits for its next request
            shows as its step starts."""
            self.session.answer(reply, outcome, pressed)
            if self.session.interrupted:
                self.stopping()

        def request(self, kind, payload, reply):
            """A request from the session's worker (_Session.ask): show a list, or suspend the app and answer prompts on
            the normal screen (after what the worker printed meanwhile) until the next list, or the end."""
            if kind == "list":
                return self.show(payload, reply)
            if self.deliver(reply):
                return
            session = self.session
            with self.suspend():
                self.suspending()
                sys.stdout, sys.stderr = session.streams  # suspend() restores Textual's on the way out
                session.flush()
                with session.lock:
                    session.suspended = True
                request = session.prompts((kind, payload, reply))
                with session.lock:
                    session.suspended = False
            if request is None:  # the editor is done, or abandoned
                session.requests.put(None)  # for _Session.run, once the app has closed
                self.exit()
            else:
                self.show(*request[1:])

        def last_line(self, line):
            for last in self.screen_stack[0].query("#last"):  # none before the working screen is composed
                last.update(Text(line, "dim"))

        def _print(self, text, stderr=False):
            """What the worker prints while the app runs is kept for the normal screen, and its last line shown under
            "Working..."; other threads' goes to Textual. Overrides Textual's private App._print, which its print
            capture calls with every write while the app runs (TextualPrintHook tests pin that)."""
            if self.session and threading.get_ident() == self.session.worker:
                if self.session.abandoned:
                    return
                self.session.printed.append((stderr, text))
                line = self.session.last_line(text)
                if line is not None:
                    self.call_later(self.last_line, line)
            else:
                super()._print(text, stderr)

        def feed(self, k):
            if k == "ctrl+c":
                self.interrupted = True
                self.finish(None)
            elif k == "ctrl+z":  # raw mode clears ISIG, so the terminal no longer suspends on its own
                self.action_suspend_process()
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
            self.list_screen.query_one(_ListLines).refresh()
            if self.model.preview:
                pane = self.list_screen.query_one("#preview")
                path = self.model.preview_path()
                if path != pane.image:  # the setter re-transmits the image, so only touch it when it changed
                    pane.image = path

        def finish(self, result):
            self.done = True
            if not self.session:
                return self.exit(result)
            if self.timer:
                self.timer.stop()
            self.ended_at = get_time()
            while len(self.screen_stack) > 1:
                self.pop_screen()
            self.call_later(self.send, result)  # after the keys already queued (session_input)

        def send(self, result):
            """Hand the ended list's result to the worker."""
            reply, self.reply = self.reply, None
            self.answer(reply, (result, self.error or (KeyboardInterrupt() if self.interrupted else None)),
                        _now() if self.interrupted else None)

    return _ListApp


def _outcome(call):
    """(what call() returns, None), or (None, what it raised)."""
    try:
        return call(), None
    except BaseException as error:  # noqa: BLE001 -- handed to the thread waiting for it, which raises it
        return None, error


_session = None  # the editor session (one_app) running now, if any
_ESCAPES = re.compile(r"\x1b(\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(\x07|\x1b\\)|[0-~])")  # CSI, OSC, other ESC sequences


def _now():
    """The clock an editor session times Ctrl-C with, in seconds (one function, so tests can set it)."""
    return time.monotonic()


def _in_session():
    """Whether this thread is an editor session's worker."""
    return _session is not None and _session.worker == threading.get_ident()


class _Output:
    """sys.stdout or sys.stderr (stream) during an editor session: all of it, except what the session's worker writes
    once the session is abandoned, which goes nowhere."""

    def __init__(self, session, stream):
        self.session, self.stream = session, stream

    def write(self, text):
        if self.session.abandoned and threading.get_ident() == self.session.worker:
            return len(text)
        return self.stream.write(text)

    def __getattr__(self, name):
        return getattr(self.stream, name)


class _Session:
    """One list app for a whole editor run (one_app). The editor runs on a worker thread. The main thread starts the
    app at the first list and keeps it until the editor is done, with "Working..." between lists. Each list and each
    prompt is a request the worker hands to the main thread (to the app while it runs) and waits for: prompts run on
    the main thread with the app suspended until the next list, so input, Ctrl-C and output between prompts work as
    without a session, and so do commands that may ask (ui.uses_terminal). What the worker prints while the app shows
    comes out, in order, when the normal screen is back; its last line shows under "Working...". Ctrl-C while the
    editor works reaches it as KeyboardInterrupt from its next request; another one a second or more later, before
    that request, abandons it: the session ends at once, and the worker, left to itself, gets KeyboardInterrupt from
    every request and prints nothing (interrupt). Nothing is ever raised in the worker but by its own requests."""

    def __init__(self):
        self.requests = queue.SimpleQueue()  # the worker's (kind, payload, reply) while no app takes them; None: no more
        self.lock = threading.RLock()  # app, suspended, waiting, working, abandoned: for both threads (re-entrant: on_sigint)
        self.app = None  # the running app
        self.suspended = False  # the app is suspended for prompts: the main thread takes requests from the queue
        self.waiting = None  # the reply the worker waits for from the app
        self.worker = None  # the worker's thread id, while it runs
        self.result = None  # the editor's _outcome
        self.prompting = False  # the main thread runs a prompt (at_terminal): Ctrl-C raises KeyboardInterrupt there
        self.working = True  # the worker runs editor code: it is not waiting for a request's answer, and has not ended
        self.interrupted = False  # a Ctrl-C the worker gets from its next request (or once the editor is done)
        self.interrupted_at = 0  # when it came (_now), or when the worker went back to work with it still waiting
        self.pressed = None  # when the Ctrl-C came that the worker has just got, until its next request
        self.abandoned = False  # a later Ctrl-C ended the session without waiting for the worker
        self.tail = ""  # the worker's printed text after its last newline
        self.draws = None  # _draws_images(), asked when the first list with a preview comes, on the normal screen
        self.streams = None  # sys.stdout and sys.stderr from before the app started
        self.printed = collections.deque()  # (to stderr, text) the worker printed while the app ran

    def run(self, fn, args, kwargs):
        """Run fn(*args, **kwargs) on the worker and serve its requests until it is done; returns or raises what it
        did, once the app is closed. Raises KeyboardInterrupt without waiting for it once it is abandoned."""
        global _session
        _session, ui.terminal_runner = self, self.outside
        handler = signal.signal(signal.SIGINT, self.on_sigint)  # also keeps asyncio.run's own (it would cancel the app)
        outputs = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = _Output(self, sys.stdout), _Output(self, sys.stderr)
        try:
            threading.Thread(target=self.work, args=(fn, args, kwargs), name="editor", daemon=True).start()
            while (request := self.prompts(self.requests.get())) is not None:
                self.serve(*request[1:])
        finally:
            signal.signal(signal.SIGINT, handler)
            if not self.abandoned:  # else it all stays, for the worker that lives on: its requests raise, its output is dropped
                sys.stdout, sys.stderr = outputs
                _session = ui.terminal_runner = None
        if self.abandoned:
            raise KeyboardInterrupt
        value, error = self.result
        if error is None and self.interrupted:  # Ctrl-C after the last list
            error = KeyboardInterrupt()
        if error is not None:
            raise error
        return value

    def prompts(self, request):
        """On the main thread: answer requests while they are prompts. Returns the first list request (the terminal
        probed for it if it needs that), or None once the editor is done or abandoned."""
        while request is not None:
            kind, payload, reply = request
            if self.deliver(reply):
                pass
            elif kind == "list":
                _, error = _outcome(lambda: self.at_terminal(self.probe, payload))  # the terminal is still ours here
                if error is None:
                    return request
                self.answer(reply, (None, error))  # Ctrl-C while it asked: as in the list
            else:
                self.answer(reply, _outcome(lambda: self.at_terminal(payload)))
            request = self.requests.get()
        return None

    def deliver(self, reply):
        """On the main thread: answer reply with the Ctrl-C that waits for the worker's next request, if one does."""
        if not self.interrupted:
            return False
        self.interrupted = False
        self.answer(reply, (None, KeyboardInterrupt()), self.interrupted_at)
        return True

    def answer(self, reply, outcome, pressed=None):
        """On the main thread: give the worker the outcome of its request, and so send it back to work. pressed: when
        the Ctrl-C came that the outcome carries (it ended the list, or it waited for this request); until the
        worker's next request another one less than QUIT_AFTER after it is the same press. A Ctrl-C that still waits
        (it came while the list or the prompt was up) counts from now, when the step it waits for starts."""
        with self.lock:
            self.pressed = pressed
            if self.interrupted:
                self.interrupted_at = _now()
        reply.put(outcome)

    def at_terminal(self, fn, *args):
        """Run a prompt (or the image probe) on the main thread, where Ctrl-C raises KeyboardInterrupt in it."""
        try:
            self.prompting = True
            return fn(*args)
        finally:
            self.prompting = False

    def on_sigint(self, signum, frame):
        """The session's SIGINT handler (main thread): KeyboardInterrupt in a prompt, else interrupt; never an
        exception in the session's own code."""
        if self.prompting:
            raise KeyboardInterrupt
        self.interrupt()
        app = self.app
        if app:  # the app shows it (stopping) from its loop: a signal handler runs inside that loop and must not post to it
            import asyncio
            try:
                asyncio.get_running_loop().call_soon_threadsafe(app.call_later, app.stopping)
            except RuntimeError:  # the loop is not running: the app is starting, or has closed
                pass

    def interrupt(self):
        """Ctrl-C while neither a list nor a prompt is up (main thread): the worker gets KeyboardInterrupt from its
        next request. Another one QUIT_AFTER seconds or more later, while the worker is still at work on the same
        step, abandons it: the session ends now. One that comes sooner counts as the same press, and so does one
        that comes that soon after the Ctrl-C the worker has just got (pressed)."""
        with self.lock:
            if self.pressed is not None and _now() - self.pressed < QUIT_AFTER:
                return
            if not self.interrupted:
                self.interrupted, self.interrupted_at = True, _now()
            elif self.working and not self.quit_wait():
                self.abandoned = True
                self.requests.put(None)  # for the main thread, if it waits for the worker (safe from a signal handler)

    def quit_wait(self):
        """On the main thread: the seconds until another Ctrl-C quits (0: it does now), or None when no Ctrl-C waits
        for the worker."""
        return max(0, self.interrupted_at + QUIT_AFTER - _now()) if self.interrupted else None

    def work(self, fn, args, kwargs):
        """The worker: run the editor, then end the app and the main thread's loop."""
        self.worker = threading.get_ident()
        self.result = _outcome(lambda: fn(*args, **kwargs))
        with self.lock:
            self.working = False
            if self.app and not self.suspended:  # a suspended app ends when its prompts get the None below
                self.app.call_later(self.app.exit)
        self.requests.put(None)
        self.worker = None  # another thread may get its id (an abandoned session stays in place)

    def serve(self, model, reply):
        """Run the app, showing model first, until the editor is done. If the app fails instead, the worker's pending
        request fails the way _run does without a session."""
        cls = _app_class()
        app = cls(model, self, reply)
        self.streams = sys.stdout, sys.stderr
        with self.lock:
            self.app = app
        try:
            app.run(mouse=False)
        finally:
            with self.lock:
                self.app = None
                pending = [r for r in (app.reply, self.waiting) if r is not None]
            self.flush()
        for r in pending:
            r.put((None, SystemExit(app.return_code or 1)))

    def flush(self):
        """Write out what the worker printed while the app showed (main thread)."""
        out, err = self.streams
        while self.printed:
            to_err, text = self.printed.popleft()
            (err if to_err else out).write(text)
        out.flush()
        err.flush()

    def ask(self, kind, payload):
        """On the worker: have the main thread show a list (kind "list", payload its model) or run a prompt ("call",
        payload a callable), and wait. Returns (result, error): at once, with KeyboardInterrupt, once abandoned."""
        reply = queue.Queue()
        with self.lock:
            if self.abandoned:
                return None, KeyboardInterrupt()
            self.working, self.pressed = False, None
            if self.app and not self.suspended and self.app.call_later(self.app.request, kind, payload, reply):
                self.waiting = reply
            else:
                self.requests.put((kind, payload, reply))
        got = reply.get()
        with self.lock:
            self.waiting = None
            self.working = True
        return got

    def probe(self, model):
        """Ask the terminal whether it draws images, once, when the first list with a preview comes (main thread, with
        the terminal not taken by the app)."""
        if model.preview and self.draws is None:
            _app_class()
            self.draws = _draws_images()

    def last_line(self, text):
        """On the worker: the last complete line once text is printed, as plain text (escape sequences and control
        characters dropped), or None when text completes no line with something in it."""
        lines = (self.tail + text).split("\n")
        self.tail = lines.pop()[-1000:]  # a line that never ends (a progress bar's redraws) is never shown
        for line in reversed(lines):
            for part in reversed(line.split("\r")):  # a progress line redraws itself after \r
                plain = "".join(c for c in _ESCAPES.sub("", part) if c.isprintable()).rstrip()
                if plain.strip():
                    return plain
        return None

    def outside(self, fn, *args, **kwargs):
        """ui.terminal_runner: fn called on the worker runs on the main thread, on the normal screen."""
        if threading.get_ident() != self.worker:
            return fn(*args, **kwargs)
        value, error = self.ask("call", functools.partial(fn, *args, **kwargs))
        if error is not None:
            raise error
        return value


def one_app(fn):
    """An editor (fn) whose lists all show in one app (_Session) instead of one app each. Only with a terminal; inside
    another editor's session it just runs."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        if _session or not ui.has_terminal() or threading.current_thread() is not threading.main_thread():
            return fn(*args, **kwargs)
        return _Session().run(fn, args, kwargs)
    return run


def _run(model):
    """Show the list full screen until it is done; returns its result. Ctrl-C raises KeyboardInterrupt."""
    if _in_session():
        result, error = _session.ask("list", model)
        if error is not None:
            raise error
        return result
    app = _app_class()(model)
    result = app.run(mouse=False)
    if app.error:
        raise app.error
    if app.interrupted:
        raise KeyboardInterrupt
    if app.return_code:  # Textual itself failed (it already printed the traceback): not an Esc
        raise SystemExit(app.return_code)
    return result


def _probe_through_tmux():
    """Inside tmux, ask the outer terminal instead of tmux, and leave the answer where textual-image keeps its own
    probe's. tmux answers textual-image's device-attributes query itself (claiming Sixel, which it may not be able to
    pass on), before the outer terminal's Kitty graphics reply, which then arrives late, as keys. Passed through,
    every reply comes from the outer terminal, in order. Needs tmux's allow-passthrough; False when it gets no answer.
    Uses textual-image internals (0.14), so anything unexpected also means False."""
    import sys
    try:
        from textual_image import _terminal as term
        from textual_image._tmux import tmux_escape
        if not (sys.__stdout__ and sys.__stdout__.isatty()):
            return False
        with term.capture_until_primary_da(term._PROBE_TIMEOUT) as response:
            sys.__stdout__.write(term._tgp_support_query() + tmux_escape("\x1b[16t") + tmux_escape("\x1b[c"))
            sys.__stdout__.flush()
        sixel, tgp, width, height = term._parse_probe_response(response.sequence)
        if not (width and height):
            rows, columns, x_pixels, y_pixels = term.get_tiocgwinsz()
            width, height = x_pixels // columns, y_pixels // rows
        if not (width and height):
            return False
        term.probe_terminal._result = term.TerminalCapabilities(term.CellSize(width, height), sixel=sixel, tgp=tgp)
    except Exception:  # noqa: BLE001 -- a missing internal, a closed stdin or no answer: no images
        return False
    return sixel or tgp


def _image_loads(path):
    """Whether path is an image Pillow can read (textual-image's own error handling differs between versions)."""
    from PIL import Image  # textual-image depends on Pillow
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (OSError, ValueError, EOFError, SyntaxError):
        return False


def _draws_images():
    """True when the terminal speaks Kitty graphics or Sixel. textual-image probes the terminal on import, which must
    happen before the app starts; its block fallbacks are too coarse for the art, so they don't count."""
    import logging
    logging.getLogger("textual_image").setLevel(logging.ERROR)  # a terminal that doesn't answer isn't worth a traceback
    if os.environ.get("TMUX") and not _probe_through_tmux():
        return False
    from textual_image import renderable
    if renderable.Image not in (renderable.TGPImage, renderable.SixelImage):
        return False
    import textual_image.widget  # noqa: F401 -- also asks the terminal for its cell size
    return True


def filter_list(title, labels, multi=False, initial=None, hint="", cursor=0, extras=None, locked=None, locked_note="",
                hotkeys=(), note_text=None, on_note=None, esc_asks=True, hidden=None, status=None, diff_marks=True,
                session=None, poll=None, links=None, on_hotkey=None, preview=None, row_note=None, key_help=None, filters=""):
    """Modal list: vim keys for moving and acting, Emacs keys for editing the filter.

    Normal mode: j/k ↑/↓ ^N/^P move · g/G top/bottom · ^D/^U half page · ^F/^B/PgUp/PgDn/^V page · / filter ·
    Enter picks · Esc/q/^G clears the filter, then goes back · ? help. Multi mode adds Space/Tab toggle · a all/none
    shown · o view (all / on / changed) · u revert · w note. After `/`, typed text filters (every
    space-separated term must appear in a label, case-insensitive); Tab keeps the filter, Enter does too in multi
    mode and picks the highlighted row in single mode, Esc clears it.

    Single mode returns the chosen index, or None on Esc. Multi mode returns the list of on/off states on Enter;
    Esc asks whether to keep or revert pending changes (esc_asks=False: it just returns None).
    cursor: index the highlight starts on.
    extras: per label, a list of (text, color) drawn after it, right-aligned (color: green, red, cyan or dim); a long
    label is cut with "…" to leave them room. They are not matched by the filter.
    locked: optional per-label flags; those rows are greyed out, can't be toggled, and show locked_note
    (one string, or one per label).
    on_note: optional callable(label index, text) -> message, called with a line typed after `w` on a row (multi mode);
    note_text(label index) gives the text to start from.
    hotkeys: normal-mode keys that return (key, label index) for the highlighted row instead of acting.
    key_help: optional (keys, what they do) pairs that `?` lists as this screen's keys; without it, it lists the hint's
    entries. Every hint line starts with "? help".
    hidden: optional per-label flags; those rows are left out (and drawn dim) until `z` reveals them.
    status(states) -> text, or (text, color): the status row's text, after the pending counts (+on −off); its right end
    shows the cursor's row and "N/M shown" when the text leaves room (only the numbers when just those fit). filters: the caller's own filters, shown on the
    filter line after the typed text. diff_marks: show ➕/➖ against `initial` (else ✅/⬜ only).
    session: a dict the caller keeps so selection, view, revealed rows, filter text, cursor and scroll survive reopening
    the list (carry_place keeps them across passes that list the same rows).
    poll: optional callable, called on the list's thread every POLL_MS while it waits for a key; the list is then redrawn,
    so poll can update extras in place (and status can read what it changed).
    links: optional per-label lists of the label indexes switched together with it (multi mode): Space/Tab and `a`
    set them all to the toggled row's new state (locked ones excepted).
    on_hotkey: optional callable(key, label index) -> bool, tried first for a hotkey; True means it handled the key
    in place (the list stays open and is redrawn, so it can update extras), False returns (key, index) as usual.
    preview: optional callable(label index) -> path of an image file, or None; the list then shares the screen with an
    image pane showing the highlighted row's image (blank when there is none), updated as the cursor and filter change.
    Only in a terminal that draws real images (Kitty graphics or Sixel), and not inside tmux; elsewhere there is no pane.
    row_note: optional callable(label index) -> text; when non-empty for the highlighted row it replaces the status
    line (below a notice and a locked row's note).
    """
    if preview and not _in_session():  # a session asks the terminal once, before its app starts
        _app_class()  # first: it sets up Textual's environment
        if not _draws_images():
            preview = None
    return _run(_ListModel(title, labels, multi, initial, hint, cursor, extras, locked, locked_note, hotkeys, note_text,
                           on_note, esc_asks, hidden, status, diff_marks, session, poll, links, on_hotkey, preview, row_note,
                           key_help, filters))


PLACE = ("row", "query", "view_mode", "top")  # the session entries carry_place keeps


def carry_place(place, keys, session):
    """Start a list's session where its last pass left off (row, filter text, view, scroll) when this pass lists the
    same keys; place is a dict the caller keeps across passes. Only what is shown is kept, never the rows' states."""
    if place.get("keys") == keys:
        session.update({k: v for k, v in place["session"].items() if k in PLACE})
    place.update(keys=list(keys), session=session)
