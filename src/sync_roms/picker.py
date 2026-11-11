"""Interactive curses pickers."""
import curses
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


def show_help(stdscr, lines):
    """Draw the key list over the screen and wait for any key."""
    h, w = stdscr.getmaxyx()
    lines = ["Keybindings", ""] + lines + ["", "Press any key to close"]
    top = max(0, (h - len(lines)) // 2)
    left = max(0, (w - max(cell_width(l) for l in lines)) // 2 - 2)
    stdscr.erase()
    for n, line in enumerate(lines[:h - 1]):
        stdscr.addnstr(top + n, left, line, max(1, w - left - 1), curses.A_BOLD if n == 0 else 0)
    stdscr.refresh()
    stdscr.timeout(-1)
    try:
        stdscr.get_wch()
    except curses.error:
        pass


def cell_width(text):
    """Terminal cells text takes up (emoji and CJK are two wide)."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def line_key(text, pos, k):
    """Emacs-style single-line editing. Returns (text, cursor position), or None if k isn't an editing key.
    ^A/^E start/end · ^B/^F left/right · ^D delete char · ^K kill to end · ^U kill to start · ^W kill word."""
    if k in ("\x01", curses.KEY_HOME):
        return text, 0
    if k in ("\x05", curses.KEY_END):
        return text, len(text)
    if k in ("\x02", curses.KEY_LEFT):
        return text, max(0, pos - 1)
    if k in ("\x06", curses.KEY_RIGHT):
        return text, min(len(text), pos + 1)
    if k in ("\x04", curses.KEY_DC):
        return text[:pos] + text[pos + 1:], pos
    if k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
        return (text[:pos - 1] + text[pos:], pos - 1) if pos else (text, pos)
    if k == "\x0b":
        return text[:pos], pos
    if k == "\x15":
        return text[pos:], 0
    if k == "\x17":
        start = text.rfind(" ", 0, len(text[:pos].rstrip())) + 1
        return text[:start] + text[pos:], start
    if isinstance(k, str) and k.isprintable():
        return text[:pos] + k + text[pos:], pos + 1
    return None


def move_key(k, cur, last, view):
    """The new cursor row for a movement key (arrows, ^N/^P, PgUp/PgDn/^V, Home/End), or None if k isn't one."""
    if k in (curses.KEY_UP, "\x10"):
        return max(0, cur - 1)
    if k in (curses.KEY_DOWN, "\x0e"):
        return min(last, cur + 1)
    if k == curses.KEY_PPAGE:
        return max(0, cur - view)
    if k in (curses.KEY_NPAGE, "\x16"):
        return min(last, cur + view)
    if k == curses.KEY_HOME:
        return 0
    if k == curses.KEY_END:
        return max(0, last)
    return None


def read_line(stdscr, prompt, text=""):
    """Edit one line on the bottom row (see line_key). Returns the text on Enter, or None on Esc or ^G."""
    pos = len(text)
    curses.curs_set(1)
    while True:
        h, w = stdscr.getmaxyx()
        stdscr.addnstr(h - 1, 0, " " * (w - 1), w - 1)
        stdscr.addnstr(h - 1, 0, prompt + text, w - 1, curses.A_BOLD)
        stdscr.move(h - 1, min(w - 1, cell_width(prompt + text[:pos])))
        try:
            k = stdscr.get_wch()
        except curses.error:
            continue
        if k in ("\n", "\r", curses.KEY_ENTER):
            return text
        if k in ("\x1b", "\x07"):
            return None
        edited = line_key(text, pos, k)
        if edited:
            text, pos = edited


POLL_MS = 200  # how often filter_list calls its poll while no key comes


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
    poll: optional callable, called on the curses thread whenever no key came for POLL_MS; the list is then redrawn,
    so poll can update extras in place (and status can read what it changed).
    links: optional per-label lists of the label indexes switched together with it (multi mode): Space/Tab and `a`
    set them all to the toggled row's new state (locked ones excepted).
    on_hotkey: optional callable(key, label index) -> bool, tried first for a hotkey; True means it handled the key
    in place (the list stays open and is redrawn, so it can update extras), False returns (key, index) as usual.
    """
    os.environ.setdefault("ESCDELAY", "25")
    lowered = [l.casefold() for l in labels]
    start = list(initial) if initial is not None else [False] * len(labels)
    locked = locked or [False] * len(labels)
    hidden = hidden or [False] * len(labels)
    hidden_count = sum(hidden)
    session = {} if session is None else session

    def linked(rows):
        """rows and the rows linked to them, without locked ones."""
        out = dict.fromkeys(rows)
        for i in rows:
            out.update(dict.fromkeys(links[i] if links else ()))
        return [i for i in out if not locked[i]]

    def run(stdscr):
        curses.use_default_colors()
        green_a = red_a = cyan_a = yellow_a = 0
        if curses.has_colors():
            curses.start_color()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_RED, -1)
            curses.init_pair(3, curses.COLOR_CYAN, -1)
            curses.init_pair(4, curses.COLOR_YELLOW, -1)
            green_a, red_a, cyan_a, yellow_a = (curses.color_pair(n) for n in (1, 2, 3, 4))
        colors = {"green": green_a, "red": red_a, "cyan": cyan_a, "yellow": yellow_a, "dim": curses.A_DIM}
        state = list(session["sel"]) if "sel" in session else list(start)
        view_mode = session.get("view_mode", 0)  # multi: 0 all rows, 1 only rows that are on, 2 only rows changed
        revealed = session.get("revealed", False)
        restore = session.get("row")
        query, qpos, typing = "", 0, False
        cur, top = cursor, 0
        notice = ""
        if poll:
            stdscr.timeout(POLL_MS)
        while True:
            terms = query.casefold().split()
            vis = [i for i, l in enumerate(lowered) if (revealed or not hidden[i]) and all(t in l for t in terms)
                   and (view_mode == 0 or (state[i] if view_mode == 1 else state[i] != start[i]))]
            vis.sort(key=lambda i: hidden[i])  # revealed rows go last; stable within each group
            try:
                cur = vis.index(restore)
            except ValueError:
                pass
            restore = None
            cur = max(0, min(cur, len(vis) - 1))
            session.update(sel=state, view_mode=view_mode, revealed=revealed, row=vis[cur] if vis else None)
            h, w = stdscr.getmaxyx()
            view = max(1, h - 4)
            if cur < top:
                top = cur
            elif cur >= top + view:
                top = cur - view + 1
            curses.curs_set(1 if typing else 0)
            stdscr.erase()
            stdscr.addnstr(0, 0, title, w - 1, cyan_a | curses.A_BOLD)
            stdscr.addnstr(1, 0, "🔎 " + query, w - 1)
            stdscr.addnstr(2, 0, TYPING_HINT if typing else hint or (MULTI_HINT if multi else SINGLE_HINT), w - 1, curses.A_DIM)
            for pos in range(top, min(len(vis), top + view)):
                i = vis[pos]
                attr = curses.A_REVERSE if pos == cur else 0
                if locked[i]:
                    line = f"🔒 {labels[i]}"
                    attr |= curses.A_DIM
                elif multi:
                    if not diff_marks or state[i] == start[i]:
                        mark = "✅" if state[i] else "⬜"
                        attr |= green_a if state[i] and not diff_marks else 0
                    else:
                        mark = "➕" if state[i] else "➖"
                        attr |= green_a if state[i] else red_a
                    line = f"{mark} {labels[i]}"
                else:
                    line = labels[i]
                if hidden[i]:
                    attr |= curses.A_DIM
                stdscr.addnstr(pos - top + 3, 0, line, w - 1, attr)
                x = cell_width(line)
                for text, color in (extras[i] if extras else []):
                    if x >= w - 1:
                        break
                    stdscr.addnstr(pos - top + 3, x, text, w - 1 - x, attr | colors[color])
                    x += cell_width(text)
            line, line_color = status(state) if status else f"{len(vis)}/{len(labels)} shown", None
            if isinstance(line, tuple):
                line, line_color = line
            if multi and diff_marks:
                added = sum(1 for a, b in zip(state, start) if a and not b)
                removed = sum(1 for a, b in zip(state, start) if b and not a)
                line += f" · +{added} −{removed} pending"
            if multi and (diff_marks or view_mode):
                line += f" · view: {('all', 'on only', 'changed only')[view_mode]}"
            if not revealed and hidden_count:
                line += f" · {hidden_count} hidden (press z)"
            if vis and locked[vis[cur]]:
                line = f"🔒 {locked_note[vis[cur]] if isinstance(locked_note, list) else locked_note}"
            if notice:
                line = notice
                notice = ""
            stdscr.addnstr(h - 1, 0, " " * (w - 1), w - 1)
            stdscr.addnstr(h - 1, 0, line, w - 1, curses.A_BOLD | (colors[line_color] if line_color else 0))
            if typing:
                stdscr.move(1, min(w - 1, 3 + cell_width(query[:qpos])))
            try:
                k = stdscr.get_wch()
            except curses.error:
                if poll:
                    poll()
                continue
            if typing:
                edited = line_key(query, qpos, k)
                if k in ("\n", "\r", curses.KEY_ENTER):
                    typing = False
                elif k in ("\x1b", "\x07"):
                    query, qpos, typing = "", 0, False
                    cur = top = 0
                elif edited:
                    if edited[0] != query:
                        cur = top = 0
                    query, qpos = edited
                else:
                    moved = move_key(k, cur, len(vis) - 1, view)
                    cur = cur if moved is None else moved
                continue
            moved = move_key(k, cur, len(vis) - 1, view)
            if k in hotkeys and (vis or multi):
                if on_hotkey and on_hotkey(k, vis[cur] if vis else None):
                    continue
                return k, (vis[cur] if vis else None)
            if moved is not None:
                cur = moved
            elif k == "/":
                typing, qpos = True, len(query)
            elif k == "?":
                show_help(stdscr, help_lines(multi, hint, hidden_count, bool(on_note)))
                stdscr.timeout(POLL_MS if poll else -1)
            elif k == "j":
                cur = min(len(vis) - 1, cur + 1)
            elif k == "k":
                cur = max(0, cur - 1)
            elif k == "g":
                cur = 0
            elif k == "G":
                cur = len(vis) - 1
            elif k == "\x04":
                cur = min(len(vis) - 1, cur + max(1, view // 2))
            elif k == "\x15":
                cur = max(0, cur - max(1, view // 2))
            elif k == "\x06":
                cur = min(len(vis) - 1, cur + view)
            elif k == "\x02":
                cur = max(0, cur - view)
            elif k in ("\x1b", "q", "\x07"):
                if query:
                    query, qpos = "", 0
                    cur = top = 0
                    continue
                if not multi or not esc_asks:
                    return None
                if state == start:
                    return state
                stdscr.addnstr(h - 1, 0, " " * (w - 1), w - 1)
                stdscr.addnstr(h - 1, 0, f"Keep +{added} −{removed} pending change(s)?  y/Enter keep · u revert · any other key keeps editing",
                               w - 1, curses.A_BOLD | red_a)
                stdscr.timeout(-1)  # wait for the answer even when polling
                try:
                    answer = stdscr.get_wch()
                except curses.error:
                    continue
                finally:
                    if poll:
                        stdscr.timeout(POLL_MS)
                if answer in ("y", "Y", "\n", "\r", curses.KEY_ENTER):
                    return state
                if answer in ("u", "U"):
                    return list(start)
            elif k in ("\n", "\r", curses.KEY_ENTER):
                if multi:
                    return state
                if vis:
                    return vis[cur]
            elif k == "z" and hidden_count:
                revealed = not revealed
            elif not multi:
                continue
            elif k == "u":
                state = list(start)
                notice = "Reverted this list to how it was when opened"
            elif k in ("o", "\x0f"):
                view_mode = (view_mode + 1) % 3
                cur = top = 0
            elif k in ("\t", " ") and vis:
                if not locked[vis[cur]]:
                    target = not state[vis[cur]]
                    for i in linked([vis[cur]]):
                        state[i] = target
            elif k == "w" and vis and on_note and not locked[vis[cur]]:
                text = read_line(stdscr, "Note (empty clears, Esc cancels): ", note_text(vis[cur]) if note_text else "")
                if text is not None:
                    notice = on_note(vis[cur], text.strip())
            elif k in ("a", "\x01") and vis:
                free = [i for i in vis if not locked[i]]
                target = not all(state[i] for i in free)
                for i in linked(free):
                    state[i] = target
    return curses.wrapper(run)
