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
                    hint="type to filter · ↑/↓ move · Enter continue · Esc quit")
    return None if i is None else options[i][1]


def pick_layout(layouts, default):
    """Returns a layout (firmware) name, or None on Esc. default: layout name the cursor starts on."""
    names = list(layouts)
    labels = [f"{l['label']}  ({l['roms_dir']}/ {l['bios_dir']}/)" for l in layouts.values()]
    i = filter_list("🗂️  Which firmware?", labels, cursor=names.index(default) if default in names else 0,
                    hint="type to filter · ↑/↓ move · Enter continue · Esc back")
    return None if i is None else names[i]


def device_layouts(device, layouts):
    """The layouts (firmwares) a device can run, in its own order: the first is its default."""
    return {name: layouts[name] for name in device["firmwares"]}


def saved_setup(saved, devices, layouts):
    """(device dict or None for Full, layout name) from a card's saved entry, or None if it no longer applies."""
    if not isinstance(saved, dict) or saved.get("layout") not in layouts:
        return None
    if saved.get("device") == "full":
        return None, saved["layout"]
    device = next((d for d in devices if d["id"] == saved.get("device")), None)
    return (device, saved["layout"]) if device and saved["layout"] in device["firmwares"] else None


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
            raise SystemExit(ui.yellow("👋 Cancelled."))
        device = choice if isinstance(choice, dict) else None
        offered = device_layouts(device, layouts) if device else layouts
        if len(offered) == 1:
            return device, next(iter(offered))
        layout = pick_layout(offered, current[1] if current else next(iter(offered)))
        if layout is not None:
            return device, layout


def pick_systems(rows, initial=None, state=None, editable=False):
    """rows: list of (label, has_roms, need_bytes, total_bytes); initial: indexes toggled on at start.
    Returns selected indexes, or None if quit.

    state: a dict kept by the caller so the selection, cursor and shown/hidden 0-ROM systems survive
    reopening the picker. editable: g (edit the highlighted system's games) and x (clear the card's games)
    close the picker and return ("games", row index) or ("clear", None); the caller reopens it with the same state.
    """
    state = {} if state is None else state
    ui.require_terminal("pick systems", "--systems a,b (or --systems all)")
    os.environ.setdefault("ESCDELAY", "25")

    def run(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        on = off = head = 0
        if curses.has_colors():
            curses.start_color()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_CYAN, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
            on, head, off = curses.color_pair(1), curses.color_pair(2), curses.color_pair(3)
        sel = state["sel"] if "sel" in state else [i in (initial or ()) for i in range(len(rows))]
        show_empty = state.get("show_empty", False)
        cur = top = 0
        restore = state.get("row")
        while True:
            # systems with ROMs first, then (when shown) the empty ones; stable within each group
            order = [i for i, r in enumerate(rows) if r[1]]
            if show_empty:
                order += [i for i, r in enumerate(rows) if not r[1]]
            if restore in order:
                cur = order.index(restore)
            restore = None
            cur = min(cur, len(order) - 1)
            state.update(sel=sel, show_empty=show_empty, row=order[cur] if order else None)
            stdscr.erase()
            h, w = stdscr.getmaxyx()
            hidden = len(rows) - len(order)
            stdscr.addnstr(0, 0, "🕹  Pick systems", w - 1, head | curses.A_BOLD)
            keys = ("↑/↓ move · space/tab toggle · a all on · n all off · "
                    "e show/hide 0-ROM systems" + (" · g games · x clear card's games" if editable else "")
                    + " · enter go · esc/q cancel")
            stdscr.addnstr(1, 0, keys, w - 1, curses.A_DIM)
            view = h - 4
            if cur < top:
                top = cur
            elif cur >= top + view:
                top = cur - view + 1
            for pos in range(top, min(len(order), top + view)):
                i = order[pos]
                mark = "✅" if sel[i] else "⬜"
                attr = (on if sel[i] else 0) | (curses.A_REVERSE if pos == cur else 0)
                if not rows[i][1]:
                    attr |= curses.A_DIM
                stdscr.addnstr(pos - top + 2, 0, f"{mark} {rows[i][0]}", w - 1, attr)
            need = sum(r[2] for r, on_ in zip(rows, sel) if on_)
            total = sum(r[3] for r, on_ in zip(rows, sel) if on_)
            status = f"{sum(sel)} selected · {ui.human_size(need)} to download ({ui.human_size(total)} total)"
            if hidden:
                status += f" · {hidden} systems with 0 ROMs hidden (press e)"
            stdscr.addnstr(h - 1, 0, status, w - 1, off | curses.A_BOLD)
            k = stdscr.getch()
            if k in (curses.KEY_UP, ord("k")):
                cur = max(0, cur - 1)
            elif k in (curses.KEY_DOWN, ord("j")):
                cur = min(len(order) - 1, cur + 1)
            elif k == curses.KEY_PPAGE:
                cur = max(0, cur - view)
            elif k == curses.KEY_NPAGE:
                cur = min(len(order) - 1, cur + view)
            elif k in (ord(" "), 9) and order:
                sel[order[cur]] = not sel[order[cur]]
            elif k == ord("a"):
                for i in order:
                    sel[i] = True
            elif k == ord("n"):
                sel = [False] * len(rows)
            elif k == ord("e"):
                show_empty = not show_empty
            elif k == ord("g") and editable and order:
                return "games", order[cur]
            elif k == ord("x") and editable:
                return "clear", None
            elif k in (10, 13, curses.KEY_ENTER):
                return [i for i, s in enumerate(sel) if s]
            elif k in (ord("q"), 27):
                return None
    return curses.wrapper(run)


def cell_width(text):
    """Terminal cells text takes up (emoji and CJK are two wide)."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def filter_list(title, labels, multi=False, initial=None, hint="", cursor=0, extras=None, locked=None, locked_note="",
                hotkeys=()):
    """Type-to-filter list. Every space-separated term must appear in a label (case-insensitive).

    Single mode returns the chosen index, or None on Esc. Multi mode (Tab toggles, or Space with no filter typed)
    returns the list of on/off states on Enter; Esc asks whether to keep or revert pending changes, ^R reverts
    them and ^O cycles the view (all / on / changed). cursor: index the highlight starts on.
    extras: per label, a list of (text, color) drawn after it (color: green, red, cyan or dim);
    they are not matched by the filter.
    locked: optional per-label flags; those rows are greyed out, can't be toggled, and show locked_note
    (one string, or one per label).
    hotkeys: control keys that, in single mode, return (key, label index) for the highlighted row instead of an index.
    """
    os.environ.setdefault("ESCDELAY", "25")
    lowered = [l.lower() for l in labels]
    start = list(initial) if initial is not None else [False] * len(labels)
    locked = locked or [False] * len(labels)

    def run(stdscr):
        curses.curs_set(1)
        curses.use_default_colors()
        green_a = red_a = cyan_a = 0
        if curses.has_colors():
            curses.start_color()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_RED, -1)
            curses.init_pair(3, curses.COLOR_CYAN, -1)
            green_a, red_a, cyan_a = (curses.color_pair(n) for n in (1, 2, 3))
        colors = {"green": green_a, "red": red_a, "cyan": cyan_a, "dim": curses.A_DIM}
        state = list(start)
        query = ""
        vis = list(range(len(labels)))
        cur, top = cursor, 0
        view_mode = 0  # multi: 0 all rows, 1 only rows that are on, 2 only rows changed in this session
        notice = ""
        while True:
            terms = query.lower().split()
            vis = [i for i, l in enumerate(lowered) if all(t in l for t in terms)
                   and (view_mode == 0 or (state[i] if view_mode == 1 else state[i] != start[i]))]
            cur = max(0, min(cur, len(vis) - 1))
            h, w = stdscr.getmaxyx()
            view = max(1, h - 4)
            if cur < top:
                top = cur
            elif cur >= top + view:
                top = cur - view + 1
            stdscr.erase()
            stdscr.addnstr(0, 0, title, w - 1, cyan_a | curses.A_BOLD)
            stdscr.addnstr(1, 0, "🔎 " + query, w - 1)
            keys = ("Tab/Space toggle · Enter done · Esc done/revert · ^R revert · ^A all shown · ^O view"
                    if multi else "↑/↓ move · Enter select · Esc back")
            stdscr.addnstr(2, 0, hint or keys, w - 1, curses.A_DIM)
            for pos in range(top, min(len(vis), top + view)):
                i = vis[pos]
                attr = curses.A_REVERSE if pos == cur else 0
                if locked[i]:
                    line = f"🔒 {labels[i]}"
                    attr |= curses.A_DIM
                elif multi:
                    if state[i] == start[i]:
                        mark = "✅" if state[i] else "⬜"
                    else:
                        mark = "➕" if state[i] else "➖"
                        attr |= green_a if state[i] else red_a
                    line = f"{mark} {labels[i]}"
                else:
                    line = labels[i]
                stdscr.addnstr(pos - top + 3, 0, line, w - 1, attr)
                x = cell_width(line)
                for text, color in (extras[i] if extras else []):
                    if x >= w - 1:
                        break
                    stdscr.addnstr(pos - top + 3, x, text, w - 1 - x, attr | colors[color])
                    x += cell_width(text)
            added = sum(1 for a, b in zip(state, start) if a and not b)
            removed = sum(1 for a, b in zip(state, start) if b and not a)
            status = f"{len(vis)}/{len(labels)} shown"
            if multi:
                status += f" · +{added} −{removed} pending · view: {('all', 'on only', 'changed only')[view_mode]}"
            if vis and locked[vis[cur]]:
                status = f"🔒 {locked_note[vis[cur]] if isinstance(locked_note, list) else locked_note}"
            stdscr.addnstr(h - 1, 0, status, w - 1, curses.A_BOLD)
            if notice:
                status = notice
                notice = ""
            stdscr.addnstr(h - 1, 0, " " * (w - 1), w - 1)
            stdscr.addnstr(h - 1, 0, status, w - 1, curses.A_BOLD)
            stdscr.move(1, min(w - 1, 3 + len(query)))
            try:
                k = stdscr.get_wch()
            except curses.error:
                continue
            if k == curses.KEY_UP:
                cur = max(0, cur - 1)
            elif k == curses.KEY_DOWN:
                cur = min(len(vis) - 1, cur + 1)
            elif k == curses.KEY_PPAGE:
                cur = max(0, cur - view)
            elif k == curses.KEY_NPAGE:
                cur = min(len(vis) - 1, cur + view)
            elif k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                query = query[:-1]
                cur = top = 0
            elif k == "\x15":  # ^U clears the filter
                query = ""
                cur = top = 0
            elif k == curses.KEY_HOME:
                cur = 0
            elif k == curses.KEY_END:
                cur = len(vis) - 1
            elif k == "\x1b":
                if not multi:
                    return None
                if state == start:
                    return state
                stdscr.addnstr(h - 1, 0, " " * (w - 1), w - 1)
                stdscr.addnstr(h - 1, 0, f"Keep +{added} −{removed} pending change(s)?  y/Enter keep · r revert · any other key keeps editing",
                               w - 1, curses.A_BOLD | red_a)
                answer = stdscr.get_wch()
                if answer in ("y", "Y", "\n", "\r", curses.KEY_ENTER):
                    return state
                if answer in ("r", "R"):
                    return list(start)
            elif k in ("\n", "\r", curses.KEY_ENTER):
                if multi:
                    return state
                if vis:
                    return vis[cur]
            elif k == "\x12" and multi:  # ^R
                state = list(start)
                notice = "Reverted this list to how it was when opened"
            elif k == "\x0f" and multi:  # ^O
                view_mode = (view_mode + 1) % 3
                cur = top = 0
            elif k in ("\t", " ") and multi and vis and (k == "\t" or not query):
                if not locked[vis[cur]]:
                    state[vis[cur]] = not state[vis[cur]]
            elif k == "\x01" and multi and vis:
                free = [i for i in vis if not locked[i]]
                target = not all(state[i] for i in free)
                for i in free:
                    state[i] = target
            elif k in hotkeys and not multi and vis:
                return k, vis[cur]
            elif isinstance(k, str) and k.isprintable():
                query += k
                cur = top = 0
    return curses.wrapper(run)
