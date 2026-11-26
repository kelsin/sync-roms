# Collections page on GitHub Pages

## Intent

Host the collections page publicly at `https://sync-roms.games/`, a GitHub Pages site. The root lists users (only `kelsin` at first); `/collections/<user>/` is that user's collections page with a link back to the list; `/collections` and `/collections/` lead back to the root. `sync-roms collections publish` updates the site with the latest page.

## Goals

- One command publishes a user's latest page, committing and pushing only when it changed.
- The local page (`collections page`, `collections share`) stays one self-contained file, exactly as today.
- The public page is split into proper files: `index.html`, `page.css`, `page.js`, art as `.webp` files.
- The public page has no storage paths: no game `paths`, no Copy column. Titles, systems, years, sizes, tags and translation flags stay.
- A "← All users" link at the top on the public page only.
- A guide for the one-time GitHub and DNS setup.

## Non-goals / anti-goals

- No game list in the `sync-roms` repo (CLAUDE.md rule): the built site lives in a separate repo, never a `gh-pages` branch here.
- No GitHub Actions deploy.
- No multi-user publishing flow beyond folders per user: the root list is built from the folders present.

## Approaches

1. **Separate Pages repo** (`kelsin/sync-roms.games`) holding only the built site; sync-roms keeps a clone and pushes. **Picked**: keeps game lists out of the public code repo, simple, scales to more users as folders.
2. `gh-pages` branch in this repo: breaks the no-game-list rule and every clone gets the lists.
3. Actions deploy with nothing committed: the page still has to reach the Action (release asset, dispatch payload), more moving parts for no gain.

## Design

### Template

`data/collections-page.html` splits into `data/collections-page/page.html`, `page.css`, `page.js`.

- Local build: CSS and JS inlined into the HTML, art as `data:` URIs: one self-contained file, the same page as now.
- Public build: `index.html` links `page.css` and `page.js`; art written to `art/<id>-<band|box|totk>.webp`, the data referring to those relative paths.
- Public data drops each game's `paths`; the template hides the Copy column when no game has paths.
- Public data has `home: "/"`; the template shows "← All users" linking to it only when set.

### Pages repo layout

```
CNAME                      sync-roms.games
index.html                 user list, built from collections/*/
collections/index.html     redirect to /
collections/<user>/        index.html, page.css, page.js, art/
```

GitHub Pages redirects `/collections` to `/collections/`, whose page redirects to `/`. The root index and the redirect come from sync-roms templates and are rebuilt on every publish.

### Command

`sync-roms collections publish [--user NAME] [--dry-run]`

- `--user` defaults to `getpass.getuser()`.
- The repo is the `pages_repo` setting in `settings.json`, default `git@github.com:kelsin/sync-roms.games.git` (builder's call: a setting so nothing is tied to one account in code beyond a default).
- Clones into `~/.sync-roms/cache/pages/` (pulls when present), replaces `collections/<user>/`, rebuilds the root index, redirect and `CNAME`, commits and pushes only when something changed, prints the URL. `--dry-run` builds and reports what would change without committing or pushing.
- Follows the CLI rules: subparser in `commands.build_parser`, help in `cli.TOPICS`, `cli.SUBCOMMANDS`, README tables (checked by `tests/test_readme.py`).

### Guide

`docs/github-pages.md`: create the repo, enable Pages from `main`, set the custom domain and enforce HTTPS, DNS for `sync-roms.games` (GitHub's four A and four AAAA records on the apex, `www` CNAME to `kelsin.github.io`), first `publish`.

## Left to the builder

- Exact markup and styling of the user list and back link (match the collections page's look).
- Git invocation details (subprocess `git`, commit message, author from the user's git config).
- Test structure, using a local bare repo as the remote.
