# Changelog

## [2.8.0](https://github.com/kelsin/sync-roms/compare/v2.7.0...v2.8.0) (2026-11-14)


### :video_game: Features

* **collections:** show an emoji for each collection's art in the editors ([#261](https://github.com/kelsin/sync-roms/issues/261)) ([ac7d710](https://github.com/kelsin/sync-roms/commit/ac7d710283a1cd5dbf06d456ee58393d8e4e603c))
* **convert:** show time left, print results as they finish and guard cards and storage ([#285](https://github.com/kelsin/sync-roms/issues/285)) ([b88f7ea](https://github.com/kelsin/sync-roms/commit/b88f7ea2362968695355b18ab3d54b50140ea9cb))
* **devices:** add AYN Thor Lite (Snapdragon 865) ([#273](https://github.com/kelsin/sync-roms/issues/273)) ([465ea32](https://github.com/kelsin/sync-roms/commit/465ea32d5f750396c8043e8e19060cd35c4add1c))
* **drivers:** sync suggested adreno gpu drivers to android cards ([#279](https://github.com/kelsin/sync-roms/issues/279)) ([40de07e](https://github.com/kelsin/sync-roms/commit/40de07e618eb1f711406eea6810438c404e4bc1f))
* **edit:** add games from a set across systems in the set and collection editors ([#259](https://github.com/kelsin/sync-roms/issues/259)) ([03a50e4](https://github.com/kelsin/sync-roms/commit/03a50e4d17d2977acb890290100c6b9d00e52618))
* **edit:** hide systems with no games when adding games ([#260](https://github.com/kelsin/sync-roms/issues/260)) ([4aa399d](https://github.com/kelsin/sync-roms/commit/4aa399d96a1f46f447d740658f49a975678f3e1e))
* **edit:** show collection, system and game art while browsing lists ([#282](https://github.com/kelsin/sync-roms/issues/282)) ([5dd5f98](https://github.com/kelsin/sync-roms/commit/5dd5f98da8a9c3519c350f6b3f0a5ab1ce64ecd9))
* **edit:** show proper names for mame and fbneo games ([#264](https://github.com/kelsin/sync-roms/issues/264)) ([e8815da](https://github.com/kelsin/sync-roms/commit/e8815da4c57821a31c357e7278eeccc5a8db79ea))
* **picker:** show the row, keep your place and make help findable ([#289](https://github.com/kelsin/sync-roms/issues/289)) ([88943de](https://github.com/kelsin/sync-roms/commit/88943de9741c486b4ae2832a7012314260e59264))
* **scrape:** show each rom, time left and quota, and keep finished roms on ctrl-c ([#286](https://github.com/kelsin/sync-roms/issues/286)) ([8579e20](https://github.com/kelsin/sync-roms/commit/8579e20a5f0e5ceed99249f55fc3b8122f6fc0fb))
* **scrape:** show the review's position, add quit and step back ([#287](https://github.com/kelsin/sync-roms/issues/287)) ([b2633c2](https://github.com/kelsin/sync-roms/commit/b2633c241c6ab79e52bf48b91adfa6065d75860b))
* **sets:** keep one version of each game and add variants ([#276](https://github.com/kelsin/sync-roms/issues/276)) ([beda660](https://github.com/kelsin/sync-roms/commit/beda6606fa8f665563729945320baedfbe48bb79))
* **theme:** add 20 collection pictures and redraw kart and sonic art ([#291](https://github.com/kelsin/sync-roms/issues/291)) ([6143ff6](https://github.com/kelsin/sync-roms/commit/6143ff6b22f8c6fac5c7a4d994871edd6e120f9b))
* **themes:** install art book next on a new es-de card before es-de is set up ([#263](https://github.com/kelsin/sync-roms/issues/263)) ([1a76778](https://github.com/kelsin/sync-roms/commit/1a767786e5a733666ccb29ff9282511de3093d08))


### :bug: Bug Fixes

* **cli:** make --dry-run, --yes and --quiet honest ([#266](https://github.com/kelsin/sync-roms/issues/266)) ([600551f](https://github.com/kelsin/sync-roms/commit/600551f33808c9efcbcaa2d1145f7fe66fe70689))
* **cli:** make help, usage errors and readme match the code ([#269](https://github.com/kelsin/sync-roms/issues/269)) ([d933600](https://github.com/kelsin/sync-roms/commit/d933600f98b4ca4f605155fe5eb5a7c8529c859f))
* close small leftovers from the review of the earlier fixes ([#293](https://github.com/kelsin/sync-roms/issues/293)) ([ff65ffd](https://github.com/kelsin/sync-roms/commit/ff65ffd19fc372a6d4ec06ffe6c4239d59a3801b))
* **edit:** keep collection and set edits on ctrl-c ([#268](https://github.com/kelsin/sync-roms/issues/268)) ([d7f2de6](https://github.com/kelsin/sync-roms/commit/d7f2de67c1e48785c116b16fdac0b9bd269ce380))
* **edit:** keep the open list's toggles on ctrl-c in the collections and sets editors ([#294](https://github.com/kelsin/sync-roms/issues/294)) ([0f24293](https://github.com/kelsin/sync-roms/commit/0f2429342b706cb9cf4b72d4d11fc541788807e3))
* **picker:** fit rows and the status to narrow terminals ([#290](https://github.com/kelsin/sync-roms/issues/290)) ([4bca165](https://github.com/kelsin/sync-roms/commit/4bca1656c44af9e07d36e2d503835bd798efa0db))
* **s3:** refresh the mirror's theme after themes update and size the connection pool ([#288](https://github.com/kelsin/sync-roms/issues/288)) ([6376173](https://github.com/kelsin/sync-roms/commit/6376173a938f8d2fd1e5d49e9c858342b3deb617))
* **scrape:** retry transient errors and stop on failures that are not about the rom ([#274](https://github.com/kelsin/sync-roms/issues/274)) ([3e45df6](https://github.com/kelsin/sync-roms/commit/3e45df688b09e984ef6f9c5d45d570be38c6011b))
* **settings:** treat a path answer as a storage folder on first run ([#270](https://github.com/kelsin/sync-roms/issues/270)) ([9f0eb20](https://github.com/kelsin/sync-roms/commit/9f0eb2011363f92c1ff43a1eba534e54f7777b4d))
* **sync:** count scraped media in the plan and end with a summary ([#267](https://github.com/kelsin/sync-roms/issues/267)) ([d875ddd](https://github.com/kelsin/sync-roms/commit/d875ddd5cecbd6a982204cc29f4d3ba0ade00338))
* **sync:** fail clearly when the storage folder or card path is missing ([#257](https://github.com/kelsin/sync-roms/issues/257)) ([b88fd0d](https://github.com/kelsin/sync-roms/commit/b88fd0ddd577fef1774a2485477780fea7e8c0c9))
* **upload:** match renames by content and stop on ctrl-c ([#262](https://github.com/kelsin/sync-roms/issues/262)) ([c822e28](https://github.com/kelsin/sync-roms/commit/c822e285b767090e2bb615b05a0d6fd87128168f))
* **upload:** run rename chains safely and match diff by content ([#265](https://github.com/kelsin/sync-roms/issues/265)) ([58330d5](https://github.com/kelsin/sync-roms/commit/58330d589c5a699a8854d05e4a7e2af748c80cf6))


### :zap: Performance Improvements

* **cache:** skip listing folders that did not change in cache update ([#275](https://github.com/kelsin/sync-roms/issues/275)) ([3572c01](https://github.com/kelsin/sync-roms/commit/3572c01811e937a9c9afce549fbbeafb59c9f82d))
* **convert:** unpack to local temp and cap jobs by free space ([#284](https://github.com/kelsin/sync-roms/issues/284)) ([2218fe3](https://github.com/kelsin/sync-roms/commit/2218fe330b36715afb7056e0dfad1eea5c65571f))
* **edit:** recount only the system that changed in the card editor ([#277](https://github.com/kelsin/sync-roms/issues/277)) ([d345b47](https://github.com/kelsin/sync-roms/commit/d345b4780a164b925f0d5b0b472d170afb585060))
* **picker:** run each editor's lists in one app ([#292](https://github.com/kelsin/sync-roms/issues/292)) ([f25731e](https://github.com/kelsin/sync-roms/commit/f25731e101e07f7463916e1ee076efca262af371))
* **s3:** skip the head request before a download when the cache has its size and etag ([#295](https://github.com/kelsin/sync-roms/issues/295)) ([b80e0c2](https://github.com/kelsin/sync-roms/commit/b80e0c2529d5f1e3396477f41abf6b1b3d2a9bc4))
* **scrape:** hash only files up to 64 MB in a storage folder ([#271](https://github.com/kelsin/sync-roms/issues/271)) ([aedca0d](https://github.com/kelsin/sync-roms/commit/aedca0dec05c1404e7412641e9fd97f725479dd7))
* **scrape:** remember media screenscraper does not offer ([#272](https://github.com/kelsin/sync-roms/issues/272)) ([2243b5f](https://github.com/kelsin/sync-roms/commit/2243b5f8f37559c24299f435505cde6af9627559))
* **sync:** skip work that cannot change the result ([#280](https://github.com/kelsin/sync-roms/issues/280)) ([6f77f57](https://github.com/kelsin/sync-roms/commit/6f77f57c98f56e84344b7b068f14bed7b3c145c9))


### :broom: Chores

* drop python 3.11 support ([#283](https://github.com/kelsin/sync-roms/issues/283)) ([c5329d4](https://github.com/kelsin/sync-roms/commit/c5329d43e014fcb61d855c4b791426b769139b8d))


### :book: Documentation

* **theme:** add generated gallery of the art book next collection art ([#278](https://github.com/kelsin/sync-roms/issues/278)) ([94145ea](https://github.com/kelsin/sync-roms/commit/94145ea9bc5c0181be85e87b7b2ec0c009ce0c56))
* **theme:** top-align the art gallery and credit art book next ([#281](https://github.com/kelsin/sync-roms/issues/281)) ([fd92108](https://github.com/kelsin/sync-roms/commit/fd921087a2aed97371de8f5d984d8730f034c317))

## [2.7.0](https://github.com/kelsin/sync-roms/compare/v2.6.0...v2.7.0) (2026-11-13)


### :video_game: Features

* **themeart:** add art for the usual kinds of personal collection ([#254](https://github.com/kelsin/sync-roms/issues/254)) ([c3620a9](https://github.com/kelsin/sync-roms/commit/c3620a90f0c73ccddc8aa1f984b4a8dec642f49b))
* **vita:** sync a game's DLC and newest update with it ([#256](https://github.com/kelsin/sync-roms/issues/256)) ([aff5315](https://github.com/kelsin/sync-roms/commit/aff5315cd7a51fe3af4d1cde04800cf1899ab867))

## [2.6.0](https://github.com/kelsin/sync-roms/compare/v2.5.0...v2.6.0) (2026-11-12)


### :video_game: Features

* **sync:** unmount the card when a sync finishes ([#252](https://github.com/kelsin/sync-roms/issues/252)) ([a07ac47](https://github.com/kelsin/sync-roms/commit/a07ac471b40412ca45a95b94cafd4f81252492d3))

## [2.5.0](https://github.com/kelsin/sync-roms/compare/v2.4.1...v2.5.0) (2026-11-12)


### :video_game: Features

* **bios:** sync prod.keys and firmware for switch ([#248](https://github.com/kelsin/sync-roms/issues/248)) ([48bed6d](https://github.com/kelsin/sync-roms/commit/48bed6d8005b823b5c95617601ccf8235554bae7))


### :bug: Bug Fixes

* **storage:** find accented names on shares that store them decomposed ([#247](https://github.com/kelsin/sync-roms/issues/247)) ([37a0f06](https://github.com/kelsin/sync-roms/commit/37a0f062a374a2e43db56668090a79dfb4975015))


### :traffic_light: Tests

* **scrape:** fix flaky credentials output check ([#250](https://github.com/kelsin/sync-roms/issues/250)) ([ea4f81b](https://github.com/kelsin/sync-roms/commit/ea4f81b16dbfbb23084ab1b0174d27a5239d43d9))

## [2.4.1](https://github.com/kelsin/sync-roms/compare/v2.4.0...v2.4.1) (2026-11-12)


### :bug: Bug Fixes

* **themeart:** clean up the collection art and drop duplicates ([#245](https://github.com/kelsin/sync-roms/issues/245)) ([05e5b66](https://github.com/kelsin/sync-roms/commit/05e5b66b945fe39eaad7f438adcadc3357151f7f))

## [2.4.0](https://github.com/kelsin/sync-roms/compare/v2.3.0...v2.4.0) (2026-11-12)


### :video_game: Features

* **devices:** recommend psvita on snapdragon 8 gen 2 class handhelds ([#242](https://github.com/kelsin/sync-roms/issues/242)) ([9152c94](https://github.com/kelsin/sync-roms/commit/9152c94a507bbb5078e1f607816e68cf9453e74c))
* **picker:** port list screens to Textual and preview theme art ([#243](https://github.com/kelsin/sync-roms/issues/243)) ([6aa85ab](https://github.com/kelsin/sync-roms/commit/6aa85ab4e00a32662859b9b62b98a4719c4561ec))
* **themeart:** redraw the collection art and add art for every set ([#240](https://github.com/kelsin/sync-roms/issues/240)) ([e7f3de3](https://github.com/kelsin/sync-roms/commit/e7f3de35758f28c99c8d581369ca15b736c7a574))


### :traffic_light: Tests

* **scrape:** make the quota test deterministic ([#244](https://github.com/kelsin/sync-roms/issues/244)) ([6be8841](https://github.com/kelsin/sync-roms/commit/6be88412bbc89f6d49bb2256a4d2dbe4e90d2d02))

## [2.3.0](https://github.com/kelsin/sync-roms/compare/v2.2.0...v2.3.0) (2026-11-12)


### :video_game: Features

* **cache:** make cache update quick by default and add --full ([#237](https://github.com/kelsin/sync-roms/issues/237)) ([7d21ba9](https://github.com/kelsin/sync-roms/commit/7d21ba94b2b30877f0fd0119651857b65abda98c))


### :bug: Bug Fixes

* **inventory:** ignore .DS_Store files in storage listings and the cache ([#239](https://github.com/kelsin/sync-roms/issues/239)) ([2e47ece](https://github.com/kelsin/sync-roms/commit/2e47ece0249f6c8ee9ac29ec4caad81ff2e24209))

## [2.2.0](https://github.com/kelsin/sync-roms/compare/v2.1.0...v2.2.0) (2026-11-12)


### :video_game: Features

* **cache:** add cache update --quick to stat only new files ([#235](https://github.com/kelsin/sync-roms/issues/235)) ([ee5f0fa](https://github.com/kelsin/sync-roms/commit/ee5f0fa9c46f4e7ac8bd8aaa62f721c0dcc395aa))

## [2.1.0](https://github.com/kelsin/sync-roms/compare/v2.0.0...v2.1.0) (2026-11-12)


### :video_game: Features

* **scrape:** list ROMs with no metadata and review unknown ROMs ([#233](https://github.com/kelsin/sync-roms/issues/233)) ([78580de](https://github.com/kelsin/sync-roms/commit/78580decf691574c0439595ad8628d4837517a6c))

## [2.0.0](https://github.com/kelsin/sync-roms/compare/v1.5.0...v2.0.0) (2026-11-12)


### ⚠ BREAKING CHANGES

* **sync:** sync every system with games and preview downloads in the card editor ([#229](https://github.com/kelsin/sync-roms/issues/229))

### :video_game: Features

* **scrape:** ignore non-game ROMs and review non-game results ([#232](https://github.com/kelsin/sync-roms/issues/232)) ([ab3b1c3](https://github.com/kelsin/sync-roms/commit/ab3b1c38fcdc154882131c3e5044754b2f9aa70d))
* **surprise:** choose the systems surprise may use on every card ([#231](https://github.com/kelsin/sync-roms/issues/231)) ([e6b5458](https://github.com/kelsin/sync-roms/commit/e6b54589e5e887a0da107c51393959e5bed2ee94))
* **sync:** sync every system with games and preview downloads in the card editor ([#229](https://github.com/kelsin/sync-roms/issues/229)) ([9273b7d](https://github.com/kelsin/sync-roms/commit/9273b7d0c1b4489eb21c0a1b1775d170b26ee151))

## [1.5.0](https://github.com/kelsin/sync-roms/compare/v1.4.0...v1.5.0) (2026-11-11)


### :video_game: Features

* **cache:** read storage listings from a persistent storage cache ([#228](https://github.com/kelsin/sync-roms/issues/228)) ([e924fee](https://github.com/kelsin/sync-roms/commit/e924feedb70c21b49dcd5968a667176c3f4973df))
* **collections:** filter the add-games list by set and metadata ([#226](https://github.com/kelsin/sync-roms/issues/226)) ([a5c5e88](https://github.com/kelsin/sync-roms/commit/a5c5e880252f00fec1897efa8d9fc40f6b485e3f))

## [1.4.0](https://github.com/kelsin/sync-roms/compare/v1.3.0...v1.4.0) (2026-11-11)


### :video_game: Features

* add custom collections and surprise ([#223](https://github.com/kelsin/sync-roms/issues/223)) ([5a89ee1](https://github.com/kelsin/sync-roms/commit/5a89ee180e7888e0343365e25781756ae1a592f0))
* **chd:** convert ps3 isos to zstd chds and unpack psn archives ([#222](https://github.com/kelsin/sync-roms/issues/222)) ([27e2c5b](https://github.com/kelsin/sync-roms/commit/27e2c5be04f345f491deccae68874637a5f94c14))
* **collections:** let a collection pick Art Book Next theme art ([#225](https://github.com/kelsin/sync-roms/issues/225)) ([00e1736](https://github.com/kelsin/sync-roms/commit/00e17364633160887f8816032125e074a650a20b))
* **edit:** hide systems with no storage folder in the card editor ([#217](https://github.com/kelsin/sync-roms/issues/217)) ([0a176a0](https://github.com/kelsin/sync-roms/commit/0a176a0761b8a66ee43cff0619ba5c2e022d0601))
* **sets:** expand every set and add seventeen new ones ([#221](https://github.com/kelsin/sync-roms/issues/221)) ([53c9e33](https://github.com/kelsin/sync-roms/commit/53c9e332f237ee61d5fd76e623be162e34f39652))
* **surprise:** add Art Book Next art for the Surprise collection ([#224](https://github.com/kelsin/sync-roms/issues/224)) ([1db9166](https://github.com/kelsin/sync-roms/commit/1db91668737fba9ae603c4c5808281603468c1a5))
* **sync:** copy a system's rom_files from BIOS/ into its ROM folder ([#220](https://github.com/kelsin/sync-roms/issues/220)) ([9eace0b](https://github.com/kelsin/sync-roms/commit/9eace0b7fb946dd238e2e6e865d4cd30d96609e3))


### :bug: Bug Fixes

* **sync:** keep repo data readable when an upgrade removes the install mid-run ([#218](https://github.com/kelsin/sync-roms/issues/218)) ([8354541](https://github.com/kelsin/sync-roms/commit/83545411ecb26e1f1ac220dcc506844041915519))

## [1.3.0](https://github.com/kelsin/sync-roms/compare/v1.2.0...v1.3.0) (2026-11-11)


### :video_game: Features

* **edit:** show emoji for empty and fully synced sets in the set picker ([#215](https://github.com/kelsin/sync-roms/issues/215)) ([1dd222b](https://github.com/kelsin/sync-roms/commit/1dd222b62a92b90ef8817ada5b784df095c43866))

## [1.2.0](https://github.com/kelsin/sync-roms/compare/v1.1.0...v1.2.0) (2026-11-11)


### :video_game: Features

* **edit:** hide systems with an empty folder in the card editor ([#208](https://github.com/kelsin/sync-roms/issues/208)) ([c9f02f2](https://github.com/kelsin/sync-roms/commit/c9f02f25e278c294edd466d45212c4d57db4b9a4))
* **edit:** show synced/total games per set in the set picker ([#210](https://github.com/kelsin/sync-roms/issues/210)) ([8b1bce0](https://github.com/kelsin/sync-roms/commit/8b1bce0e5dcb9066c133d6cb98f53120f510c292))
* **edit:** sort metadata filter values alphabetically ([#212](https://github.com/kelsin/sync-roms/issues/212)) ([2f5d472](https://github.com/kelsin/sync-roms/commit/2f5d47281306d2e7d4fa1f994efd4f332a514526))
* **edit:** start the metadata value picker on the current selection ([#214](https://github.com/kelsin/sync-roms/issues/214)) ([0fd4f10](https://github.com/kelsin/sync-roms/commit/0fd4f1034004c904f24d8e36d05fe6139d44f4ff))
* **edit:** start the set picker on the set the list is filtered to ([#211](https://github.com/kelsin/sync-roms/issues/211)) ([7f4e275](https://github.com/kelsin/sync-roms/commit/7f4e275b365dc81d2dcae622ebcc21e1e9155414))
* **edit:** toggle a set's games on one system with space/tab ([#213](https://github.com/kelsin/sync-roms/issues/213)) ([a68fa81](https://github.com/kelsin/sync-roms/commit/a68fa8106652ae9308b2946925715b14d49b8922))

## [1.1.0](https://github.com/kelsin/sync-roms/compare/v1.0.0...v1.1.0) (2026-11-11)


### :video_game: Features

* **edit:** add D hotkey to clear all picks from a card ([#203](https://github.com/kelsin/sync-roms/issues/203)) ([e275392](https://github.com/kelsin/sync-roms/commit/e27539236a7eec77816d201e14aad8d1c91e3b49))
* **edit:** show all keybindings in a popup on ? ([#205](https://github.com/kelsin/sync-roms/issues/205)) ([527783c](https://github.com/kelsin/sync-roms/commit/527783c4b3d5e503ae67ea50e3dccb1b8113287d))
* **edit:** sort systems by company then name in the editors ([#207](https://github.com/kelsin/sync-roms/issues/207)) ([13065b4](https://github.com/kelsin/sync-roms/commit/13065b429e58a1da814e4ba73cb706f96cb2a904))


### :bug: Bug Fixes

* **edit:** exit without waiting for background size refreshes ([#206](https://github.com/kelsin/sync-roms/issues/206)) ([d28aaf3](https://github.com/kelsin/sync-roms/commit/d28aaf355a34b484a09545062904b42f84ce498c))
* **edit:** toggle full system and set references in place without redrawing the screen ([#202](https://github.com/kelsin/sync-roms/issues/202)) ([dd318ce](https://github.com/kelsin/sync-roms/commit/dd318ce7f909f89f0d801392970b1f79fd1ffc79))

## [1.0.0](https://github.com/kelsin/sync-roms/compare/v0.48.0...v1.0.0) (2026-11-11)


### ⚠ BREAKING CHANGES

* **edit:** system-first card editor with space budget, filters and recommended systems ([#200](https://github.com/kelsin/sync-roms/issues/200))

### :video_game: Features

* **edit:** system-first card editor with space budget, filters and recommended systems ([#200](https://github.com/kelsin/sync-roms/issues/200)) ([14f10be](https://github.com/kelsin/sync-roms/commit/14f10be7b9e45e0ea1567136e6ccecf399511ea0))

## [0.48.0](https://github.com/kelsin/sync-roms/compare/v0.47.1...v0.48.0) (2026-11-10)


### :video_game: Features

* **devices:** add screen aspect ratio to every device ([#198](https://github.com/kelsin/sync-roms/issues/198)) ([1bcb54b](https://github.com/kelsin/sync-roms/commit/1bcb54bad4861f6d339619672eff91a2aa686eb7))
* **sets:** add picks from Atari, MSX, Sega CD, NEC, SNK, Bandai and modern consoles ([#196](https://github.com/kelsin/sync-roms/issues/196)) ([868aa75](https://github.com/kelsin/sync-roms/commit/868aa75b797e71d9dac88364c39382781fa4c3df))
* **vita:** create .psvita title id files for Vita zips on sync ([#199](https://github.com/kelsin/sync-roms/issues/199)) ([8cd0318](https://github.com/kelsin/sync-roms/commit/8cd0318dbaa5cde4d1ff2764817ca446cbc9dd51))

## [0.47.1](https://github.com/kelsin/sync-roms/compare/v0.47.0...v0.47.1) (2026-11-10)


### :bug: Bug Fixes

* **bios:** audit bios lists against libretro, batocera and es-de ([#194](https://github.com/kelsin/sync-roms/issues/194)) ([88d7b80](https://github.com/kelsin/sync-roms/commit/88d7b805ef3c88e277f6d6c6bf337b577ab1aa92))

## [0.47.0](https://github.com/kelsin/sync-roms/compare/v0.46.3...v0.47.0) (2026-11-10)


### :video_game: Features

* **cards:** save a readable card size and show it in cards list ([#192](https://github.com/kelsin/sync-roms/issues/192)) ([c718593](https://github.com/kelsin/sync-roms/commit/c7185931dcbf432bda07a7168dc24f3b3d55d85b))

## [0.46.3](https://github.com/kelsin/sync-roms/compare/v0.46.2...v0.46.3) (2026-11-10)


### :bug: Bug Fixes

* **test:** count real hash reads so the prefetch test isn't racy ([#191](https://github.com/kelsin/sync-roms/issues/191)) ([04e6e36](https://github.com/kelsin/sync-roms/commit/04e6e3640f7c97c0c1988290e2f87f1abee549b9))


### :zap: Performance Improvements

* cut redundant I/O and hashing, dedupe helpers, make tests hermetic ([#190](https://github.com/kelsin/sync-roms/issues/190)) ([736aef0](https://github.com/kelsin/sync-roms/commit/736aef0d57deba216eafdade3c9066caf4435801))
* **scrape:** hash ahead of lookups, batch hash writes, list in parallel ([#188](https://github.com/kelsin/sync-roms/issues/188)) ([665066c](https://github.com/kelsin/sync-roms/commit/665066c901e94b180e38628895b0b32194f4b8aa))

## [0.46.2](https://github.com/kelsin/sync-roms/compare/v0.46.1...v0.46.2) (2026-11-10)


### :bug: Bug Fixes

* **data:** add screenscraper ids for arduboy, sufami, arcadia and gamate ([#187](https://github.com/kelsin/sync-roms/issues/187)) ([a95ff55](https://github.com/kelsin/sync-roms/commit/a95ff55fb2d4ee25504e08a1b6caf50e3e67d6a0))


### :broom: Chores

* **release:** include perf and chore sections in changelog ([#185](https://github.com/kelsin/sync-roms/issues/185)) ([5f375d8](https://github.com/kelsin/sync-roms/commit/5f375d8a9415f24842e026397d81df5530d08409))

## [0.46.1](https://github.com/kelsin/sync-roms/compare/v0.46.0...v0.46.1) (2026-11-10)


### Code Refactoring

* **sync:** read android apks from os/android/APKs/ ([#182](https://github.com/kelsin/sync-roms/issues/182)) ([7292dfe](https://github.com/kelsin/sync-roms/commit/7292dfe4e9c80947cbf2b891c81a719149cd7cd3))

## [0.46.0](https://github.com/kelsin/sync-roms/compare/v0.45.0...v0.46.0) (2026-11-10)


### Features

* **scrape:** add --fill-media to scrape missing media for ROMs with metadata ([#177](https://github.com/kelsin/sync-roms/issues/177)) ([88c55df](https://github.com/kelsin/sync-roms/commit/88c55df55ad887249b3325f6d7bcf7b99d83c93b))
* **systems:** add sg-1000, msx, msx2, c64, arcadia, gamate and game.com ([#179](https://github.com/kelsin/sync-roms/issues/179)) ([912df14](https://github.com/kelsin/sync-roms/commit/912df1432f3fe96225d45a3da61bf736c72c7182))


### Bug Fixes

* **devices:** move retroid pocket 2s and 4 pro up a tier ([#181](https://github.com/kelsin/sync-roms/issues/181)) ([1677816](https://github.com/kelsin/sync-roms/commit/167781678d1223d76fe79cebf8d8025f7bf4793e))
* **systems:** add ScreenScraper id for SuperGrafx ([#176](https://github.com/kelsin/sync-roms/issues/176)) ([50b129c](https://github.com/kelsin/sync-roms/commit/50b129ca9cc03a29a43627a43fdd3c450419a39d))


### Code Refactoring

* **devices:** define device systems as a chain of tiers ([#180](https://github.com/kelsin/sync-roms/issues/180)) ([4e98104](https://github.com/kelsin/sync-roms/commit/4e981049b91ee8dd83b0d46e6c02e3d88e2e04db))

## [0.45.0](https://github.com/kelsin/sync-roms/compare/v0.44.0...v0.45.0) (2026-11-10)


### Features

* **scrape:** add --all to scrape every ROM in the storage ([#172](https://github.com/kelsin/sync-roms/issues/172)) ([2eceac5](https://github.com/kelsin/sync-roms/commit/2eceac532d17f50cc86ddd15709b5370c9831560))

## [0.44.0](https://github.com/kelsin/sync-roms/compare/v0.43.1...v0.44.0) (2026-11-10)


### Features

* **sets:** add invader (gba) to shmups ([#169](https://github.com/kelsin/sync-roms/issues/169)) ([01402ed](https://github.com/kelsin/sync-roms/commit/01402edaaab7f6e5dd8d26fbae4d701fa09d4267))

## [0.43.1](https://github.com/kelsin/sync-roms/compare/v0.43.0...v0.43.1) (2026-11-09)


### Bug Fixes

* **convert:** run iso2zar with a terminal so it stays in cli mode ([#167](https://github.com/kelsin/sync-roms/issues/167)) ([762a6fe](https://github.com/kelsin/sync-roms/commit/762a6fe0d9e6a60feebccf8681216b2934f58e20))

## [0.43.0](https://github.com/kelsin/sync-roms/compare/v0.42.0...v0.43.0) (2026-11-09)


### Features

* **convert:** compress xbox 360 isos to zar with iso2zar ([#164](https://github.com/kelsin/sync-roms/issues/164)) ([9e634d5](https://github.com/kelsin/sync-roms/commit/9e634d5039aaa4b583d3bd680ab9922905a89056))

## [0.42.0](https://github.com/kelsin/sync-roms/compare/v0.41.0...v0.42.0) (2026-11-09)


### Features

* **devices:** add magicx zero 40 ([#162](https://github.com/kelsin/sync-roms/issues/162)) ([021212b](https://github.com/kelsin/sync-roms/commit/021212b8b0271b15958db4d3b5e122874a5d1db6))

## [0.41.0](https://github.com/kelsin/sync-roms/compare/v0.40.2...v0.41.0) (2026-11-09)


### Features

* **sets:** add publisher categories to shmups ([#160](https://github.com/kelsin/sync-roms/issues/160)) ([66e8a6a](https://github.com/kelsin/sync-roms/commit/66e8a6a59254361a8332ba944db5d896ecc3badf))

## [0.40.2](https://github.com/kelsin/sync-roms/compare/v0.40.1...v0.40.2) (2026-11-09)


### Bug Fixes

* **release:** include refactors in releases ([#158](https://github.com/kelsin/sync-roms/issues/158)) ([fba33dc](https://github.com/kelsin/sync-roms/commit/fba33dcf1380f192b0a8a3574ea45254a1c65c04))


### Code Refactoring

* **sets:** drop arcade-1g1r and repoint sets at 1g1r fbneo/mame ([#156](https://github.com/kelsin/sync-roms/issues/156)) ([4c993d5](https://github.com/kelsin/sync-roms/commit/4c993d59502e1e71224b34e65c2b45cb8c7cef1c))

## [0.40.1](https://github.com/kelsin/sync-roms/compare/v0.40.0...v0.40.1) (2026-11-09)


### Bug Fixes

* **clean:** stop Spotlight before dot_clean and retry it ([#153](https://github.com/kelsin/sync-roms/issues/153)) ([e0ecce5](https://github.com/kelsin/sync-roms/commit/e0ecce57417e2b4960f494dcac5410fb71b4aed1))

## [0.40.0](https://github.com/kelsin/sync-roms/compare/v0.39.0...v0.40.0) (2026-11-09)


### Features

* **sync:** remove empty Onion and Allium systems and their folders ([#151](https://github.com/kelsin/sync-roms/issues/151)) ([e2d30cc](https://github.com/kelsin/sync-roms/commit/e2d30cc4140e9958747388bbec23f7c872256d1f))

## [0.39.0](https://github.com/kelsin/sync-roms/compare/v0.38.1...v0.39.0) (2026-11-09)


### Features

* **scrape:** remove the other Onion-family gamelist once the layout's own exists ([#150](https://github.com/kelsin/sync-roms/issues/150)) ([ac30d79](https://github.com/kelsin/sync-roms/commit/ac30d795b505d4384cb37c229028d4087522484b))


### Bug Fixes

* **cli:** size table columns to their content ([#148](https://github.com/kelsin/sync-roms/issues/148)) ([508b100](https://github.com/kelsin/sync-roms/commit/508b10026e24ba6ed7243829130f897c88d9e3c1))

## [0.38.1](https://github.com/kelsin/sync-roms/compare/v0.38.0...v0.38.1) (2026-11-09)


### Bug Fixes

* **sync:** clean up ROMs of systems the device no longer lists ([#146](https://github.com/kelsin/sync-roms/issues/146)) ([d21e909](https://github.com/kelsin/sync-roms/commit/d21e909db10eb12293e3292c0dbfd28f9c434b63))

## [0.38.0](https://github.com/kelsin/sync-roms/compare/v0.37.0...v0.38.0) (2026-11-09)


### Features

* **onion:** install bucket themes onto the card ([#145](https://github.com/kelsin/sync-roms/issues/145)) ([eb4f8fe](https://github.com/kelsin/sync-roms/commit/eb4f8fea570b9c0606cca056af006a48d2a1408e))
* **sets:** add arcade 1g1r set ([#144](https://github.com/kelsin/sync-roms/issues/144)) ([4180f66](https://github.com/kelsin/sync-roms/commit/4180f663a0e667ed6562392859af4ef1e1b28604))


### Bug Fixes

* **devices:** remove arcade systems from miyoo mini flip ([#141](https://github.com/kelsin/sync-roms/issues/141)) ([78dd1c6](https://github.com/kelsin/sync-roms/commit/78dd1c6ac53def5c75646d4f2a0b9e15e3b45658))
* **sync:** tolerate already-missing files when deleting extras ([#143](https://github.com/kelsin/sync-roms/issues/143)) ([888d244](https://github.com/kelsin/sync-roms/commit/888d2444225fe4c46d2a8f5e2556f2f279950557))

## [0.37.0](https://github.com/kelsin/sync-roms/compare/v0.36.0...v0.37.0) (2026-11-08)


### Features

* **sets:** add radiant silvergun to shmups ([#140](https://github.com/kelsin/sync-roms/issues/140)) ([d91a403](https://github.com/kelsin/sync-roms/commit/d91a403101e42e269fe07438d1f1e4c33fa9b36c))
* **skills:** add build-card skill ([#138](https://github.com/kelsin/sync-roms/issues/138)) ([1e0f86e](https://github.com/kelsin/sync-roms/commit/1e0f86ea45ebdc26c46ae4b1b490e5b055bad19c))

## [0.36.0](https://github.com/kelsin/sync-roms/compare/v0.35.0...v0.36.0) (2026-11-08)


### Features

* **cli:** add edit and cards edit as aliases for games edit ([#136](https://github.com/kelsin/sync-roms/issues/136)) ([e223594](https://github.com/kelsin/sync-roms/commit/e2235948d91417616fa1c41abd66a5d2b9f46f5c))

## [0.35.0](https://github.com/kelsin/sync-roms/compare/v0.34.0...v0.35.0) (2026-11-08)


### Features

* **picker:** vim-style modal lists with emacs line editing ([#135](https://github.com/kelsin/sync-roms/issues/135)) ([2234242](https://github.com/kelsin/sync-roms/commit/22342424baad5339c7ff9f5b95885ce95463b3a1))


### Bug Fixes

* **tests:** keep the sync smoke test out of the real data folder ([#133](https://github.com/kelsin/sync-roms/issues/133)) ([d8750b0](https://github.com/kelsin/sync-roms/commit/d8750b0d733438ab3a577427fd031b7a10e337d1))

## [0.34.0](https://github.com/kelsin/sync-roms/compare/v0.33.0...v0.34.0) (2026-11-08)


### Features

* **sync:** copy the bucket's APKs folder to Android cards ([#130](https://github.com/kelsin/sync-roms/issues/130)) ([5584572](https://github.com/kelsin/sync-roms/commit/5584572b7c27b1e1a8210972d49a130cfa6ee683))


### Bug Fixes

* **sets:** prefer fbneo over mame and drop duplicate ports ([#132](https://github.com/kelsin/sync-roms/issues/132)) ([6a6f869](https://github.com/kelsin/sync-roms/commit/6a6f86944a5b4652c94da78ba402a649277295b0))

## [0.33.0](https://github.com/kelsin/sync-roms/compare/v0.32.0...v0.33.0) (2026-11-08)


### Features

* **sets:** update 9 sets ([#128](https://github.com/kelsin/sync-roms/issues/128)) ([6dbbd1d](https://github.com/kelsin/sync-roms/commit/6dbbd1d44e46ce94ffe541e0a666a7a6ef5693ad))

## [0.32.0](https://github.com/kelsin/sync-roms/compare/v0.31.0...v0.32.0) (2026-11-08)


### Features

* **scrape:** scrape missing roms from screenscraper into the bucket ([#105](https://github.com/kelsin/sync-roms/issues/105)) ([73181f8](https://github.com/kelsin/sync-roms/commit/73181f80c0bf433f2835185b48ddeb4cd52639a3))
* **sync:** give Allium its own layout with a full gamelist.xml ([#127](https://github.com/kelsin/sync-roms/issues/127)) ([2f33ff4](https://github.com/kelsin/sync-roms/commit/2f33ff4ce72c71659ca4be542ba51e28d0eb926c))

## [0.31.0](https://github.com/kelsin/sync-roms/compare/v0.30.0...v0.31.0) (2026-11-08)


### Features

* **sets:** add sets edit command that opens a PR with set changes ([#123](https://github.com/kelsin/sync-roms/issues/123)) ([7ae6cff](https://github.com/kelsin/sync-roms/commit/7ae6cffbf35cfb8a198542c0bd77b6bb383a5ea5))
* **sets:** merge shmup sets into one with categories ([#121](https://github.com/kelsin/sync-roms/issues/121)) ([4edfcba](https://github.com/kelsin/sync-roms/commit/4edfcbab50bcd6b6530fbf499ac83a10bfdd500e))
* **sync:** install BIOS for every system with ROMs on the card ([#125](https://github.com/kelsin/sync-roms/issues/125)) ([17fffc0](https://github.com/kelsin/sync-roms/commit/17fffc001a128d9d02aeed698e754afe778a1b90))
* **sync:** selected-only systems view and per-card game exclusions ([#122](https://github.com/kelsin/sync-roms/issues/122)) ([dd38f2d](https://github.com/kelsin/sync-roms/commit/dd38f2dc061542aedd69de48d3e80d0588c82cdf))


### Bug Fixes

* **cards:** warn when a saved card setup is ignored ([#120](https://github.com/kelsin/sync-roms/issues/120)) ([6d36274](https://github.com/kelsin/sync-roms/commit/6d362749393c2e0cd64a9dc0378d2ef49e83831d))
* **sets:** make mame and fbneo entries 1g1r, preferring US over Japan ([#118](https://github.com/kelsin/sync-roms/issues/118)) ([2040e8c](https://github.com/kelsin/sync-roms/commit/2040e8cca79e19dc1afdd493a0117d7fca3501d0))
* **sync:** name MAME and FBNeo clones in the Onion/Allium gamelist ([#124](https://github.com/kelsin/sync-roms/issues/124)) ([c2a2385](https://github.com/kelsin/sync-roms/commit/c2a23857514955eeee0873466f59ad4685c7a904))

## [0.30.0](https://github.com/kelsin/sync-roms/compare/v0.29.1...v0.30.0) (2026-11-07)


### Features

* **emudeck:** install scraped media ([#116](https://github.com/kelsin/sync-roms/issues/116)) ([eeb7d71](https://github.com/kelsin/sync-roms/commit/eeb7d71761a4fdce2d6fbb592b70c7885644034a))
* **scrape:** name mame and fbneo clones after their variant ([#117](https://github.com/kelsin/sync-roms/issues/117)) ([c01c811](https://github.com/kelsin/sync-roms/commit/c01c811d36e631b6752efd0816acb902a1a741a8))
* **sync:** delete unselected roms before checking free space ([#114](https://github.com/kelsin/sync-roms/issues/114)) ([acd47df](https://github.com/kelsin/sync-roms/commit/acd47df06de844c98082ca648b380233853a0fb1))

## [0.29.1](https://github.com/kelsin/sync-roms/compare/v0.29.0...v0.29.1) (2026-11-07)


### Bug Fixes

* **ui:** keep the download line within the terminal width ([#112](https://github.com/kelsin/sync-roms/issues/112)) ([e788e1b](https://github.com/kelsin/sync-roms/commit/e788e1bbdc5e0a874730ae4ac2aef86600f8131f))

## [0.29.0](https://github.com/kelsin/sync-roms/compare/v0.28.0...v0.29.0) (2026-11-07)


### Features

* **ui:** show network versus disk speed while downloading ([#110](https://github.com/kelsin/sync-roms/issues/110)) ([71e8153](https://github.com/kelsin/sync-roms/commit/71e81531fb5d42252b7ae8d50fd1fd7b944f7236))
* **ui:** show system sizes in the picker and current transfer speed ([#109](https://github.com/kelsin/sync-roms/issues/109)) ([708e3f6](https://github.com/kelsin/sync-roms/commit/708e3f6dcb7cec783782887f43bb33deb86ad250))

## [0.28.0](https://github.com/kelsin/sync-roms/compare/v0.27.0...v0.28.0) (2026-11-07)


### Features

* **onion:** keep multi-disc discs in a hidden .multi-disc folder ([#106](https://github.com/kelsin/sync-roms/issues/106)) ([1447201](https://github.com/kelsin/sync-roms/commit/1447201bc42a995e3821953ade771ce744b1bcde))
* **onion:** sync fbneo to Onion's FBNEO folder on the mini flip ([#108](https://github.com/kelsin/sync-roms/issues/108)) ([819cdb9](https://github.com/kelsin/sync-roms/commit/819cdb94a9126329c836ec8a3c92dfab68b4ef69))

## [0.27.0](https://github.com/kelsin/sync-roms/compare/v0.26.0...v0.27.0) (2026-11-07)


### Features

* **sets:** add cave, psikyo and touhou shmup sets ([#102](https://github.com/kelsin/sync-roms/issues/102)) ([3e2455b](https://github.com/kelsin/sync-roms/commit/3e2455b3cbb5c07dd44bd28e78f61b34d54656aa))
* **sets:** add spriggan mark 2 to shmups set ([#104](https://github.com/kelsin/sync-roms/issues/104)) ([40a478a](https://github.com/kelsin/sync-roms/commit/40a478a71a738643bde1d3168fb3b0986c0f2b02))

## [0.26.0](https://github.com/kelsin/sync-roms/compare/v0.25.1...v0.26.0) (2026-11-06)


### Features

* **chd:** use zlib for ps2 chds and recompress other codecs ([#98](https://github.com/kelsin/sync-roms/issues/98)) ([4d686cb](https://github.com/kelsin/sync-roms/commit/4d686cb11df509ba2f74031b89529c93d5a800aa))
* support a folder (e.g. a network share) instead of an S3 bucket ([#100](https://github.com/kelsin/sync-roms/issues/100)) ([01d6699](https://github.com/kelsin/sync-roms/commit/01d669955bd3e864fec2c80d8f439358e5d17e53))
* **systems:** add NEC PC-98 with np2kai bios and zip extraction ([#101](https://github.com/kelsin/sync-roms/issues/101)) ([4d0e535](https://github.com/kelsin/sync-roms/commit/4d0e535d316dd6eedfe6e6db2c8bef1a4a103ec7))

## [0.25.1](https://github.com/kelsin/sync-roms/compare/v0.25.0...v0.25.1) (2026-11-01)


### Bug Fixes

* **scrape:** skip empty placeholder art when making Onion and Slot images ([#96](https://github.com/kelsin/sync-roms/issues/96)) ([057447d](https://github.com/kelsin/sync-roms/commit/057447d6d473657501744219779039117ee2191f))

## [0.25.0](https://github.com/kelsin/sync-roms/compare/v0.24.0...v0.25.0) (2026-11-01)


### Features

* **layouts:** support Allium through the Onion layout ([#93](https://github.com/kelsin/sync-roms/issues/93)) ([e7edfd0](https://github.com/kelsin/sync-roms/commit/e7edfd0837c032dc5ca0e727d0606b85584a771f))


### Bug Fixes

* **onion:** ignore .db cache files in rom folders ([#92](https://github.com/kelsin/sync-roms/issues/92)) ([d2304a2](https://github.com/kelsin/sync-roms/commit/d2304a2e953612ffa743bd0b155cbfe7a090206b))
* **sync:** remove ROMs of systems with no games listed and re-add fds ([#95](https://github.com/kelsin/sync-roms/issues/95)) ([9a30bc0](https://github.com/kelsin/sync-roms/commit/9a30bc0247b87344293b0055d1a0c34e1bf03373))

## [0.24.0](https://github.com/kelsin/sync-roms/compare/v0.23.0...v0.24.0) (2026-11-01)


### Features

* **cli:** add subcommands, scripting flags and safer edit and sync flows ([#91](https://github.com/kelsin/sync-roms/issues/91)) ([8f2ecc5](https://github.com/kelsin/sync-roms/commit/8f2ecc552451ed5941949eaae2e09f9a505aeba5))
* **sets:** add iridion games to shmups set ([#89](https://github.com/kelsin/sync-roms/issues/89)) ([e7af6b1](https://github.com/kelsin/sync-roms/commit/e7af6b153fa988c531bfb6b6bd738fa73de0912c))

## [0.23.0](https://github.com/kelsin/sync-roms/compare/v0.22.0...v0.23.0) (2026-11-01)


### Features

* **sets:** use fbneo for CAVE games in shmups set ([#87](https://github.com/kelsin/sync-roms/issues/87)) ([35092b7](https://github.com/kelsin/sync-roms/commit/35092b73660f1aa49ccc293a447c8b3bf29231f9))

## [0.22.0](https://github.com/kelsin/sync-roms/compare/v0.21.0...v0.22.0) (2026-11-01)


### Features

* **sets:** add dreamcast and xbox games to sets ([#86](https://github.com/kelsin/sync-roms/issues/86)) ([34f06b1](https://github.com/kelsin/sync-roms/commit/34f06b18f2901f05546c8eb21d2b6a00b5098e99))
* **sets:** add pinball set ([#84](https://github.com/kelsin/sync-roms/issues/84)) ([bf182b2](https://github.com/kelsin/sync-roms/commit/bf182b23b4c13ae06dc2465528fdc79d88228b32))


### Bug Fixes

* **edit:** keep the last letter of card names in the edit menu ([#83](https://github.com/kelsin/sync-roms/issues/83)) ([c58e278](https://github.com/kelsin/sync-roms/commit/c58e278ee1354a639d3a5ffef292be3321632da2))

## [0.21.0](https://github.com/kelsin/sync-roms/compare/v0.20.1...v0.21.0) (2026-11-01)


### Features

* **sync:** edit a card's games from the sync picker ([#81](https://github.com/kelsin/sync-roms/issues/81)) ([1124c46](https://github.com/kelsin/sync-roms/commit/1124c463199c7b1879ca95f06065f570b5a1c39f))

## [0.20.1](https://github.com/kelsin/sync-roms/compare/v0.20.0...v0.20.1) (2026-11-01)


### Bug Fixes

* **cd:** skip m3u playlists for xbox 360 ([#79](https://github.com/kelsin/sync-roms/issues/79)) ([b4e7e89](https://github.com/kelsin/sync-roms/commit/b4e7e89f3e45bedabc84259e969d2e3e5c93a1d0))

## [0.20.0](https://github.com/kelsin/sync-roms/compare/v0.19.1...v0.20.0) (2026-11-01)


### Features

* **devices:** add windows pc (retrobat) on the es-de layout ([#77](https://github.com/kelsin/sync-roms/issues/77)) ([2defd30](https://github.com/kelsin/sync-roms/commit/2defd301988e8cd05e6ba5557dcd9e154ee96f45))

## [0.19.1](https://github.com/kelsin/sync-roms/compare/v0.19.0...v0.19.1) (2026-11-01)


### Bug Fixes

* **cd:** extract xbox 360 isos without converting to xiso ([#75](https://github.com/kelsin/sync-roms/issues/75)) ([9f04731](https://github.com/kelsin/sync-roms/commit/9f04731d95a24a351072cf746257c2c31e252d34))

## [0.19.0](https://github.com/kelsin/sync-roms/compare/v0.18.0...v0.19.0) (2026-11-01)


### Features

* **cd:** convert xbox 360 isos to xiso ([#74](https://github.com/kelsin/sync-roms/issues/74)) ([708aa33](https://github.com/kelsin/sync-roms/commit/708aa3384524c5e6cdad10ae5460fc3417f65c27))


### Bug Fixes

* **cd:** write the rewritten xiso into the work folder ([#72](https://github.com/kelsin/sync-roms/issues/72)) ([8beddef](https://github.com/kelsin/sync-roms/commit/8beddefaade0836e478c33c1a4d55bb0b622eb0e))

## [0.18.0](https://github.com/kelsin/sync-roms/compare/v0.17.0...v0.18.0) (2026-10-31)


### Features

* **cd:** add --cd with xiso conversion for xbox isos ([#71](https://github.com/kelsin/sync-roms/issues/71)) ([ebbd129](https://github.com/kelsin/sync-roms/commit/ebbd1294cd57cb9c7997430c686e0d40b08c3008))
* **sets:** add ps2 and wii games to sets and add 3d platformers set ([#70](https://github.com/kelsin/sync-roms/issues/70)) ([e187212](https://github.com/kelsin/sync-roms/commit/e18721223f98496197bc179052a4364d7cfa3bb5))
* **sets:** add psx and neogeocd games to existing sets ([#68](https://github.com/kelsin/sync-roms/issues/68)) ([d63d0f8](https://github.com/kelsin/sync-roms/commit/d63d0f8ddeed48a545a4b8ea8957eac1a45b167a))
* **sets:** add psx games to sets and add survival horror and racing sets ([#64](https://github.com/kelsin/sync-roms/issues/64)) ([61f0a7e](https://github.com/kelsin/sync-roms/commit/61f0a7e63ad59516300b669a3c4c75d6d52d95b4))


### Bug Fixes

* **m3u:** generate playlists for rvz discs and after --chd on extract systems ([#66](https://github.com/kelsin/sync-roms/issues/66)) ([b4b2656](https://github.com/kelsin/sync-roms/commit/b4b26568275c5a2ea321e41732ecc64b125dec16))
* **sets:** link multi-disc games to their m3u playlists ([#67](https://github.com/kelsin/sync-roms/issues/67)) ([d00ad05](https://github.com/kelsin/sync-roms/commit/d00ad0503cd6d66cf8c9eb3984163484f56dff53))
* **sets:** point arcade set entries at the fbneo bucket folder ([#69](https://github.com/kelsin/sync-roms/issues/69)) ([dd83ed5](https://github.com/kelsin/sync-roms/commit/dd83ed58940c445d3608a1162f0edb6ac38b0f4c))

## [0.17.0](https://github.com/kelsin/sync-roms/compare/v0.16.1...v0.17.0) (2026-10-31)


### Features

* **sets:** add english-patched psp games to jrpg essentials and hidden gems ([#62](https://github.com/kelsin/sync-roms/issues/62)) ([2baa524](https://github.com/kelsin/sync-roms/commit/2baa5249e7bfe0e2e66699b7169b3fbd6f3da062))
* **sets:** add resident evil and star wars sets and fill in gc games ([#63](https://github.com/kelsin/sync-roms/issues/63)) ([0c1907f](https://github.com/kelsin/sync-roms/commit/0c1907fcfd93593145d0b58c717bc091d2c099f4))


### Bug Fixes

* **sets:** relink psp games to chd files and add more psp titles ([#60](https://github.com/kelsin/sync-roms/issues/60)) ([550d7ef](https://github.com/kelsin/sync-roms/commit/550d7ef03311babd7d6ea2bd34bf18dd3cab9ca5))

## [0.16.1](https://github.com/kelsin/sync-roms/compare/v0.16.0...v0.16.1) (2026-10-31)


### Bug Fixes

* **upload:** cap concurrency and warm up TLS to avoid OpenSSL segfault ([#58](https://github.com/kelsin/sync-roms/issues/58)) ([16b03cc](https://github.com/kelsin/sync-roms/commit/16b03cce9ea6e4e128dbff02d6e3647575a4719e))

## [0.16.0](https://github.com/kelsin/sync-roms/compare/v0.15.0...v0.16.0) (2026-10-31)


### Features

* **data:** add emudeck layout with steam deck and steam machine ([#56](https://github.com/kelsin/sync-roms/issues/56)) ([21aaefc](https://github.com/kelsin/sync-roms/commit/21aaefccb67a09ba6815a2d7eae6ef117fe37164))

## [0.15.0](https://github.com/kelsin/sync-roms/compare/v0.14.3...v0.15.0) (2026-10-31)


### Features

* **scrapes:** upload Slot labels from a Slot card ([#54](https://github.com/kelsin/sync-roms/issues/54)) ([41a33b3](https://github.com/kelsin/sync-roms/commit/41a33b3972b3e51abffdd86b4426eaa517ce85fe))

## [0.14.3](https://github.com/kelsin/sync-roms/compare/v0.14.2...v0.14.3) (2026-10-31)


### Bug Fixes

* **replace:** show progress while matching files by content ([#51](https://github.com/kelsin/sync-roms/issues/51)) ([3f9f699](https://github.com/kelsin/sync-roms/commit/3f9f6998a29f36f963a71b171998dc86a719d02d))

## [0.14.2](https://github.com/kelsin/sync-roms/compare/v0.14.1...v0.14.2) (2026-10-31)


### Bug Fixes

* **sync:** extract leftover archives and show extraction progress ([#49](https://github.com/kelsin/sync-roms/issues/49)) ([a444a3d](https://github.com/kelsin/sync-roms/commit/a444a3dfe2ee7ebea9540597a65742229aa85dab))

## [0.14.1](https://github.com/kelsin/sync-roms/compare/v0.14.0...v0.14.1) (2026-10-31)


### Bug Fixes

* **mirror:** rename mirror size listing that shadowed local_sizes ([#47](https://github.com/kelsin/sync-roms/issues/47)) ([7786579](https://github.com/kelsin/sync-roms/commit/77865795793732f5f6a6b0a6eece79eef14e3237))

## [0.14.0](https://github.com/kelsin/sync-roms/compare/v0.13.0...v0.14.0) (2026-10-31)


### Features

* **edit:** change a card's device and firmware with ^D ([#44](https://github.com/kelsin/sync-roms/issues/44)) ([6131337](https://github.com/kelsin/sync-roms/commit/6131337a6a6947e3dc9fa083e63483a6aaf163ff))


### Bug Fixes

* **edit:** list only systems a card's firmware supports ([#45](https://github.com/kelsin/sync-roms/issues/45)) ([ea452d2](https://github.com/kelsin/sync-roms/commit/ea452d284e4aefd27b11a5c3e3c7cf09fa9f5ac7))
* **sets:** relink games to current bucket files and add gc, nds and ps2 titles ([#42](https://github.com/kelsin/sync-roms/issues/42)) ([657821e](https://github.com/kelsin/sync-roms/commit/657821e9300ac614003824869cb551ef7a0bafb8))
* **sets:** relink to re-uploaded cartridge files and add more cartridge games ([#46](https://github.com/kelsin/sync-roms/issues/46)) ([392603d](https://github.com/kelsin/sync-roms/commit/392603dd9759a8fb0ea55cd555932b38570a8bb6))

## [0.13.0](https://github.com/kelsin/sync-roms/compare/v0.12.0...v0.13.0) (2026-10-31)


### Features

* **systems:** add SNK Neo Geo Pocket ([#39](https://github.com/kelsin/sync-roms/issues/39)) ([9f95cb5](https://github.com/kelsin/sync-roms/commit/9f95cb5ca5caace636271d35aa33062dd76b4e43))


### Bug Fixes

* **chd:** convert files and archives whose names start with a dot ([#41](https://github.com/kelsin/sync-roms/issues/41)) ([56a9c40](https://github.com/kelsin/sync-roms/commit/56a9c407ede399b79c2a729781494fdf392c56ad))

## [0.12.0](https://github.com/kelsin/sync-roms/compare/v0.11.0...v0.12.0) (2026-10-31)


### Features

* **diff:** compare a local folder with its bucket folder by content, ignoring renames ([#36](https://github.com/kelsin/sync-roms/issues/36)) ([36f7169](https://github.com/kelsin/sync-roms/commit/36f7169a9d512aec3f26d245e394da2d2fd62a60))
* **upload:** add --replace to make a bucket folder match a local one ([#38](https://github.com/kelsin/sync-roms/issues/38)) ([5a6430a](https://github.com/kelsin/sync-roms/commit/5a6430a2d243e38d7979949fd1902a7ab67841a0))

## [0.11.0](https://github.com/kelsin/sync-roms/compare/v0.10.1...v0.11.0) (2026-10-30)


### Features

* **firmware:** add muOS and Slot, picked per device ([#30](https://github.com/kelsin/sync-roms/issues/30)) ([72ec8db](https://github.com/kelsin/sync-roms/commit/72ec8dbab40ffde87539ee235ecffbb9eed33cf0))
* **games:** per-card game lists and full-set references ([#34](https://github.com/kelsin/sync-roms/issues/34)) ([fe8fe85](https://github.com/kelsin/sync-roms/commit/fe8fe85b4e5505a98580443a90d726ab5b008317))
* **scrapes:** clean up stale muOS catalogue art and Slot labels ([#33](https://github.com/kelsin/sync-roms/issues/33)) ([5aa584a](https://github.com/kelsin/sync-roms/commit/5aa584a5e41cbdc1785d23ae7cca171192fcb467))
* **scrapes:** install scraped data for muOS and Slot ([#32](https://github.com/kelsin/sync-roms/issues/32)) ([5bd786a](https://github.com/kelsin/sync-roms/commit/5bd786ac713f9d69999e95e54583a3e50802786d))


### Bug Fixes

* **progress:** label the file count as done and the percent as a share of total size ([#35](https://github.com/kelsin/sync-roms/issues/35)) ([a3410c9](https://github.com/kelsin/sync-roms/commit/a3410c969a61e1ddb7d91fdced00c976da1c3090))

## [0.10.1](https://github.com/kelsin/sync-roms/compare/v0.10.0...v0.10.1) (2026-10-30)


### Bug Fixes

* **upload:** show progress right away by queuing uploads off the main thread ([#28](https://github.com/kelsin/sync-roms/issues/28)) ([90adeac](https://github.com/kelsin/sync-roms/commit/90adeacd3cd40377f98086ad07664b2419a35cfd))

## [0.10.0](https://github.com/kelsin/sync-roms/compare/v0.9.0...v0.10.0) (2026-10-30)


### Features

* **chd:** warn when no folder is named after a chd system ([#23](https://github.com/kelsin/sync-roms/issues/23)) ([e4447e3](https://github.com/kelsin/sync-roms/commit/e4447e3fdfc0760145bd13b2f636891f2a2cbb33))
* **progress:** show the chd progress bar for uploads and downloads ([#27](https://github.com/kelsin/sync-roms/issues/27)) ([e96272e](https://github.com/kelsin/sync-roms/commit/e96272e529cf894cb22e0af10f4daa7620afb6b7))
* **s3:** support a custom s3 endpoint and settings/env overrides ([#26](https://github.com/kelsin/sync-roms/issues/26)) ([7de206d](https://github.com/kelsin/sync-roms/commit/7de206d497faaa3af876114314310215843a2c7b))


### Bug Fixes

* **upload:** skip system files like .DS_Store but keep dot-named roms ([#25](https://github.com/kelsin/sync-roms/issues/25)) ([9c4273c](https://github.com/kelsin/sync-roms/commit/9c4273cd74e1a8da9cfec07bcc4405144abdb676))

## [0.9.0](https://github.com/kelsin/sync-roms/compare/v0.8.0...v0.9.0) (2026-10-29)


### Features

* **upload:** add --upload to send a folder of roms to a system and speed up uploads with a shared transfer pool ([#22](https://github.com/kelsin/sync-roms/issues/22)) ([bfbc4ba](https://github.com/kelsin/sync-roms/commit/bfbc4ba15344ad2811f59d715ab9443aa65f649f))


### Documentation

* **readme:** document aws profile setup and s3 transfer speed settings ([#20](https://github.com/kelsin/sync-roms/issues/20)) ([61e78a2](https://github.com/kelsin/sync-roms/commit/61e78a2b6bdccae144c58c04a22b9b747ef3233d))

## [0.8.0](https://github.com/kelsin/sync-roms/compare/v0.7.0...v0.8.0) (2026-10-29)


### Features

* **chd:** convert in parallel with a progress bar, make interrupts safe and always fix playlists ([#17](https://github.com/kelsin/sync-roms/issues/17)) ([2657147](https://github.com/kelsin/sync-roms/commit/2657147d6a21b293de91bd5a4f0a385a0f33f650))

## [0.7.0](https://github.com/kelsin/sync-roms/compare/v0.6.0...v0.7.0) (2026-10-29)


### Features

* **chd:** add --chd to convert disc archives to verified chd and --install-tools ([#16](https://github.com/kelsin/sync-roms/issues/16)) ([2877599](https://github.com/kelsin/sync-roms/commit/28775990214aca95e9083af0028a0e246be8152f))
* **m3u:** add --m3u to create and fix multi-disc playlists ([#15](https://github.com/kelsin/sync-roms/issues/15)) ([c8ee65f](https://github.com/kelsin/sync-roms/commit/c8ee65f337bf20188ead5eaaa8f569746af02102))
* **sets:** add mame and neogeo games, refresh for 1g1r bucket, drop ngp, sg-1000 and fds ([#13](https://github.com/kelsin/sync-roms/issues/13)) ([ba43ece](https://github.com/kelsin/sync-roms/commit/ba43ece5f388fa40a2049253ce6c5d037048106d))

## [0.6.0](https://github.com/kelsin/sync-roms/compare/v0.5.0...v0.6.0) (2026-10-29)


### Features

* **sets:** add metroid and shmups sets, split run and gun, add ps2 games ([#11](https://github.com/kelsin/sync-roms/issues/11)) ([b8e5043](https://github.com/kelsin/sync-roms/commit/b8e5043c669e2810d773211e6fcfa2150c25ab7c))

## [0.5.0](https://github.com/kelsin/sync-roms/compare/v0.4.0...v0.5.0) (2026-10-29)


### Features

* **sets:** add curated game sets with multi-disc support ([#9](https://github.com/kelsin/sync-roms/issues/9)) ([1950d20](https://github.com/kelsin/sync-roms/commit/1950d200e7440a565f1cabdd055a3d7885c9c6d1))

## [0.4.0](https://github.com/kelsin/sync-roms/compare/v0.3.0...v0.4.0) (2026-10-29)


### Features

* **devices:** add ayaneo android pocket handhelds ([#6](https://github.com/kelsin/sync-roms/issues/6)) ([1860ef7](https://github.com/kelsin/sync-roms/commit/1860ef7ec5b876b660fc4fce9f7d8ca7aa2550ac))
* **edit:** add game sets and keep changes on esc ([#8](https://github.com/kelsin/sync-roms/issues/8)) ([a935bfd](https://github.com/kelsin/sync-roms/commit/a935bfde6a99934090c1d6172680926db53c584b))

## [0.3.0](https://github.com/kelsin/sync-roms/compare/v0.2.2...v0.3.0) (2026-10-28)


### Features

* **edit:** show selected, missing and available counts per system an… ([#4](https://github.com/kelsin/sync-roms/issues/4)) ([ec47bfd](https://github.com/kelsin/sync-roms/commit/ec47bfd6d9b35d174a2252d584e743830d1419a3))

## [0.2.2](https://github.com/kelsin/sync-roms/compare/v0.2.1...v0.2.2) (2026-10-28)


### Bug Fixes

* **release:** find the tap bump pr by branch name ([3561d0c](https://github.com/kelsin/sync-roms/commit/3561d0ce9bf04da54695e3f25d3e6322049c0219))

## [0.2.1](https://github.com/kelsin/sync-roms/compare/v0.2.0...v0.2.1) (2026-10-28)


### Documentation

* add brew tap and trust steps to install ([ff120df](https://github.com/kelsin/sync-roms/commit/ff120df2e15720cf949fa47fd1d0414339a32630))
* document brew install, upgrade and release steps ([98655c2](https://github.com/kelsin/sync-roms/commit/98655c2da4faa34e289d88c2339012827dd0a240))

## [0.2.0](https://github.com/kelsin/sync-roms/compare/v0.1.0...v0.2.0) (2026-10-28)


### Features

* add pyproject with sync-roms console script ([44cdd3a](https://github.com/kelsin/sync-roms/commit/44cdd3a6fe1ad48a3e133fd3407b97996635dbd0))
* **devices:** add anbernic rg35xx sp and document rg sp ([d848f1f](https://github.com/kelsin/sync-roms/commit/d848f1f81ba951720b6c18daadcfa6daa0e040d2))
* **devices:** add retroid, anbernic and ayn handhelds ([54deedf](https://github.com/kelsin/sync-roms/commit/54deedf5aa8bc864d2d76374180578b8b1eb9296))
* **devices:** read device systems from defaults with a personal overlay ([453b7ed](https://github.com/kelsin/sync-roms/commit/453b7ed64dcd682922a54c4692c50a15cfee89c7))


### Bug Fixes

* escape braces in help text overlay example ([a6b644d](https://github.com/kelsin/sync-roms/commit/a6b644d694aab702fa9f0da20bbb6d3490f7bc67))
* point missing-profile error at the aws config files ([67e6458](https://github.com/kelsin/sync-roms/commit/67e6458794b3eed55d7d8f8542e6875e7aad33c4))
* **release:** tag releases without the package name ([8860e30](https://github.com/kelsin/sync-roms/commit/8860e3077eb29c62073e3fe78ee64a96340e56d2))


### Documentation

* document brew and pipx install ([41dd454](https://github.com/kelsin/sync-roms/commit/41dd4540a292af14015cc6eb3d2abd5814dcec5b))
* lead with pipx install until the brew tap exists ([f54ff3f](https://github.com/kelsin/sync-roms/commit/f54ff3f8bc72a374a9f14e78ba4fca0bf4d5cb12))
* note old device-systems.json copies can be deleted ([749eace](https://github.com/kelsin/sync-roms/commit/749eacee0dbf5e8fa19ec3cbfad961b124277e32))
