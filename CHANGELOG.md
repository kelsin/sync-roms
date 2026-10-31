# Changelog

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
