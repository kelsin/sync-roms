# ScreenScraper API notes

Sources: official page https://api.screenscraper.fr/webapi2.php (fetched via a summarizing tool, so wording is paraphrased; the page itself says v2 is beta and may change) and ES-DE's `ScreenScraper.cpp` (XML parser). No authenticated or live call was made. Every fact is tagged **[documented]** (official page), **[ES-DE source]**, or **[memory/unverified]**.

## REQUIRED: developer credentials (read first)

- **[documented]** Every call carries developer credentials `devid`, `devpassword`, `softname` in addition to the user's `ssid`/`sspassword`. The page says the API may only be integrated into fully free, distributed applications; other uses need prior authorization. A bad dev login returns 403.
- **[documented]** To obtain them: present the software on the ScreenScraper forum (developer section); the team validates it and issues devid/devpassword.
- **[documented]** HTTP 426 means the scraping software is blacklisted (non-compliant/obsolete), so an unregistered or abused softname can be blocked.
- **Consequence for Task 2:** the user must request dev credentials from ScreenScraper (forum thread), then settings need `devid`, `devpassword`, `softname` plus user `ssid`, `sspassword`. Open question for the user: ship the project's own devid (requires approval) or have each user supply their own. Task 2's settings names depend on this answer. **Resolved:** sync-roms ships its own developer credentials as constants (`DEV_ID`, `DEV_PASSWORD` in `screenscraper.py`), as ES-DE does; users supply only their login.

## Base URL and auth

- **[documented/ES-DE commit]** `https://api.screenscraper.fr/api2/<endpoint>.php` (ES-DE moved from `www.screenscraper.fr/api2`). Query params: `devid`, `devpassword`, `softname`, `ssid`, `sspassword`, `output` (`xml`|`json`|`ini`).

## jeuInfos.php lookup parameters

- **[documented]** `systemeid` (numeric, from systemesListe.php), `romnom` (filename with extension, no path; a path gives 400), `romtaille` (bytes), `romtype` (`rom`|`iso`|folder), `crc`, `md5`, `sha1` (give at least one, ideally all three plus romtaille), `serialnum` (force lookup by serial), `gameid` (force lookup by numeric game id; no ROM info returned in that case).
- Hash matched for zip/CHD: **not documented** on the page read. [memory/unverified] ScreenScraper matches the hash of the file as given (so for a zip, the zip's own md5/sha1/crc, unlike No-Intro DATs that hash contents); for CHD, the whole CHD file. Task design should send `romnom` + `romtaille` + hashes of the file itself and fall back to name-only (`romnom`) lookup when no hash match. As built, a lookup sends `romnom` and `romtaille` with whatever hashes it has (not always any, see "As built" below), so ScreenScraper itself falls back to the name; the result is labelled a hash match only when the matched ROM's hashes (`jeu.rom`/`jeu.roms`) include one that was sent.
- Unknown hash/name still can match by `romnom`+`systemeid`. [memory/unverified]

## jeuInfos.php response fields

JSON shape is [memory/unverified]; XML shape is [ES-DE source] (the JSON mirrors it). Root `response` (JSON) / `Data` (XML); game at `response.jeu` (XML: `jeux/jeu`, `id` attribute).

| Data | XML [ES-DE source] | JSON [memory/unverified] |
|---|---|---|
| id | `jeu@id` | `jeu.id` |
| names | `noms/nom@region` | `jeu.noms[] = {region, text}` |
| description | `synopsis@langue` | `jeu.synopsis[] = {langue, text}` |
| dates | `dates/date@region` (`YYYY-MM-DD` or `YYYY`) | `jeu.dates[] = {region, text}` |
| genres | `genres/genre@langue` | `jeu.genres[] = {id, noms:[{langue,text}]}` (shape differs from XML; verify) |
| players | `joueurs` | `jeu.joueurs.text` (e.g. `1-2`) |
| rating | `note` (out of 20; ES-DE divides by 20 into stars) | `jeu.note.text` |
| developer / publisher | `developpeur`, `editeur` | `jeu.developpeur.text`, `jeu.editeur.text` |
| system | `systeme@id`, `@parentid` | `jeu.systeme` |
| matched rom | `rom/rommd5` | `jeu.rom` / `jeu.roms` (`rommd5`, `romsha1`, `romcrc`); sync-roms labels a match "hash" only when one of these equals a hash it sent |
| media | `medias/media@type,@region,@format` | `jeu.medias[] = {type, parent, url, region, crc, md5, sha1, size, format}` |

- Placeholder/non-game results are named `ZZZ(NOTGAME)` [ES-DE source]. ES-DE discards them; sync-roms records them for `scrape review` (see "As built").
- In ES-DE the media file extension comes from the `format` field and URL spaces become `%20` [ES-DE source]. sync-roms does neither (see "As built").
- Date keys in docs are per-region (`date_fr`, `date_eu`, `date_us`, `date_jp`) [documented]; that is the older flat shape. Prefer the `dates[]` list [ES-DE source], verify when live.

## Media types and ES-DE folders

Official list of type strings [documented]: `ss`, `sstitle`, `video`, `fanart`, `videotable`, `videofronton16-9`, `videodmd`, `wheel`, `wheel-hd`, `wheel-tarcisios`, `marquee`, `screenmarquee`, `overlay`, `steamgrid`, `box-2D`, `box-2D-side`, `box-2D-back`, `box-texture`, `box-scan`, `support-texture`, `support-scan`, `manuel`, `flyer`, `maps`, `figurine`, bezels (`bezel-4-3`, `bezel-16-9`, `-v`, `-cocktail`). Region suffix in parentheses, e.g. `manuel(eu)`.

| ScreenScraper type | ES-DE folder | Status |
|---|---|---|
| `box-2D` | covers | type [documented]; mapping [memory/unverified], matches brief |
| `box-3D` | 3dboxes | **`box-3D` NOT in the official list read**; [memory/unverified] it exists in practice. Verify live. |
| `box-2D-back` | backcovers | type [documented] |
| `ss` | screenshots | [documented] |
| `sstitle` | titlescreens | [documented] |
| `marquee` | marquees | type [documented]; `wheel`/`wheel-hd` are treated as equivalent marquee fallbacks by ES-DE [ES-DE source]; sync-roms prefers them to `marquee` (see "As built") |
| `video` | videos | [documented]; ES-DE also falls back to `video-normalized` [ES-DE source] |
| `manuel` | manuals | [documented] |
| `fanart` | fanart | [documented] |
| `support-2D` | physicalmedia | **`support-2D` NOT in official list read** (only `support-texture`, `support-scan`); [memory/unverified]. Verify live. |
| `mixrbv1` / `mixrbv2` | miximages | **NOT in official list read**; [memory/unverified] these are RBV mix images. Verify live. |

Mapping to ES-DE folder names is from the task brief/ES-DE conventions, not from ScreenScraper.

## Region / language fallback

All [ES-DE source] (ES-DE's practice, not an API rule; sync-roms has no user region or language, its orders are under "As built"):
- Name and date: user region, then `wor`, `us`, `ss`, `eu`, `jp`.
- Description: user language, then `en`, `wor`.
- Genre: user language, then `en`.
- Media (except video, fanart): user region, then `wor`, `us`, `eu`, `jp`, `cus`.
- Video: first entry.
Region short codes come from regionsListe.php (`nomcourt`), language codes from languesListe.php [documented].

## jeuRecherche.php (search)

**[memory/unverified]** Not on the official page read. Assumed parameters `systemeid`, `recherche` (the name to search), and
response `response.jeux[]` of game dicts shaped like `jeu` (`id`, `noms[]`). Verify live. Where sync-roms uses it is
under "As built".

## ssuserInfos.php (quota)

**[documented]** fields (under `response.ssuser` [memory/unverified for the nesting; ES-DE reads `ssuser` > `requeststoday`, `maxrequestsperday`, `niveau`, `id`]):
`maxthreads`, `maxrequestsperday`, `requeststoday`, `maxrequestspermin` (misspelled `maxrequestsperdmin` elsewhere on the page), `maxrequestskoperday`, `requestskotoday` (negative-result calls), `maxdownloadspeed` (Ko/s).
- ES-DE treats `niveau == "0"` as bad username/password [ES-DE source].
- Values are strings in XML; likely strings in JSON too [memory/unverified]. Parse defensively.

## systemesListe.php

**[documented]** per system: `id`, `parentid`, `extensions`, `compagnie`, `type`, `datedebut`, `datefin`, `romtype`, `supporttype`, `noms` (`nom_xx`, `nom_recalbox`, `nom_retropie`, `nom_launchbox`, `nom_hyperspin`, `noms_commun`), `medias` groups. Needed to map our system ids to `systemeid` (Task for systems.json). JSON nesting [memory/unverified]: `response.systemes[]`.

## HTTP codes

All [documented]:
| Code | Meaning |
|---|---|
| 400 | malformed request (missing data, path in romnom, bad hash format) |
| 401 | API closed to non-members/inactive, or server saturated |
| 403 | login failed (check dev credentials) |
| **404** | **game/ROM not found** |
| 423 | API fully closed |
| 426 | software blacklisted |
| 429 | thread/rate limit reached; slow down |
| **430** | **daily scrape quota exceeded** |
| 431 | too many unrecognized ROMs scraped today |

Not-found body is plain text, not JSON (ES-DE checks a body starting with `Erreur : Rom`) [ES-DE source]; it may also come with HTTP 200 on some paths [memory/unverified], so handle both the 404 and the text body.

## As built

What sync-roms does today (`screenscraper.py`, `scrape_online.py`), where it differs from the research above.

- **Region and language.** There is no user region or language: `parse_game` is always called with no regions and `LANGUAGES` is `("en",)`. Every text pick falls back to the first entry with text (`_pick`, `fallback=True`, which no caller turns off).
  - Name and date: `wor`, `us`, `ss`, `eu`, `jp`, then the first entry with text in any region.
  - Description: `en`, `wor`, then the first synopsis in any language.
  - Genre: the genres in order; each gives its `en` name, else its first name in any language; the first genre with a name is used.
  - Media, video and fanart included: `wor`, `us`, `eu`, `jp`, `cus`, then an entry with no region, then any other region. In a tie the first entry listed wins, except among marquee types.
- **Marquees.** `wheel-hd`, `wheel` and `marquee` all fill `marquees`. In a region tie `TYPE_PREFERENCE` takes them in that order, so `marquee` is the last choice.
- **Media files.** `format` is never read. The extension comes from the downloaded file's first bytes: `%PDF` gives `.pdf` for manuals, an `ftyp` box gives `.mp4` for videos, and PNG, JPEG or GIF magic gives `.png`, `.jpg` or `.gif` for everything else. A file that is none of these (an error page, `NOMEDIA`, empty) is left out.
- **Media URLs.** A URL is not percent-encoded. One with a space or control character is rejected by `Client._open` as a bad URL (`ApiError`), which the download loop does not catch (it skips a file only on `NotFound`, `MediaRefused` or `Transient`), so the whole ROM ends "failed" with no entry.
- **Hashes sent.** Not every lookup carries all three hashes.
  - Bucket with no local mirror: only `md5`, taken from the ETag; nothing for a multipart upload's ETag, which is not the file's MD5.
  - Storage folder or local mirror, file under 64 MiB (`HASH_MAX`): `md5`, `sha1` and `crc` of the file.
  - Storage folder or local mirror, file of 64 MiB or more: cached hashes if there are any, else none; when a lookup sent without hashes finds nothing, the file is hashed and looked up once more.
- **Non-games.** A result is a non-game when any of its names starts with `ZZZ(NOTGAME)`, in any case. It is not discarded: the ROM gets no entry and is recorded in `scrapes/notgames.json` with what ScreenScraper says about it, for `scrape review`.
- **Search.** `jeuRecherche.php` is used by `scrape match` with a name, by `scrape review`'s `s` and `t` answers, and by the skills' `match-translations/scripts/search.py` and `dedup-names/scripts/search_games.py`. Results whose title is a `ZZZ(NOTGAME)` name are dropped; the title is picked by `wor`, `us`, `ss`, `eu`, `jp`, then any region.
- **Quota.** Of the `ssuser` fields only `maxthreads`, `requeststoday` and `maxrequestsperday` are read. A run scrapes on `maxthreads` threads; nothing enforces a per-minute cap. A 429, a 5xx or a network error is retried 3 times, after 10, 20 and 40 s. A 430 or 431 (quota), or a 401, 403, 423 or 426 (refused), stops the run; so do 3 ROMs in a row that stay unreachable after their retries.
- **Never used.** `romtype`, `serialnum`, `systemesListe.php` (the ids are in `systems.json`), `niveau` and `video-normalized`.

## Fixtures

`tests/fixtures/screenscraper/` files are **HAND-WRITTEN from the documented/remembered shape, not captured from live calls** (no credentials were used). The JSON field nesting of `jeuInfos` is [memory/unverified]; re-capture real responses before relying on them. Contents are invented placeholder data.
