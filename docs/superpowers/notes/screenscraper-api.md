# ScreenScraper API notes

Sources: official page https://api.screenscraper.fr/webapi2.php (fetched via a summarizing tool, so wording is paraphrased; the page itself says v2 is beta and may change) and ES-DE's `ScreenScraper.cpp` (XML parser). No authenticated or live call was made. Every fact is tagged **[documented]** (official page), **[ES-DE source]**, or **[memory/unverified]**.

## REQUIRED: developer credentials (read first)

- **[documented]** Every call carries developer credentials `devid`, `devpassword`, `softname` in addition to the user's `ssid`/`sspassword`. The page says the API may only be integrated into fully free, distributed applications; other uses need prior authorization. A bad dev login returns 403.
- **[documented]** To obtain them: present the software on the ScreenScraper forum (developer section); the team validates it and issues devid/devpassword.
- **[documented]** HTTP 426 means the scraping software is blacklisted (non-compliant/obsolete), so an unregistered or abused softname can be blocked.
- **Consequence for Task 2:** the user must request dev credentials from ScreenScraper (forum thread), then settings need `devid`, `devpassword`, `softname` plus user `ssid`, `sspassword`. Dev credentials must never be committed to the repo. Open question for the user: ship the project's own devid (requires approval) or have each user supply their own. Task 2's settings names depend on this answer.

## Base URL and auth

- **[documented/ES-DE commit]** `https://api.screenscraper.fr/api2/<endpoint>.php` (ES-DE moved from `www.screenscraper.fr/api2`). Query params: `devid`, `devpassword`, `softname`, `ssid`, `sspassword`, `output` (`xml`|`json`|`ini`).

## jeuInfos.php lookup parameters

- **[documented]** `systemeid` (numeric, from systemesListe.php), `romnom` (filename with extension, no path; a path gives 400), `romtaille` (bytes), `romtype` (`rom`|`iso`|folder), `crc`, `md5`, `sha1` (give at least one, ideally all three plus romtaille), `serialnum` (force lookup by serial), `gameid` (force lookup by numeric game id; no ROM info returned in that case).
- Hash matched for zip/CHD: **not documented** on the page read. [memory/unverified] ScreenScraper matches the hash of the file as given (so for a zip, the zip's own md5/sha1/crc, unlike No-Intro DATs that hash contents); for CHD, the whole CHD file. Task design should send `romnom` + `romtaille` + hashes of the file itself and fall back to name-only (`romnom`) lookup when no hash match.
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

- Placeholder/non-game results are named `ZZZ(NOTGAME)` [ES-DE source]; discard them.
- Media file extension comes from the `format` field; URL spaces become `%20` [ES-DE source].
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
| `marquee` | marquees | type [documented]; `wheel`/`wheel-hd` are treated as equivalent marquee fallbacks by ES-DE [ES-DE source] |
| `video` | videos | [documented]; ES-DE also falls back to `video-normalized` [ES-DE source] |
| `manuel` | manuals | [documented] |
| `fanart` | fanart | [documented] |
| `support-2D` | physicalmedia | **`support-2D` NOT in official list read** (only `support-texture`, `support-scan`); [memory/unverified]. Verify live. |
| `mixrbv1` / `mixrbv2` | miximages | **NOT in official list read**; [memory/unverified] these are RBV mix images. Verify live. |

Mapping to ES-DE folder names is from the task brief/ES-DE conventions, not from ScreenScraper.

## Region / language fallback

All [ES-DE source] (ES-DE's practice, not an API rule):
- Name and date: user region, then `wor`, `us`, `ss`, `eu`, `jp`.
- Description: user language, then `en`, `wor`.
- Genre: user language, then `en`.
- Media (except video, fanart): user region, then `wor`, `us`, `eu`, `jp`, `cus`.
- Video: first entry.
Region short codes come from regionsListe.php (`nomcourt`), language codes from languesListe.php [documented].

## jeuRecherche.php (search)

**[memory/unverified]** Not on the official page read. Assumed parameters `systemeid`, `recherche` (the name to search), and
response `response.jeux[]` of game dicts shaped like `jeu` (`id`, `noms[]`). Used only by `scrape match` with a name;
verify live.

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

## Fixtures

`tests/fixtures/screenscraper/` files are **HAND-WRITTEN from the documented/remembered shape, not captured from live calls** (no credentials were used). The JSON field nesting of `jeuInfos` is [memory/unverified]; re-capture real responses before relying on them. Contents are invented placeholder data.
