# Collection editor: games-first, add key, settings menu

**Why:** editing a collection is mostly switching games on and off and adding more; the menu in front of that is in the way.

**Goals**
- Opening a collection shows its games as a toggle list. Switched-off games stay listed as ⬜ for the session (undo until leaving); leaving reconciles and saves as today.
- Title line shows art emoji + art label, name and description, refreshed after edits.
- `A` (or `+`) opens the system list (first row: all systems), then the toggle list with the usual tag filter (`s`, `c`, `/`). New games appear in the list on return.
- `S` opens a Settings menu (name, description, art) like the card editor's. It shows the art image (in terminals that draw images) while open; choosing art previews the choices (existing `pick_art`).

**Non-goals:** art image in the games view; any change to `tagui.py`/`tags.py` (another session is reworking tag UX; we rebase on top later).

**Approaches:** (1) title-line art only; (2) also an image pane in the games view. Picked 1, plus the image in the Settings menu.

**Calls made:** reuse `listedit.add_from_system`, `reconcile`, `pick_art` and the existing rename prompts; drop the old five-item menu from `edit_one`.
