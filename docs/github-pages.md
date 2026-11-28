# Publishing your collections to GitHub Pages

`sync-roms collections publish` puts a public copy of your collections page at `https://sync-roms.games/collections/<user>/`, with a list of every user's page at `https://sync-roms.games/`, and rebuilds the pixel art page at `https://sync-roms.games/pixel-art/` (every picture of the spruceOS and ES-DE pixel themes, with its theme files and sizes). Building it needs the `SPRUCE` base theme in storage: without it nothing is published. The site is a GitHub repo served by GitHub Pages. These are the one-time steps to set it up.

The public page has no storage paths, but it does list your games; a game with no scraped name or saved title shows its file name (without the extension). The Pages repo is public and its history keeps every earlier publish, so games you remove stay readable there, and each commit carries your git author name and email. Each publish replaces only your own `collections/<user>/` folder and the shared `pixel-art/` page; other users' folders stay as they are.

## 1. Create the repo

On GitHub, create a public repository named `sync-roms.games`. Leave it empty: no README, license or `.gitignore`.

## 2. Point sync-roms at it

`collections publish` pushes to `git@github.com:kelsin/sync-roms.games.git` by default. If your repo is somewhere else:

```bash
sync-roms config set pages_repo git@github.com:<you>/sync-roms.games.git
```

Pushing uses your own git and SSH setup, so `git push` to that URL must work from this machine.

## 3. Publish once

```bash
sync-roms collections publish            # your login name as the folder
sync-roms collections publish --user NAME  # or another name: lowercase letters, digits, - and _
```

This creates the `main` branch, which GitHub needs before you can turn Pages on. `--dry-run` lists what would change and pushes nothing.

## 4. Turn on Pages

In the repo's **Settings → Pages**:

1. Set **Source** to **Deploy from a branch**, branch `main`, folder `/ (root)`, and save.
2. Set **Custom domain** to `sync-roms.games` and save. The `CNAME` file `collections publish` writes keeps it set.

## 5. Verify the domain

In your account's **Settings → Pages** (not the repo's), add `sync-roms.games` as a verified domain. GitHub shows a `TXT` record: add it at your registrar, then click **Verify**.

## 6. DNS at the registrar

For the apex `sync-roms.games`:

| Type | Value |
|---|---|
| `A` | `185.199.108.153` |
| `A` | `185.199.109.153` |
| `A` | `185.199.110.153` |
| `A` | `185.199.111.153` |
| `AAAA` | `2606:50c0:8000::153` |
| `AAAA` | `2606:50c0:8001::153` |
| `AAAA` | `2606:50c0:8002::153` |
| `AAAA` | `2606:50c0:8003::153` |

And for `www`: a `CNAME` to `<you>.github.io`.

## 7. HTTPS

Wait for GitHub to issue the certificate (the repo's Settings → Pages says when; it can take up to a day after DNS is right), then tick **Enforce HTTPS**.

## 8. Check

- `https://sync-roms.games/` lists the users.
- `https://sync-roms.games/collections` goes back to that list.
- `https://sync-roms.games/collections/kelsin/` shows the page, with **← All users** back to the list.
- `https://sync-roms.games/pixel-art/` shows the pixel art page, linked from the list.

After that, run `sync-roms collections publish` whenever your collections change. It commits and pushes only when something changed.
