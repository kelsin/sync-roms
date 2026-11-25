# Changelog

## [4.1.0](https://github.com/kelsin/sync-roms/compare/v4.0.0...v4.1.0) (2026-11-25)


### :video_game: Features

* **art:** add professor layton, mortal kombat, tekken, samurai shodown, fatal fury and r-type art ([#610](https://github.com/kelsin/sync-roms/issues/610)) ([2fed996](https://github.com/kelsin/sync-roms/commit/2fed99687c9ab154f60d9f7afe57db62ff6385b1))
* **art:** add shin megami tensei, kingdom hearts, mana, lunar and ace attorney art ([#608](https://github.com/kelsin/sync-roms/issues/608)) ([54152d1](https://github.com/kelsin/sync-roms/commit/54152d1eb1eab65923ff25c479c222d147c544dd))
* **art:** add star fox, contra, ninja gaiden, gradius and metal slug art ([#609](https://github.com/kelsin/sync-roms/issues/609)) ([ee39196](https://github.com/kelsin/sync-roms/commit/ee39196ce2486edbaeaa8ce73b083a273d65624d))
* **collections:** add a shareable collections page and tailscale sharing ([#618](https://github.com/kelsin/sync-roms/issues/618)) ([a53f3fa](https://github.com/kelsin/sync-roms/commit/a53f3fa302248a1efe07b80845dde2d4026fdc62))
* **format:** add format command for SD cards ([#611](https://github.com/kelsin/sync-roms/issues/611)) ([9402cb7](https://github.com/kelsin/sync-roms/commit/9402cb7a241c136db4b671d9ff1530f6c71649f5))
* **knulli:** write settings into knulli.conf ([#613](https://github.com/kelsin/sync-roms/issues/613)) ([cec6c58](https://github.com/kelsin/sync-roms/commit/cec6c58730cf3570bac523df5d77d819b1d93878))
* **portmaster:** add portmaster ports and game data for spruce cards ([#617](https://github.com/kelsin/sync-roms/issues/617)) ([a70a0ad](https://github.com/kelsin/sync-roms/commit/a70a0ad7674f34b42e7925b0d542c4d54d1192df))
* **sync:** bring splore carts from spruce cards into storage ([#607](https://github.com/kelsin/sync-roms/issues/607)) ([f65f43f](https://github.com/kelsin/sync-roms/commit/f65f43f085f79761d28635b2596d3d76da72b0b1))
* **tags:** replace game sets with per-game tags ([#616](https://github.com/kelsin/sync-roms/issues/616)) ([d242eb3](https://github.com/kelsin/sync-roms/commit/d242eb3e35f1424988be114fb0c6187e93690d18))
* **upload:** prepare, scrape after upload, add refresh command ([#615](https://github.com/kelsin/sync-roms/issues/615)) ([08105cc](https://github.com/kelsin/sync-roms/commit/08105ccdf0ee80f52e9776aa1dafecefc5c5e7ea))


### :bug: Bug Fixes

* **art:** draw the horses art without a bridle ([#614](https://github.com/kelsin/sync-roms/issues/614)) ([f19a2ec](https://github.com/kelsin/sync-roms/commit/f19a2ec772581f477209afb28e06bcaae67c320e))

## [4.0.0](https://github.com/kelsin/sync-roms/compare/v3.36.0...v4.0.0) (2026-11-25)


### ⚠ BREAKING CHANGES

* **cli:** one command parser, consistent names and aliases ([#606](https://github.com/kelsin/sync-roms/issues/606))

### :video_game: Features

* **art:** add fire emblem, farming, phantasy star, ys and horses art ([#604](https://github.com/kelsin/sync-roms/issues/604)) ([31c545b](https://github.com/kelsin/sync-roms/commit/31c545b66986e44462983e3c942d74f77f8625de))
* **art:** add king of fighters, capcom vs. and metal gear art ([#603](https://github.com/kelsin/sync-roms/issues/603)) ([0a6162c](https://github.com/kelsin/sync-roms/commit/0a6162c01a385a14556511d6ca87a43d3ac70e60))
* **art:** add wario collection art ([#600](https://github.com/kelsin/sync-roms/issues/600)) ([d503ab4](https://github.com/kelsin/sync-roms/commit/d503ab4a39159e13e66cfec14c2aff56796039d7))
* pick single games from collections on a card ([#602](https://github.com/kelsin/sync-roms/issues/602)) ([30d5e28](https://github.com/kelsin/sync-roms/commit/30d5e289d83b190c595da13d0864a1f8c7768b93))
* set retroarch save state and netplay settings on spruce and android ([#605](https://github.com/kelsin/sync-roms/issues/605)) ([c18aff0](https://github.com/kelsin/sync-roms/commit/c18aff01c2aba70acde771f6e7655ab812dc945e))


### :hammer_and_wrench: Code Refactoring

* **cli:** one command parser, consistent names and aliases ([#606](https://github.com/kelsin/sync-roms/issues/606)) ([39a7709](https://github.com/kelsin/sync-roms/commit/39a77098b688321181153d169743d08afa1a07af))

## [3.36.0](https://github.com/kelsin/sync-roms/compare/v3.35.0...v3.36.0) (2026-11-25)


### :video_game: Features

* **android:** set up syncthing-fork and raofflineproxy in config apply ([#597](https://github.com/kelsin/sync-roms/issues/597)) ([4b5ab65](https://github.com/kelsin/sync-roms/commit/4b5ab651f70c253023c8b1e0f75ebb677b014d25))
* copy android bezels to esde cards ([#594](https://github.com/kelsin/sync-roms/issues/594)) ([a7b8cc6](https://github.com/kelsin/sync-roms/commit/a7b8cc65a36addb28e041f5cbb65a6d7672ddf26))
* **edit:** add a whole set's games from the card editor ([#586](https://github.com/kelsin/sync-roms/issues/586)) ([ba0ee25](https://github.com/kelsin/sync-roms/commit/ba0ee25f595d9c70992bf95ee2285d074f99608d))
* **edit:** show a language flag on game rows ([#591](https://github.com/kelsin/sync-roms/issues/591)) ([007e7ea](https://github.com/kelsin/sync-roms/commit/007e7eaa2cd2c0cca8e40902097610f5ab953be4))
* **edit:** show each card's own collection art in its set and collection lists ([#588](https://github.com/kelsin/sync-roms/issues/588)) ([c6d2cd3](https://github.com/kelsin/sync-roms/commit/c6d2cd3815ee56527c33e9c8a4e709f4225d4fb6))
* **edit:** sort titles without leading articles ([#589](https://github.com/kelsin/sync-roms/issues/589)) ([58f9f6c](https://github.com/kelsin/sync-roms/commit/58f9f6c90f1c1368104fc2e1e70ecdec63a96eac))
* one hotkey scheme for spruce cards and android ([#599](https://github.com/kelsin/sync-roms/issues/599)) ([7c34cee](https://github.com/kelsin/sync-roms/commit/7c34ceea08c0b9b1af36f78aad4ec1f608b5ab18))
* **sync:** add a one-theme mode for spruce cards ([#593](https://github.com/kelsin/sync-roms/issues/593)) ([1c872ca](https://github.com/kelsin/sync-roms/commit/1c872cad1adaa4abc2cd5203b195f2c9279384de))
* **sync:** drop spruceOS sample ROM files without asking ([#590](https://github.com/kelsin/sync-roms/issues/590)) ([03dd58f](https://github.com/kelsin/sync-roms/commit/03dd58f282af9f5c27c2c44b7fa60b1d2dd943e6))
* **sync:** write the RA web api key to spruce cards for cheevos ([#595](https://github.com/kelsin/sync-roms/issues/595)) ([ca8189d](https://github.com/kelsin/sync-roms/commit/ca8189d1b5f49d777ea116f1cf67b8b0b62fd8ae))
* **ui:** draw progress bars as rainbows ([#592](https://github.com/kelsin/sync-roms/issues/592)) ([5a607df](https://github.com/kelsin/sync-roms/commit/5a607dffa714c6c52a2285faaa139e154c68eb5d))


### :bug: Bug Fixes

* **cards:** default the cards install confirm to yes ([#583](https://github.com/kelsin/sync-roms/issues/583)) ([caf5804](https://github.com/kelsin/sync-roms/commit/caf58049374cc11c54c6453037c870c86189df36))
* correct data-loss, storage and CLI defects found in a code review ([#585](https://github.com/kelsin/sync-roms/issues/585)) ([0e1fdd1](https://github.com/kelsin/sync-roms/commit/0e1fdd19aa5407b9344baa7eb931afdb8ddeba18))
* make enter confirm non-destructive prompts and guard them without a terminal ([#587](https://github.com/kelsin/sync-roms/issues/587)) ([b248d10](https://github.com/kelsin/sync-roms/commit/b248d10e1f5765be8daf16bddc2f164d29aac3ce))
* **themes:** scale pixel theme font sizes per screen ([#596](https://github.com/kelsin/sync-roms/issues/596)) ([845c4b5](https://github.com/kelsin/sync-roms/commit/845c4b50414fe21818b65dc590b192b6fa5afd7e))


### :book: Documentation

* **guide:** add a local network multiplayer section ([#598](https://github.com/kelsin/sync-roms/issues/598)) ([d745180](https://github.com/kelsin/sync-roms/commit/d7451801bac42a1b1142e0c605d5a3d062f00e50))

## [3.35.0](https://github.com/kelsin/sync-roms/compare/v3.34.0...v3.35.0) (2026-11-24)


### :video_game: Features

* **cards:** add cards install for a clean spruceOS install ([#582](https://github.com/kelsin/sync-roms/issues/582)) ([c782377](https://github.com/kelsin/sync-roms/commit/c78237713da3d2f4c0b8917f26e81a70e68f90b8))
* **sync:** point to a file system repair when a card folder is damaged ([#579](https://github.com/kelsin/sync-roms/issues/579)) ([18a06b0](https://github.com/kelsin/sync-roms/commit/18a06b05fd15d81a40da34a0a2de8ace4a66285a))
* **themes:** add ToTK-style collection art for spruce cards ([#581](https://github.com/kelsin/sync-roms/issues/581)) ([e1e2b08](https://github.com/kelsin/sync-roms/commit/e1e2b086c123a3698555f84fa32a35bfa433328c))

## [3.34.0](https://github.com/kelsin/sync-roms/compare/v3.33.0...v3.34.0) (2026-11-24)


### :video_game: Features

* **clean:** show live progress while deleting ._ files ([#572](https://github.com/kelsin/sync-roms/issues/572)) ([9334815](https://github.com/kelsin/sync-roms/commit/9334815a1ae20c16ae1fa31b5e1ed0d53e7e6046))
* **convert:** show a progress bar while cards convert moves and deletes files ([#577](https://github.com/kelsin/sync-roms/issues/577)) ([b1d9e42](https://github.com/kelsin/sync-roms/commit/b1d9e42a13ddcb7286e0f7bfe16ce66d29b98384))
* **spruce:** remind to run ez updater at the end of a sync that staged spruceos ([#573](https://github.com/kelsin/sync-roms/issues/573)) ([78ef2f3](https://github.com/kelsin/sync-roms/commit/78ef2f34f949ee2f8cf702d9b02cdf40bcc59a31))
* **sync:** remove the Surprise app from cards that aren't Onion ([#576](https://github.com/kelsin/sync-roms/issues/576)) ([7fc9c91](https://github.com/kelsin/sync-roms/commit/7fc9c916b1e7a05205b5e3619e6b1117c9afb1a2))
* **syncthing:** set up the shared folders on spruce cards ([#578](https://github.com/kelsin/sync-roms/issues/578)) ([6906cd8](https://github.com/kelsin/sync-roms/commit/6906cd84f94394a930f8dc4bf261ae216483ab6e))


### :bug: Bug Fixes

* **guide:** keep the header dropdowns on one row ([#575](https://github.com/kelsin/sync-roms/issues/575)) ([48ef813](https://github.com/kelsin/sync-roms/commit/48ef813b74d5c9cbe58cb61362f021c4d82e6646))
* **scrape:** print a single Nothing to make line when scrape art has nothing to do ([#569](https://github.com/kelsin/sync-roms/issues/569)) ([eb60d87](https://github.com/kelsin/sync-roms/commit/eb60d87c92c9fa8d165617fcce50688b1c4dc4ff))


### :book: Documentation

* **guide:** add click-to-copy to share paths, IDs and commands ([#574](https://github.com/kelsin/sync-roms/issues/574)) ([3e40cc5](https://github.com/kelsin/sync-roms/commit/3e40cc58819dd9596559beb85909d17539fb306e))
* **guide:** make the syncthing steps one checklist per device ([#570](https://github.com/kelsin/sync-roms/issues/570)) ([84c0885](https://github.com/kelsin/sync-roms/commit/84c08851fcc6d87bdbc4c00befa18264bd3ad48c))

## [3.33.0](https://github.com/kelsin/sync-roms/compare/v3.32.0...v3.33.0) (2026-11-24)


### :video_game: Features

* **guide:** pick a saved card to set the device and layout, spruce first ([#567](https://github.com/kelsin/sync-roms/issues/567)) ([d8b064b](https://github.com/kelsin/sync-roms/commit/d8b064b9845c595c2a91d8863153cf69ef7a42b2))


### :book: Documentation

* **guide:** point to the real modTimeWindowS location in Syncthing ([#568](https://github.com/kelsin/sync-roms/issues/568)) ([6fa4544](https://github.com/kelsin/sync-roms/commit/6fa4544368887beff16297b20222cab897ce01e0))


### :hammer_and_wrench: Code Refactoring

* **settings:** drop the spruce prefix from the RA and syncthing settings ([#565](https://github.com/kelsin/sync-roms/issues/565)) ([75ec336](https://github.com/kelsin/sync-roms/commit/75ec336e07bca73c9983d3ce5b2e3a973117ece3))

## [3.32.0](https://github.com/kelsin/sync-roms/compare/v3.31.0...v3.32.0) (2026-11-24)


### :video_game: Features

* **esde:** hide multi-disc discs on guest cards too ([#564](https://github.com/kelsin/sync-roms/issues/564)) ([02d0b6c](https://github.com/kelsin/sync-roms/commit/02d0b6c42b988d57226205ea28226f07472c97d4))
* **esde:** hide the discs of multi-disc games so only the playlist shows ([#563](https://github.com/kelsin/sync-roms/issues/563)) ([6bd69ee](https://github.com/kelsin/sync-roms/commit/6bd69eede99b9c79f72c51c7f86c89cdad09f970))


### :bug: Bug Fixes

* **guest:** remove the gamelist entries of the ROMs a guest sync deletes ([#561](https://github.com/kelsin/sync-roms/issues/561)) ([bfce27b](https://github.com/kelsin/sync-roms/commit/bfce27b676cea6b9c92272f78642435aa0562cc8))

## [3.31.0](https://github.com/kelsin/sync-roms/compare/v3.30.1...v3.31.0) (2026-11-24)


### :video_game: Features

* **themes:** redraw pixel menu icons for collections, games, apps and settings ([#556](https://github.com/kelsin/sync-roms/issues/556)) ([13d4859](https://github.com/kelsin/sync-roms/commit/13d4859f51a4425282274988dc959d78024e6e33))


### :bug: Bug Fixes

* **editor:** make the ? help and games hints list a, Esc and locked rows ([#560](https://github.com/kelsin/sync-roms/issues/560)) ([ea66282](https://github.com/kelsin/sync-roms/commit/ea66282e6caf98ec05273a8a032d4a440ebad4b2))
* **guest:** scrape only the games added this sync ([#559](https://github.com/kelsin/sync-roms/issues/559)) ([5172c1b](https://github.com/kelsin/sync-roms/commit/5172c1ba26ddbbfb9163f46c9b8228fbe8bc12d9))


### :book: Documentation

* **cards:** show --all in cards help ([#557](https://github.com/kelsin/sync-roms/issues/557)) ([0e4f2a6](https://github.com/kelsin/sync-roms/commit/0e4f2a64e55aea6f61bfb9bd1b7203587449ca66))

## [3.30.1](https://github.com/kelsin/sync-roms/compare/v3.30.0...v3.30.1) (2026-11-24)


### :bug: Bug Fixes

* **guest:** save seeded picks as game entries so they aren't deleted ([#555](https://github.com/kelsin/sync-roms/issues/555)) ([9d67d61](https://github.com/kelsin/sync-roms/commit/9d67d61bd64fe3dc46171883416e664195629ad4))
* **themes:** clear pyui's whole resized theme copy, not just its icons ([#552](https://github.com/kelsin/sync-roms/issues/552)) ([097faca](https://github.com/kelsin/sync-roms/commit/097faca3b848f3347be2075e192146e537542170))


### :hammer_and_wrench: Code Refactoring

* **cli:** rename umount to unmount, keep umount as an alias ([#553](https://github.com/kelsin/sync-roms/issues/553)) ([66e3840](https://github.com/kelsin/sync-roms/commit/66e3840d98f819dde9e49dc7625e94b93ad8da5b))

## [3.30.0](https://github.com/kelsin/sync-roms/compare/v3.29.0...v3.30.0) (2026-11-24)


### :video_game: Features

* **cards:** show the guest emoji with the badges in cards list ([#550](https://github.com/kelsin/sync-roms/issues/550)) ([3f0afdf](https://github.com/kelsin/sync-roms/commit/3f0afdf9dc41ac6e093878a1c823c1dd2a3875e4))


### :bug: Bug Fixes

* **themes:** clear pyui's resized icon copies when a spruce theme updates ([#548](https://github.com/kelsin/sync-roms/issues/548)) ([792051c](https://github.com/kelsin/sync-roms/commit/792051c08c5abc96bcc038c506d068f0c730c1d6))
* **upload:** default the upload confirm to yes ([#549](https://github.com/kelsin/sync-roms/issues/549)) ([fb48f42](https://github.com/kelsin/sync-roms/commit/fb48f42c663f62fafceaee85485ef0e96667125a))

## [3.29.0](https://github.com/kelsin/sync-roms/compare/v3.28.0...v3.29.0) (2026-11-23)


### :video_game: Features

* **themes:** show collections by default in the totk - james theme ([#545](https://github.com/kelsin/sync-roms/issues/545)) ([b92dfb7](https://github.com/kelsin/sync-roms/commit/b92dfb75dcc26561f502582447699d9aa1b683d0))


### :bug: Bug Fixes

* **themes:** draw the pixel list highlight bars one row tall ([#547](https://github.com/kelsin/sync-roms/issues/547)) ([cd161a8](https://github.com/kelsin/sync-roms/commit/cd161a81c271f21839472d39b918d5a21b597b15))
* **themes:** show republished theme previews in themes pick ([#544](https://github.com/kelsin/sync-roms/issues/544)) ([919bec4](https://github.com/kelsin/sync-roms/commit/919bec4e4c82ef30b554b8fa657ca8e0baa6135f))

## [3.28.0](https://github.com/kelsin/sync-roms/compare/v3.27.0...v3.28.0) (2026-11-23)


### :video_game: Features

* **themes:** add the totk - james theme ([#543](https://github.com/kelsin/sync-roms/issues/543)) ([803a02f](https://github.com/kelsin/sync-roms/commit/803a02f99999acfc0d2c24fa79f548fa3bb0f523))
* **themes:** preview pixel themes as their main screen in the palette ([#542](https://github.com/kelsin/sync-roms/issues/542)) ([4477ac9](https://github.com/kelsin/sync-roms/commit/4477ac9c37bf8a30479d9c178a6193ee9dcc3b13))
* **themes:** use the fusion pixel font in the pixel themes ([#540](https://github.com/kelsin/sync-roms/issues/540)) ([dad208e](https://github.com/kelsin/sync-roms/commit/dad208ee04274d14393654744dc1fd76d5a422f1))

## [3.27.0](https://github.com/kelsin/sync-roms/compare/v3.26.1...v3.27.0) (2026-11-23)


### :video_game: Features

* **devices:** add trimui brick, brick hammer, brick pro, smart pro and smart pro s ([#538](https://github.com/kelsin/sync-roms/issues/538)) ([96ea418](https://github.com/kelsin/sync-roms/commit/96ea418b87eba918b4a284576260a3a23fc429b5))

## [3.26.1](https://github.com/kelsin/sync-roms/compare/v3.26.0...v3.26.1) (2026-11-23)


### :bug: Bug Fixes

* **scrape:** hint at scrape art only for ROMs it can make spruce art for ([#537](https://github.com/kelsin/sync-roms/issues/537)) ([f4d27bd](https://github.com/kelsin/sync-roms/commit/f4d27bda58e451dbeb4e7a9827545361d8b45bf6))
* **spruce:** take out the draft reopen setting patch before highlighting the last collection ([#535](https://github.com/kelsin/sync-roms/issues/535)) ([0c46e7f](https://github.com/kelsin/sync-roms/commit/0c46e7f4f5f3e5028eac597d189ea7ed654f0f2f))

## [3.26.0](https://github.com/kelsin/sync-roms/compare/v3.25.0...v3.26.0) (2026-11-23)


### :video_game: Features

* **config:** add config apply for spruce cards and android devices ([#533](https://github.com/kelsin/sync-roms/issues/533)) ([e73654d](https://github.com/kelsin/sync-roms/commit/e73654d0c3d9ff1b5b19ae6e6e7c64cb57d98aef))
* **mount:** mount an unmounted SD card again without pulling it out ([#528](https://github.com/kelsin/sync-roms/issues/528)) ([5c2971a](https://github.com/kelsin/sync-roms/commit/5c2971aea7f063d93becc3101c22d4a2a5200069))
* **sync:** add guest cards for syncing friends' cards ([#534](https://github.com/kelsin/sync-roms/issues/534)) ([f025d33](https://github.com/kelsin/sync-roms/commit/f025d33c951e1b784b527dd926a2aa4bb0347fc7))
* **themes:** default the publish upload prompt to yes ([#527](https://github.com/kelsin/sync-roms/issues/527)) ([8d0e02c](https://github.com/kelsin/sync-roms/commit/8d0e02cf7d09a8ec4d2350b34fa26579d27c0f03))
* **themes:** draw missing app icons and show collections by default ([#530](https://github.com/kelsin/sync-roms/issues/530)) ([4231419](https://github.com/kelsin/sync-roms/commit/42314191a785b982dbb725e24b2803e824dac25a))


### :bug: Bug Fixes

* **spruce:** highlight the last collection instead of the reopen setting ([#532](https://github.com/kelsin/sync-roms/issues/532)) ([885fac4](https://github.com/kelsin/sync-roms/commit/885fac45d07123509ec443f4849a9e41553e2ce8))
* **themes:** frame the pixel list highlight bar with a light rim ([#531](https://github.com/kelsin/sync-roms/issues/531)) ([4b68602](https://github.com/kelsin/sync-roms/commit/4b68602df1e85a98f7e8fe826c2ade96dc219ce2))

## [3.25.0](https://github.com/kelsin/sync-roms/compare/v3.24.0...v3.25.0) (2026-11-23)


### :video_game: Features

* **cards:** turn systems and collection games off per card ([#525](https://github.com/kelsin/sync-roms/issues/525)) ([d556891](https://github.com/kelsin/sync-roms/commit/d556891421e980728b98250dde88a18f6285e80c))
* **devices:** add KONKR Pocket Block and make device ids consistent ([#523](https://github.com/kelsin/sync-roms/issues/523)) ([ccd0f8f](https://github.com/kelsin/sync-roms/commit/ccd0f8fbf55224d9427b7b850c5c521ddbb2eca1))
* **themes:** build and publish pixel-art spruce themes in many palettes ([#526](https://github.com/kelsin/sync-roms/issues/526)) ([f37526d](https://github.com/kelsin/sync-roms/commit/f37526d11d855461a9def9f1638c73f5483bbaed))
* **themes:** show download and upload progress in themes update ([#521](https://github.com/kelsin/sync-roms/issues/521)) ([a252189](https://github.com/kelsin/sync-roms/commit/a25218913b7bd77c7f57030b543b394d8ab9c11f))


### :bug: Bug Fixes

* **picker:** keep preview pictures at their aspect ratio ([#524](https://github.com/kelsin/sync-roms/issues/524)) ([4d009cc](https://github.com/kelsin/sync-roms/commit/4d009cc0087484a068caf5f5670e9b930a5a993e))

## [3.24.0](https://github.com/kelsin/sync-roms/compare/v3.23.0...v3.24.0) (2026-11-23)


### :video_game: Features

* **saves:** add saves manage to inspect, label, move, prune and delete stashes ([#518](https://github.com/kelsin/sync-roms/issues/518)) ([c9b3e2f](https://github.com/kelsin/sync-roms/commit/c9b3e2fa72213888ba7537e7673eb0287a0c8d93))
* **saves:** stash and apply android cards over wireless adb ([#520](https://github.com/kelsin/sync-roms/issues/520)) ([32d8969](https://github.com/kelsin/sync-roms/commit/32d8969ab3eb5d3fc6593043051c82ae2d7761f6))
* **spruce:** add the reopen last collection setting until spruceOS ships it ([#516](https://github.com/kelsin/sync-roms/issues/516)) ([5b36ebf](https://github.com/kelsin/sync-roms/commit/5b36ebfa880d9e1062d9758ab2db86d813dd0619))
* **spruce:** retro box art for collections ([#519](https://github.com/kelsin/sync-roms/issues/519)) ([b29fe48](https://github.com/kelsin/sync-roms/commit/b29fe48bda1bb5d8a87442f528f2b6220266b703))
* **spruce:** set cores and save settings for syncthing ([#514](https://github.com/kelsin/sync-roms/issues/514)) ([7d1cf4c](https://github.com/kelsin/sync-roms/commit/7d1cf4ce02fc10fe79a0b51112fad2e12dca5ad5))
* **spruce:** sync pyui themes to spruce cards ([#517](https://github.com/kelsin/sync-roms/issues/517)) ([e19bf6c](https://github.com/kelsin/sync-roms/commit/e19bf6c0e1d3cf344dee8ce4144d7458d83d8315))
* **spruce:** sync saved wifi networks to spruce cards ([#512](https://github.com/kelsin/sync-roms/issues/512)) ([1b0c5ce](https://github.com/kelsin/sync-roms/commit/1b0c5ce2b806485329dd524598fb43222885f604))
* **umount:** tidy and unmount a picked SD card ([#515](https://github.com/kelsin/sync-roms/issues/515)) ([dd45d0c](https://github.com/kelsin/sync-roms/commit/dd45d0ca2d8b3d94a496745b005f41f4ced978cf))

## [3.23.0](https://github.com/kelsin/sync-roms/compare/v3.22.0...v3.23.0) (2026-11-22)


### :video_game: Features

* **spruce:** stage personal boot logos and record device resolutions ([#511](https://github.com/kelsin/sync-roms/issues/511)) ([14fe91c](https://github.com/kelsin/sync-roms/commit/14fe91cc0289462d55047ead1881ad5da83895ca))


### :bug: Bug Fixes

* **spruce:** apply theme fixes to PyUI's resized theme copies ([#509](https://github.com/kelsin/sync-roms/issues/509)) ([cc9baeb](https://github.com/kelsin/sync-roms/commit/cc9baeb6a2985fbedb608dbc2c65b0f891173da5))

## [3.22.0](https://github.com/kelsin/sync-roms/compare/v3.21.0...v3.22.0) (2026-11-22)


### :video_game: Features

* **cardedit:** show full, partial and empty systems with distinct emoji ([#505](https://github.com/kelsin/sync-roms/issues/505)) ([cc6ef80](https://github.com/kelsin/sync-roms/commit/cc6ef80b971b0df2997194004018739cd7e4f478))


### :bug: Bug Fixes

* **spruce:** add Pokémon Mini logo files to the Art Book themes ([#507](https://github.com/kelsin/sync-roms/issues/507)) ([28ffed3](https://github.com/kelsin/sync-roms/commit/28ffed3aac48f8327da395c6fa1a849f56483023))
* **spruce:** replace the NES logo shown for FDS in the Art Book themes ([#508](https://github.com/kelsin/sync-roms/issues/508)) ([0547dc8](https://github.com/kelsin/sync-roms/commit/0547dc823cded050cf3515561b6d9c0493d2e3ed))

## [3.21.0](https://github.com/kelsin/sync-roms/compare/v3.20.1...v3.21.0) (2026-11-22)


### :video_game: Features

* **spruce:** put fbneo in ARCADE, mame in MAME2003PLUS and hide BIOS zips ([#502](https://github.com/kelsin/sync-roms/issues/502)) ([dbea898](https://github.com/kelsin/sync-roms/commit/dbea8984ad943b00ad95d8606962d026dff7b7c8))
* **spruce:** sync RetroAchievements and preference settings to spruce cards ([#504](https://github.com/kelsin/sync-roms/issues/504)) ([6dc1c41](https://github.com/kelsin/sync-roms/commit/6dc1c4180d0d7182f79d10cce8c0c74f8abcba4f))

## [3.20.1](https://github.com/kelsin/sync-roms/compare/v3.20.0...v3.20.1) (2026-11-22)


### :bug: Bug Fixes

* **scrape:** read PNGs with a bad optional chunk checksum and treat 0-byte media as missing ([#500](https://github.com/kelsin/sync-roms/issues/500)) ([0f7bf75](https://github.com/kelsin/sync-roms/commit/0f7bf759c4feca3311896b7e7c62416a7bdfb458))

## [3.20.0](https://github.com/kelsin/sync-roms/compare/v3.19.0...v3.20.0) (2026-11-22)


### :video_game: Features

* **spruce:** make QOI box art for Spruce and use covers first for Onion ([#498](https://github.com/kelsin/sync-roms/issues/498)) ([87fc125](https://github.com/kelsin/sync-roms/commit/87fc125007af0ff00e89924dd2da7955ca3af17e))


### :bug: Bug Fixes

* **cardedit:** import the module on its own ([#492](https://github.com/kelsin/sync-roms/issues/492)) ([04afa40](https://github.com/kelsin/sync-roms/commit/04afa406791b0e4883bb89e3c5b2ccc1399e1dd3))
* **chd:** keep a disc whose output another job just wrote ([#485](https://github.com/kelsin/sync-roms/issues/485)) ([ec72f7e](https://github.com/kelsin/sync-roms/commit/ec72f7ea4c5749a8bc0691e61d3b5f508eb52ebf))
* **chd:** make discs whose names differ only by case take turns ([#478](https://github.com/kelsin/sync-roms/issues/478)) ([d512dd9](https://github.com/kelsin/sync-roms/commit/d512dd95038535d841403d5cabb4a61404919a06))
* **chd:** read single-quoted file names in cue sheets ([#477](https://github.com/kelsin/sync-roms/issues/477)) ([95d5d4e](https://github.com/kelsin/sync-roms/commit/95d5d4ecf9a38aaaa82c4ac59808e70dac1d7039))
* close fake http errors, tool pipes and test files so no cleanup warning lands in another test ([#497](https://github.com/kelsin/sync-roms/issues/497)) ([5fa9760](https://github.com/kelsin/sync-roms/commit/5fa976029f343b31e70b1e5bee9f7e631a9c4927))
* **games:** keep a system's game list when games full switches it on and off ([#475](https://github.com/kelsin/sync-roms/issues/475)) ([60b9a5c](https://github.com/kelsin/sync-roms/commit/60b9a5c85287304228231cf75d074b2f15e48526))
* **sync:** don't crash a dry run on a card entry that isn't an object ([#496](https://github.com/kelsin/sync-roms/issues/496)) ([d0e0152](https://github.com/kelsin/sync-roms/commit/d0e015297babc0f88c5d50c3f8f373a3c190547d))
* **tools:** read tool output that isn't valid utf-8 ([#476](https://github.com/kelsin/sync-roms/issues/476)) ([5188326](https://github.com/kelsin/sync-roms/commit/51883265e2e366b1175030ef68c293ca18e6e099))


### :book: Documentation

* add handheld OS consolidation plan ([#491](https://github.com/kelsin/sync-roms/issues/491)) ([9d5736e](https://github.com/kelsin/sync-roms/commit/9d5736e95086cb5782b127df2f84a8e58215e50b))
* **claude:** correct and reorganise the project instructions ([#484](https://github.com/kelsin/sync-roms/issues/484)) ([ce5ce9c](https://github.com/kelsin/sync-roms/commit/ce5ce9cc94c919e11caf4a1df4aa61d378830bc6))
* **claude:** say who writes variants-checked.json ([#493](https://github.com/kelsin/sync-roms/issues/493)) ([3b8daff](https://github.com/kelsin/sync-roms/commit/3b8daffb87eb04c3eacd836018f449564f5610c6))
* **help:** correct the built-in help and stale docstrings ([#481](https://github.com/kelsin/sync-roms/issues/481)) ([3edf768](https://github.com/kelsin/sync-roms/commit/3edf7681ebef20481a3f5707fc6038c2082ef5f2))
* **readme:** correct and tidy the readme ([#490](https://github.com/kelsin/sync-roms/issues/490)) ([24c39cd](https://github.com/kelsin/sync-roms/commit/24c39cddd95c3d7d5292c4b5b7a11a0999abeb55))
* **skills:** correct the skills and the screenscraper notes against the code ([#480](https://github.com/kelsin/sync-roms/issues/480)) ([8c4c197](https://github.com/kelsin/sync-roms/commit/8c4c1977c004685022d3b1d4237c0a5a35bfe150))


### :hammer_and_wrench: Code Refactoring

* **card:** share the collection and art writers' common code ([#483](https://github.com/kelsin/sync-roms/issues/483)) ([1bb9063](https://github.com/kelsin/sync-roms/commit/1bb9063c3327633d4dce16a718bae9ad0ce352c9))
* **cards:** share repeated code in convert, saves and flash ([#487](https://github.com/kelsin/sync-roms/issues/487)) ([8dada16](https://github.com/kelsin/sync-roms/commit/8dada16249fd7e912b3034ff1cc388ce1176d713))
* **cli:** share repeated steps in the sync flow and commands ([#488](https://github.com/kelsin/sync-roms/issues/488)) ([7b81788](https://github.com/kelsin/sync-roms/commit/7b81788870079ebaf2075631888ef7eb9756ccd9))
* **edit:** share repeated code in the editors ([#489](https://github.com/kelsin/sync-roms/issues/489)) ([45dd875](https://github.com/kelsin/sync-roms/commit/45dd875cbc9fd688138c5279f0de61ef2f38a2dd))
* **install:** share the newest-file pick and the card entry read ([#482](https://github.com/kelsin/sync-roms/issues/482)) ([6d8be44](https://github.com/kelsin/sync-roms/commit/6d8be448981783e51cf4d14b3f5e47ffdf8a25c4))
* **scrape:** share the scrape modules' repeated parsing and flushing ([#486](https://github.com/kelsin/sync-roms/issues/486)) ([d3413d1](https://github.com/kelsin/sync-roms/commit/d3413d1cd3d136f1016774fe1a8b88c95341d779))
* **tests:** set up temp folders and patches with enterContext ([#499](https://github.com/kelsin/sync-roms/issues/499)) ([e76f643](https://github.com/kelsin/sync-roms/commit/e76f643faf7a698764216a0c52263acad4246d32))
* use the shared helpers at the remaining call sites ([#494](https://github.com/kelsin/sync-roms/issues/494)) ([bec5704](https://github.com/kelsin/sync-roms/commit/bec5704af7383015f8bb28d43371e362f6ba2731))


### :traffic_light: Tests

* share repeated fixtures through tests/helpers.py ([#495](https://github.com/kelsin/sync-roms/issues/495)) ([6dc972f](https://github.com/kelsin/sync-roms/commit/6dc972fb17cea217126db93dd8cae9ea8dcee109))

## [3.19.0](https://github.com/kelsin/sync-roms/compare/v3.18.0...v3.19.0) (2026-11-22)


### :video_game: Features

* **devices:** add miyoo a30 ([#432](https://github.com/kelsin/sync-roms/issues/432)) ([b6304a1](https://github.com/kelsin/sync-roms/commit/b6304a10655346d5753c529642439a65bb9a2daf))
* **flash:** offer OakMoss .img.xz images ([#431](https://github.com/kelsin/sync-roms/issues/431)) ([55acc53](https://github.com/kelsin/sync-roms/commit/55acc5310fc13aa0f7c0a4c6e3468287903859ef))
* **muos:** install the official pico-8 runtime ([#439](https://github.com/kelsin/sync-roms/issues/439)) ([440b8eb](https://github.com/kelsin/sync-roms/commit/440b8eba6d10a3ab2a397671d17cdc3ffdbb0536))
* **rocknix:** add ROCKNIX layout ([#429](https://github.com/kelsin/sync-roms/issues/429)) ([40e743c](https://github.com/kelsin/sync-roms/commit/40e743c7f8387033114ecca4d08efddd47f81657))
* **spruce:** add Art Book Next collection art in Collections/Imgs ([#450](https://github.com/kelsin/sync-roms/issues/450)) ([e92559b](https://github.com/kelsin/sync-roms/commit/e92559b6ee81459e0e0e528252843172e2002c27))
* **spruce:** install RAOfflineProxy on spruce cards ([#444](https://github.com/kelsin/sync-roms/issues/444)) ([e043cbe](https://github.com/kelsin/sync-roms/commit/e043cbed528827a9f39b545b57b38a434e102f20))
* **spruce:** stage the newest spruceOS release for EZ Updater ([#433](https://github.com/kelsin/sync-roms/issues/433)) ([c77924b](https://github.com/kelsin/sync-roms/commit/c77924b60ad6ac588e1b474dbe2113332b8315e1))


### :bug: Bug Fixes

* **cache:** patch the storage cache under the name's stored spelling ([#463](https://github.com/kelsin/sync-roms/issues/463)) ([1870146](https://github.com/kelsin/sync-roms/commit/1870146522dab9afd0eaedb0e83737090d8b5ba4))
* **cardedit:** count collection and surprise games as on the card for variants ([#465](https://github.com/kelsin/sync-roms/issues/465)) ([fca558d](https://github.com/kelsin/sync-roms/commit/fca558d6459bdc463b136f71332c11eafdd62896))
* **cardedit:** let space in the sets list switch on excluded games ([#453](https://github.com/kelsin/sync-roms/issues/453)) ([d2ea421](https://github.com/kelsin/sync-roms/commit/d2ea421b9229fd382c44c92216e69885a7451281))
* **cardedit:** recount the other system after adding a variant ([#449](https://github.com/kelsin/sync-roms/issues/449)) ([43e2c57](https://github.com/kelsin/sync-roms/commit/43e2c57be65660d535123d70b60ed84ee33e03a4))
* **cards:** keep media in folders the card's layout uses on clean ([#437](https://github.com/kelsin/sync-roms/issues/437)) ([b78fb1e](https://github.com/kelsin/sync-roms/commit/b78fb1ee993a26b3c2dc4da6b00f3b1b19d022ce))
* **chd:** count a job that raises an OSError as a failed job ([#473](https://github.com/kelsin/sync-roms/issues/473)) ([091bad3](https://github.com/kelsin/sync-roms/commit/091bad31844791f7204d211390d00058d323c8eb))
* **chd:** keep a source whose chd name already holds another disc ([#468](https://github.com/kelsin/sync-roms/issues/468)) ([048a121](https://github.com/kelsin/sync-roms/commit/048a1214853b919e55dbffd71519c0e8e0a36711))
* **chd:** read unquoted file names in cue sheets ([#472](https://github.com/kelsin/sync-roms/issues/472)) ([7aa93de](https://github.com/kelsin/sync-roms/commit/7aa93de4679378b196e8e5a96baed9dc9b6f64a2))
* **cli:** accept a leading --json before a command ([#462](https://github.com/kelsin/sync-roms/issues/462)) ([5c7d799](https://github.com/kelsin/sync-roms/commit/5c7d799325bf16f6bb67ba3f4f2d08b099e969c5))
* **cli:** exit 1 when a card with nothing to sync has failures ([#448](https://github.com/kelsin/sync-roms/issues/448)) ([4888db8](https://github.com/kelsin/sync-roms/commit/4888db83ef3344acaef993da9c392686a68933a6))
* **cli:** let --verbose doctor report an unparseable settings.json ([#467](https://github.com/kelsin/sync-roms/issues/467)) ([7500f28](https://github.com/kelsin/sync-roms/commit/7500f288f94f5ee1857fbde4c76833eeb055ca0e))
* **collections:** keep a note typed on a newly added game ([#457](https://github.com/kelsin/sync-roms/issues/457)) ([5a9951b](https://github.com/kelsin/sync-roms/commit/5a9951bde3ce976045c104d7bc126f675ad7a4eb))
* **convert:** convert cards to and from muos without crashing on saves ([#461](https://github.com/kelsin/sync-roms/issues/461)) ([6a04b84](https://github.com/kelsin/sync-roms/commit/6a04b84786bafdf35330c2cca99fec92992ddcdc))
* **convert:** leave rocknix's pico-8 runtime out of the roms it moves ([#436](https://github.com/kelsin/sync-roms/issues/436)) ([134e0e6](https://github.com/kelsin/sync-roms/commit/134e0e6911aea3af3acc12f640ce0463674c3f12))
* **devices:** correct firmware support and gpu data ([#445](https://github.com/kelsin/sync-roms/issues/445)) ([0691898](https://github.com/kelsin/sync-roms/commit/069189854f14027990bfc5a350793ce8a89840fa))
* **edit:** keep a full system's saved game list when the card's device changes ([#459](https://github.com/kelsin/sync-roms/issues/459)) ([20d0038](https://github.com/kelsin/sync-roms/commit/20d0038739623ff71ed72204f44d0ee4342c70d1))
* **games:** import a game listed twice only once ([#470](https://github.com/kelsin/sync-roms/issues/470)) ([9437039](https://github.com/kelsin/sync-roms/commit/9437039b21bfefe39bde1961636fe41d6808e7e9))
* **guide:** stop rocknix crashing the setup guide and fix stale steps ([#438](https://github.com/kelsin/sync-roms/issues/438)) ([6732212](https://github.com/kelsin/sync-roms/commit/673221286cc6c3044726f5a0523cced04215cf62))
* **knulli:** escape setting names in es_settings.cfg ([#454](https://github.com/kelsin/sync-roms/issues/454)) ([2d14887](https://github.com/kelsin/sync-roms/commit/2d14887f5422bf9016c70f8f105ecd6f5af49a53))
* **mirror:** keep the android apks in the mirror ([#455](https://github.com/kelsin/sync-roms/issues/455)) ([604e7c0](https://github.com/kelsin/sync-roms/commit/604e7c081803a475cbaeb0567aa839d0d321159b))
* **muos:** correct catalogue names and add missing muOS systems ([#440](https://github.com/kelsin/sync-roms/issues/440)) ([da28242](https://github.com/kelsin/sync-roms/commit/da28242a7a12a9b073ea25580488fb6321aa2466))
* **nextui:** match multi-disc games on the card for the keep key ([#451](https://github.com/kelsin/sync-roms/issues/451)) ([5ac10ce](https://github.com/kelsin/sync-roms/commit/5ac10ce43db9f2e2a195a3258dbadf061f1df455))
* **nextui:** put game art in the rom's own folder's .media ([#443](https://github.com/kelsin/sync-roms/issues/443)) ([103c28e](https://github.com/kelsin/sync-roms/commit/103c28e56dac35fe4aa7043086b197fb87dcfff1))
* **nextui:** use nextui's own system folder names ([#446](https://github.com/kelsin/sync-roms/issues/446)) ([adf5b30](https://github.com/kelsin/sync-roms/commit/adf5b303a0281ffbbf3b8084cb24c40b02d5afba))
* **pico8:** install pico-8 again after a card's layout changes ([#464](https://github.com/kelsin/sync-roms/issues/464)) ([178c93c](https://github.com/kelsin/sync-roms/commit/178c93cd4eb096e6505920aa7b7c516d2f05d7a2))
* **pico8:** move a cart's scrape state when it is upgraded ([#466](https://github.com/kelsin/sync-roms/issues/466)) ([1522926](https://github.com/kelsin/sync-roms/commit/15229260040af93f291cc5e7a9e75beba492f8b5))
* **pico8:** retarget a card's exclusions when a cart is upgraded ([#456](https://github.com/kelsin/sync-roms/issues/456)) ([f0faa33](https://github.com/kelsin/sync-roms/commit/f0faa332022da2ee3389596d1bf76ee5f10932ef))
* **scrape:** check storage before clearing a rom's shared scrape state ([#469](https://github.com/kelsin/sync-roms/issues/469)) ([9abfb0f](https://github.com/kelsin/sync-roms/commit/9abfb0f18c700848e2c258d80844c475573ab6d8))
* **scrape:** skip a media file that keeps failing instead of the whole rom ([#474](https://github.com/kelsin/sync-roms/issues/474)) ([670984f](https://github.com/kelsin/sync-roms/commit/670984f4f753d74901e98706d3997f02a2ef91dd))
* **sets:** skip a set file that isn't valid utf-8 ([#452](https://github.com/kelsin/sync-roms/issues/452)) ([f76a497](https://github.com/kelsin/sync-roms/commit/f76a49746190d83c7e278600113008685096e77c))
* **shared:** tag the mirror with the write's own tag ([#458](https://github.com/kelsin/sync-roms/issues/458)) ([c9b7ad0](https://github.com/kelsin/sync-roms/commit/c9b7ad05a466a9913d8861f4ab57e203328ee601))
* **spruce:** keep the owned collections when collections.json can't be read ([#435](https://github.com/kelsin/sync-roms/issues/435)) ([4519bb7](https://github.com/kelsin/sync-roms/commit/4519bb7ceed0269a8e16a1bcf5f627d227329db8))
* **spruce:** read saves and states from their core folders ([#441](https://github.com/kelsin/sync-roms/issues/441)) ([c5a5c8a](https://github.com/kelsin/sync-roms/commit/c5a5c8a744bc51b62d0ec851ba1ac3edb51ef57a))
* **themes:** remove collection art sync wrote once its collection is gone ([#471](https://github.com/kelsin/sync-roms/issues/471)) ([dfbe173](https://github.com/kelsin/sync-roms/commit/dfbe173f2d6f6935aba7df66e617e646acff7408))
* **upload:** leave a card's disc and media folders out of uploads ([#460](https://github.com/kelsin/sync-roms/issues/460)) ([f8ff0ac](https://github.com/kelsin/sync-roms/commit/f8ff0ac3715b183f5dd8292517cf686117f1270e))


### :rewind: Reverts

* install RAOfflineProxy on spruce cards ([#447](https://github.com/kelsin/sync-roms/issues/447)) ([67c0b18](https://github.com/kelsin/sync-roms/commit/67c0b183c2960bd54b220827ea4db56bce4aa8d9))


### :book: Documentation

* **guide:** add the steps sync-roms needs on each device ([#442](https://github.com/kelsin/sync-roms/issues/442)) ([61c68d8](https://github.com/kelsin/sync-roms/commit/61c68d8026659094004fe51d64c27412edf49b9c))


### :traffic_light: Tests

* **esde:** guard favorites already in a card's gamelists ([#434](https://github.com/kelsin/sync-roms/issues/434)) ([eac43bb](https://github.com/kelsin/sync-roms/commit/eac43bbbc352af5b1f0ccde0ee7f105d828039f7))

## [3.18.0](https://github.com/kelsin/sync-roms/compare/v3.17.0...v3.18.0) (2026-11-20)


### :video_game: Features

* **cards:** install RAOfflineProxy per layout with a card setting ([#426](https://github.com/kelsin/sync-roms/issues/426)) ([27d2065](https://github.com/kelsin/sync-roms/commit/27d2065709a09672a5acf45f9721687070bc0c0f))
* **cards:** show ❔ in the size slot for cards with no size set ([#425](https://github.com/kelsin/sync-roms/issues/425)) ([9f252a9](https://github.com/kelsin/sync-roms/commit/9f252a9821e2e9c4685125320b1c6fa71b7c596b))
* **guide:** add hotkeys cheat sheet to setup guide ([#424](https://github.com/kelsin/sync-roms/issues/424)) ([e0f6939](https://github.com/kelsin/sync-roms/commit/e0f6939e0fb50ee88c5262ea8633117aaedba8d0))
* **guide:** add RetroArch saving settings to setup guide ([#421](https://github.com/kelsin/sync-roms/issues/421)) ([a0a5ffb](https://github.com/kelsin/sync-roms/commit/a0a5ffb42f48370ca1d4ef4c46805e2c3cc2a24e))
* **spruce:** write collections to Collections/collections.json ([#427](https://github.com/kelsin/sync-roms/issues/427)) ([8555048](https://github.com/kelsin/sync-roms/commit/85550489b1424debca3e24404a9dbac80a859826))


### :broom: Chores

* run in a uv-managed venv on latest stable python ([#428](https://github.com/kelsin/sync-roms/issues/428)) ([5d575d8](https://github.com/kelsin/sync-roms/commit/5d575d89f53c94dccbec7f4eb2c84a9a84c900b8))


### :book: Documentation

* **guide:** add syncthing setup section per layout ([#423](https://github.com/kelsin/sync-roms/issues/423)) ([17f365b](https://github.com/kelsin/sync-roms/commit/17f365b77d8a79fb7c1b09a57dd87087055a452b))

## [3.17.0](https://github.com/kelsin/sync-roms/compare/v3.16.0...v3.17.0) (2026-11-20)


### :video_game: Features

* **cards:** delete old layout media on convert and add cards clean ([#419](https://github.com/kelsin/sync-roms/issues/419)) ([738350f](https://github.com/kelsin/sync-roms/commit/738350ffee8a74c3afbef28b98eb19a0c82d5e52))

## [3.16.0](https://github.com/kelsin/sync-roms/compare/v3.15.0...v3.16.0) (2026-11-20)


### :video_game: Features

* **cardedit:** move keep card files to K so k can move up ([#413](https://github.com/kelsin/sync-roms/issues/413)) ([bfb7759](https://github.com/kelsin/sync-roms/commit/bfb7759016b3cec0e2f7bb5b0f3696fb7bb2013b))
* **cards:** add convert to move a card's files to another layout ([#416](https://github.com/kelsin/sync-roms/issues/416)) ([ad4ef83](https://github.com/kelsin/sync-roms/commit/ad4ef83c172533b36610e4f904e7fb4f59770ee6))
* **cards:** add per-card theme and collections settings ([#418](https://github.com/kelsin/sync-roms/issues/418)) ([5e985a3](https://github.com/kelsin/sync-roms/commit/5e985a3d0d24df21dde62d09dabd1da11528941a))
* **muos:** add full muOS support ([#414](https://github.com/kelsin/sync-roms/issues/414)) ([051e8a8](https://github.com/kelsin/sync-roms/commit/051e8a8898e430de60217ae33cc4d2b368a8bc73))
* **surprise:** limit Surprise systems per card and clarify keep/replace picker ([#417](https://github.com/kelsin/sync-roms/issues/417)) ([0e51dc8](https://github.com/kelsin/sync-roms/commit/0e51dc8b6506717b1bd15ddfdc8552aebd7dbd03))

## [3.15.0](https://github.com/kelsin/sync-roms/compare/v3.14.0...v3.15.0) (2026-11-20)


### :video_game: Features

* **cardedit:** add k to keep card files during sync ([#409](https://github.com/kelsin/sync-roms/issues/409)) ([be1e8fa](https://github.com/kelsin/sync-roms/commit/be1e8fac5fe273320ce25d48f3a97f84190c72c8))
* **edit:** add an all-games view across systems ([#408](https://github.com/kelsin/sync-roms/issues/408)) ([9c029f8](https://github.com/kelsin/sync-roms/commit/9c029f89c9120128e1b01b3c9c90439395d537cf))
* **flash:** flash BaseOS images and read Knulli images from os/knulli ([#412](https://github.com/kelsin/sync-roms/issues/412)) ([adaf44f](https://github.com/kelsin/sync-roms/commit/adaf44f7f678ba79d71bc37979d5c5a982cfe6cb))
* **layouts:** add Spruce OS layout and enable it on supported Miyoo devices ([#411](https://github.com/kelsin/sync-roms/issues/411)) ([013c78b](https://github.com/kelsin/sync-roms/commit/013c78b35cf5dc90f9b209d624855ce39bba306b))
* **nextui:** add NextUI layout ([#410](https://github.com/kelsin/sync-roms/issues/410)) ([755a537](https://github.com/kelsin/sync-roms/commit/755a5376a0079ccee9ba4dc88f3e3bd0fae6b097))


### :hammer_and_wrench: Code Refactoring

* **flash:** drop the read-back verification ([#406](https://github.com/kelsin/sync-roms/issues/406)) ([3b88177](https://github.com/kelsin/sync-roms/commit/3b881773a2d6ab196d175c97c5e4b356a81239ce))

## [3.14.0](https://github.com/kelsin/sync-roms/compare/v3.13.0...v3.14.0) (2026-11-19)


### :video_game: Features

* **flash:** say why verify failed ([#404](https://github.com/kelsin/sync-roms/issues/404)) ([b0c512c](https://github.com/kelsin/sync-roms/commit/b0c512cd93586923ccf37a969da336316d295bbc))


### :bug: Bug Fixes

* **flash:** align progress lines and add a progress bar ([#403](https://github.com/kelsin/sync-roms/issues/403)) ([3b637b2](https://github.com/kelsin/sync-roms/commit/3b637b20287bcbed4cb59cf1c83d09b260b3177e))

## [3.13.0](https://github.com/kelsin/sync-roms/compare/v3.12.0...v3.13.0) (2026-11-19)


### :video_game: Features

* **guide:** add onion install order section ([#399](https://github.com/kelsin/sync-roms/issues/399)) ([b3e9e58](https://github.com/kelsin/sync-roms/commit/b3e9e58d95716f30a5e156af2c9a25c54a3279e4))
* **guide:** add onion shader steps and match knulli picks to its shader sets ([#402](https://github.com/kelsin/sync-roms/issues/402)) ([242703a](https://github.com/kelsin/sync-roms/commit/242703a937a3a75cbbfaa704df82b1fc25323735))
* **sync:** add --no-delete to keep everything on the card ([#401](https://github.com/kelsin/sync-roms/issues/401)) ([1d82c7c](https://github.com/kelsin/sync-roms/commit/1d82c7c9a9d40dd5bc58976028a529dc8d03442f))


### :bug: Bug Fixes

* **guide:** keep device and layout when clicking section pills ([#398](https://github.com/kelsin/sync-roms/issues/398)) ([c749fec](https://github.com/kelsin/sync-roms/commit/c749fecbc2b365a0c3acafd74357364e45319da6))

## [3.12.0](https://github.com/kelsin/sync-roms/compare/v3.11.0...v3.12.0) (2026-11-19)


### :video_game: Features

* **cards:** show surprise as an emoji badge column in cards list ([#396](https://github.com/kelsin/sync-roms/issues/396)) ([31e79d7](https://github.com/kelsin/sync-roms/commit/31e79d78ae001cbc625ff1b81a17e02142013c48))
* **devices:** flag devices without built-in wifi ([#397](https://github.com/kelsin/sync-roms/issues/397)) ([772239b](https://github.com/kelsin/sync-roms/commit/772239be726f69792b2300773fa147434428a252))
* **guide:** add raofflineproxy steps for knulli cards ([#393](https://github.com/kelsin/sync-roms/issues/393)) ([1d17546](https://github.com/kelsin/sync-roms/commit/1d17546ee5b2974961794b6392652989923ab5b4))
* **guide:** add retroachievements, cloud saves and shader sections ([#395](https://github.com/kelsin/sync-roms/issues/395)) ([2aaf26b](https://github.com/kelsin/sync-roms/commit/2aaf26b991220c52010ac397ba2113e59bafd276))

## [3.11.0](https://github.com/kelsin/sync-roms/compare/v3.10.0...v3.11.0) (2026-11-19)


### :video_game: Features

* **onion:** install the surprise app and write its game list ([#390](https://github.com/kelsin/sync-roms/issues/390)) ([5a4fe5b](https://github.com/kelsin/sync-roms/commit/5a4fe5b5ea9c80219e3451a75fb8e68cc0621577))
* **surprise:** default surprise on for onion cards ([#392](https://github.com/kelsin/sync-roms/issues/392)) ([f05b392](https://github.com/kelsin/sync-roms/commit/f05b392674d3836e4bfbc7216befa697c7588a4e))

## [3.10.0](https://github.com/kelsin/sync-roms/compare/v3.9.1...v3.10.0) (2026-11-19)


### :video_game: Features

* **cards:** show surprise on or off in cards list and the card editor ([#386](https://github.com/kelsin/sync-roms/issues/386)) ([0a14555](https://github.com/kelsin/sync-roms/commit/0a14555bc512f091311b900ed06e1ea0962a3a35))
* **flash:** add flash command to write a knulli image to an sd card ([#389](https://github.com/kelsin/sync-roms/issues/389)) ([51f40e3](https://github.com/kelsin/sync-roms/commit/51f40e38b55fae4328b755788022b2502c68f43e))
* **guide:** add emulator install and raofflineproxy steps per device ([#388](https://github.com/kelsin/sync-roms/issues/388)) ([287ee12](https://github.com/kelsin/sync-roms/commit/287ee12c43b3f366b6d33db34ce2efe87ade799d))
* **guide:** add guide command to open the device setup guide ([#387](https://github.com/kelsin/sync-roms/issues/387)) ([9ccd1c4](https://github.com/kelsin/sync-roms/commit/9ccd1c4d4518e5a95d86820b18a3975e111d9c1b))
* **saves:** add saves stash and apply to move retroarch saves ([#382](https://github.com/kelsin/sync-roms/issues/382)) ([03892a5](https://github.com/kelsin/sync-roms/commit/03892a5a9d242cadf57d643351afd76d5cc15a76))


### :book: Documentation

* add a device setup guide with device and layout pickers ([#383](https://github.com/kelsin/sync-roms/issues/383)) ([bef4561](https://github.com/kelsin/sync-roms/commit/bef4561ab9dfbab044dff77051d1965a80530ca0))
* describe the setup guide and link it from the readme ([#385](https://github.com/kelsin/sync-roms/issues/385)) ([dc82e51](https://github.com/kelsin/sync-roms/commit/dc82e51563c10ed463a40dc1986bfddbec778c12))

## [3.9.1](https://github.com/kelsin/sync-roms/compare/v3.9.0...v3.9.1) (2026-11-19)


### :zap: Performance Improvements

* **sync:** minimize sd card reads and writes during sync ([#380](https://github.com/kelsin/sync-roms/issues/380)) ([0d97459](https://github.com/kelsin/sync-roms/commit/0d97459892e269c93f18d6d52f6aa43ed152285f))

## [3.9.0](https://github.com/kelsin/sync-roms/compare/v3.8.0...v3.9.0) (2026-11-18)


### :video_game: Features

* **surprise:** default surprise off on layouts without collections ([#378](https://github.com/kelsin/sync-roms/issues/378)) ([3eb9ef0](https://github.com/kelsin/sync-roms/commit/3eb9ef0eb8eac58a2093e3d2bf5b5ddc57115699))
* **surprise:** pick from every system the device supports ([#376](https://github.com/kelsin/sync-roms/issues/376)) ([6b553b5](https://github.com/kelsin/sync-roms/commit/6b553b5ba24dcf33770c402db198533989addff5))
* **ui:** show a mini progress bar for each file in flight ([#379](https://github.com/kelsin/sync-roms/issues/379)) ([be2218b](https://github.com/kelsin/sync-roms/commit/be2218b8c23f667c88ba3061e49e1142f4391714))

## [3.8.0](https://github.com/kelsin/sync-roms/compare/v3.7.0...v3.8.0) (2026-11-18)


### :video_game: Features

* add config set, review collections before saving, and speed up cache and sync ([#374](https://github.com/kelsin/sync-roms/issues/374)) ([c4e3154](https://github.com/kelsin/sync-roms/commit/c4e31549df6c1cd6641529bca196bf3e063c8c5d))
* **cardedit:** narrow a system's set filter to one series with r ([#375](https://github.com/kelsin/sync-roms/issues/375)) ([c156383](https://github.com/kelsin/sync-roms/commit/c15638391d9acd6684bd3b4b771cff3ac95cb381))


### :bug: Bug Fixes

* stop overwriting a broken settings.json and drop android media cleanup ([#372](https://github.com/kelsin/sync-roms/issues/372)) ([ef39090](https://github.com/kelsin/sync-roms/commit/ef390902a2b1ce06fe69dee609abaed2fb70aa33))

## [3.7.0](https://github.com/kelsin/sync-roms/compare/v3.6.1...v3.7.0) (2026-11-18)


### :video_game: Features

* **scrape:** scrape pico8 carts, cart picture only as fallback ([#369](https://github.com/kelsin/sync-roms/issues/369)) ([d7c233e](https://github.com/kelsin/sync-roms/commit/d7c233ee271cb32bf16eec12b3f96527b72745dc))

## [3.6.1](https://github.com/kelsin/sync-roms/compare/v3.6.0...v3.6.1) (2026-11-18)


### :gear: Continuous Integration

* run bump-tap on ubuntu without the install check ([#367](https://github.com/kelsin/sync-roms/issues/367)) ([2ee8d7c](https://github.com/kelsin/sync-roms/commit/2ee8d7cca82ebd3cfe825e78812695e0ae06e630))

## [3.6.0](https://github.com/kelsin/sync-roms/compare/v3.5.0...v3.6.0) (2026-11-18)


### :video_game: Features

* **cards:** show a footnote marker for unsized cards in cards list ([#365](https://github.com/kelsin/sync-roms/issues/365)) ([77e0c5d](https://github.com/kelsin/sync-roms/commit/77e0c5dbc8ca5fd5c40f58ec070df45c0ef1bdc0))


### :bug: Bug Fixes

* **scrape:** default the clean scrapes delete prompt to yes ([#364](https://github.com/kelsin/sync-roms/issues/364)) ([a6509a9](https://github.com/kelsin/sync-roms/commit/a6509a9a4af64accf874d6f0c7ea7240f18d1164))

## [3.5.0](https://github.com/kelsin/sync-roms/compare/v3.4.0...v3.5.0) (2026-11-18)


### :video_game: Features

* **pico8:** use each cart as its own image instead of scraping ([#359](https://github.com/kelsin/sync-roms/issues/359)) ([9f6b5ee](https://github.com/kelsin/sync-roms/commit/9f6b5eeacfebea5526b8aed6446d6e388f13e4cc))
* **scrape:** keep scrape state in storage ([#361](https://github.com/kelsin/sync-roms/issues/361)) ([d6fb677](https://github.com/kelsin/sync-roms/commit/d6fb677cae612558d3e23a7b2bcf3435d180d4fe))
* **sets:** keep game sets in storage ([#362](https://github.com/kelsin/sync-roms/issues/362)) ([82898a7](https://github.com/kelsin/sync-roms/commit/82898a7c4536a5669f938123d485aa613fb97c4d))
* **surprise:** fill empty surprise slots at the end, after the card editor ([#358](https://github.com/kelsin/sync-roms/issues/358)) ([6c1d32a](https://github.com/kelsin/sync-roms/commit/6c1d32a85ad3c100f6b5d992f3b3b16a57168b63))


### :bug: Bug Fixes

* disable macOS AppleDouble file creation during syncing ([#357](https://github.com/kelsin/sync-roms/issues/357)) ([7ff8906](https://github.com/kelsin/sync-roms/commit/7ff890605894552baf3142860b7ca7fe94d3f439))


### :broom: Chores

* **sets:** remove the repo copy of the game sets ([#363](https://github.com/kelsin/sync-roms/issues/363)) ([f6bad85](https://github.com/kelsin/sync-roms/commit/f6bad8559bccda929d27fdd1efeda9e3a9eec47a))


### :hammer_and_wrench: Code Refactoring

* drop clones.json and name arcade sets from scraped metadata ([#356](https://github.com/kelsin/sync-roms/issues/356)) ([8717771](https://github.com/kelsin/sync-roms/commit/87177712a92234ece8b1e982a0ab9ec6267b4082))
* keep shared storage files and caches in their own folders ([#354](https://github.com/kelsin/sync-roms/issues/354)) ([10b42c1](https://github.com/kelsin/sync-roms/commit/10b42c1ea27834697f90aa11459ee2e692c9cd4d))
* remove muOS support ([#360](https://github.com/kelsin/sync-roms/issues/360)) ([16febdc](https://github.com/kelsin/sync-roms/commit/16febdc878fffcce451195d5d08e6a154d828fef))

## [3.4.0](https://github.com/kelsin/sync-roms/compare/v3.3.1...v3.4.0) (2026-11-18)


### :video_game: Features

* **cardedit:** mark games with a variant on the card ([#350](https://github.com/kelsin/sync-roms/issues/350)) ([57374e3](https://github.com/kelsin/sync-roms/commit/57374e3f164178b955d8ed8039229994e36a0e2f))
* **sets:** filter set games by series ([#353](https://github.com/kelsin/sync-roms/issues/353)) ([d0fbfee](https://github.com/kelsin/sync-roms/commit/d0fbfeefc3d6799fc9036f28d57225b224f11c4e))


### :bug: Bug Fixes

* **edit:** clear the search text with c along with the other filters ([#349](https://github.com/kelsin/sync-roms/issues/349)) ([5976256](https://github.com/kelsin/sync-roms/commit/597625675600308508187f866a097b316675f006))
* **surprise:** draw a fresh card's surprises from all its systems ([#352](https://github.com/kelsin/sync-roms/issues/352)) ([a55e174](https://github.com/kelsin/sync-roms/commit/a55e17436624cb732bc5821fdc69009ccd06c1eb))

## [3.3.1](https://github.com/kelsin/sync-roms/compare/v3.3.0...v3.3.1) (2026-11-18)


### :bug: Bug Fixes

* **sync:** steady the progress bar's time left ([#347](https://github.com/kelsin/sync-roms/issues/347)) ([8cc571b](https://github.com/kelsin/sync-roms/commit/8cc571be5e9acc24e89140641d10ec1b6c9edc57))

## [3.3.0](https://github.com/kelsin/sync-roms/compare/v3.2.0...v3.3.0) (2026-11-18)


### :video_game: Features

* **sets:** fill sets from storage and add every fan translation ([#345](https://github.com/kelsin/sync-roms/issues/345)) ([88e924b](https://github.com/kelsin/sync-roms/commit/88e924b79eed1e7c3734ded35632abe056cf67bc))


### :bug: Bug Fixes

* **cli:** align the columns of cards list ([#346](https://github.com/kelsin/sync-roms/issues/346)) ([3913bf6](https://github.com/kelsin/sync-roms/commit/3913bf6a2878b833d2d4a21c06a3d5a64d6df30e))
* **edit:** count a set's games, not their files, in the system sets list ([#343](https://github.com/kelsin/sync-roms/issues/343)) ([778a469](https://github.com/kelsin/sync-roms/commit/778a4696d62ac925d8fd44b2155f8bd92341d8e6))

## [3.2.0](https://github.com/kelsin/sync-roms/compare/v3.1.0...v3.2.0) (2026-11-17)


### :video_game: Features

* **cli:** add cards copy to merge one card's selections into another ([#340](https://github.com/kelsin/sync-roms/issues/340)) ([e63d529](https://github.com/kelsin/sync-roms/commit/e63d529b9fe0820ee4eb57d57bf976d4058f6c28))
* **cli:** show each card's planned space and picks in cards list ([#341](https://github.com/kelsin/sync-roms/issues/341)) ([6d8bb61](https://github.com/kelsin/sync-roms/commit/6d8bb61d3bc75db7a9fbb1b72ca0190f438e7984))
* **edit:** show multi-disc games as their playlist only ([#337](https://github.com/kelsin/sync-roms/issues/337)) ([7680ce5](https://github.com/kelsin/sync-roms/commit/7680ce52d8919592bfa054088fd32552f52641df))
* **edit:** view a set's games across a card's systems ([#342](https://github.com/kelsin/sync-roms/issues/342)) ([f7bf762](https://github.com/kelsin/sync-roms/commit/f7bf76298073f8d9118c7aa61721922af860963e))


### :bug: Bug Fixes

* **sync:** flush large downloads to the card as they go ([#339](https://github.com/kelsin/sync-roms/issues/339)) ([0ad70e3](https://github.com/kelsin/sync-roms/commit/0ad70e3668431ef059a483beb19cc530f167909b))

## [3.1.0](https://github.com/kelsin/sync-roms/compare/v3.0.2...v3.1.0) (2026-11-17)


### :video_game: Features

* **cli:** add layouts command to list firmware layouts ([#333](https://github.com/kelsin/sync-roms/issues/333)) ([92ea906](https://github.com/kelsin/sync-roms/commit/92ea906ff04a15f0558f7e6ebee7cd213227b68c))
* **cli:** make list the default cards subcommand ([#336](https://github.com/kelsin/sync-roms/issues/336)) ([262e464](https://github.com/kelsin/sync-roms/commit/262e464de2a0cea50c927bbc8cd46db6f3fe7fd8))
* **devices:** rename miyoo flip and add miyoo mini and mini plus ([#332](https://github.com/kelsin/sync-roms/issues/332)) ([a0b8b0e](https://github.com/kelsin/sync-roms/commit/a0b8b0e34e740858f36e6838825ef58d8ab44c7d))


### :traffic_light: Tests

* **upload:** wait for the second move before the first ctrl-c in the abort test ([#335](https://github.com/kelsin/sync-roms/issues/335)) ([3f0939e](https://github.com/kelsin/sync-roms/commit/3f0939e9e2903bbd6ddd5dcb5aa018b9e088059e))

## [3.0.2](https://github.com/kelsin/sync-roms/compare/v3.0.1...v3.0.2) (2026-11-17)


### :bug: Bug Fixes

* **m3u:** group discs labelled with letters or roman numerals ([#330](https://github.com/kelsin/sync-roms/issues/330)) ([583416f](https://github.com/kelsin/sync-roms/commit/583416f1d8f8e49d00018a20acc397477eac2f53))

## [3.0.1](https://github.com/kelsin/sync-roms/compare/v3.0.0...v3.0.1) (2026-11-17)


### :bug: Bug Fixes

* **cardedit:** toggle collections in place without a slow recount ([#327](https://github.com/kelsin/sync-roms/issues/327)) ([9bcc4c2](https://github.com/kelsin/sync-roms/commit/9bcc4c2dad39eda1c3307ef4ea32c14eff980a22))
* **m3u:** keep bracket tags after (Disc N) in playlist grouping and names ([#329](https://github.com/kelsin/sync-roms/issues/329)) ([794b108](https://github.com/kelsin/sync-roms/commit/794b1080241555c14bf99f76702650a5cdb726e2))

## [3.0.0](https://github.com/kelsin/sync-roms/compare/v2.16.0...v3.0.0) (2026-11-16)


### ⚠ BREAKING CHANGES

* remove the slot layout ([#323](https://github.com/kelsin/sync-roms/issues/323))
* **upload:** drop upload scrapes now that scraping is native ([#321](https://github.com/kelsin/sync-roms/issues/321))

### :video_game: Features

* **scrape:** add dedup-names skill and a qualifier for same-named ROMs ([#325](https://github.com/kelsin/sync-roms/issues/325)) ([93839df](https://github.com/kelsin/sync-roms/commit/93839df245b0a757873bb5b8717ecfdc040b5e5a))
* **skills:** add match-translations skill for fan-translated scrape reviews ([#324](https://github.com/kelsin/sync-roms/issues/324)) ([6e603fd](https://github.com/kelsin/sync-roms/commit/6e603fdde2270ff3ef6c0443096f7a28e28702f4))
* **upload:** drop upload scrapes now that scraping is native ([#321](https://github.com/kelsin/sync-roms/issues/321)) ([eb22b9b](https://github.com/kelsin/sync-roms/commit/eb22b9bf573ec0d7dbcf5672f0068120a8850f21))


### :book: Documentation

* document the Claude Code skills in the readme ([#326](https://github.com/kelsin/sync-roms/issues/326)) ([f0c979c](https://github.com/kelsin/sync-roms/commit/f0c979c2859301e94951dc706d5e0dfd49086e03))


### :hammer_and_wrench: Code Refactoring

* remove the slot layout ([#323](https://github.com/kelsin/sync-roms/issues/323)) ([5e2c4e3](https://github.com/kelsin/sync-roms/commit/5e2c4e3e3d6a731a7ee6b3e238e179827acd75ea))

## [2.16.0](https://github.com/kelsin/sync-roms/compare/v2.15.0...v2.16.0) (2026-11-16)


### :video_game: Features

* **scrape:** title fan translations "&lt;name&gt; - Translated" ([#320](https://github.com/kelsin/sync-roms/issues/320)) ([fe60f42](https://github.com/kelsin/sync-roms/commit/fe60f428c48e94052b87fbacdd6cec72fd8eec82))


### :bug: Bug Fixes

* **convert:** unzip an archive that holds a chd and keep the chd ([#318](https://github.com/kelsin/sync-roms/issues/318)) ([f5a5ea9](https://github.com/kelsin/sync-roms/commit/f5a5ea93130faefc5247537ec21adf9abe3f6449))

## [2.15.0](https://github.com/kelsin/sync-roms/compare/v2.14.0...v2.15.0) (2026-11-16)


### :video_game: Features

* **cards:** add cards export and cards import ([#316](https://github.com/kelsin/sync-roms/issues/316)) ([cd72ee2](https://github.com/kelsin/sync-roms/commit/cd72ee20fed8d6c0df0bd80e202f92c6c30c7ede))

## [2.14.0](https://github.com/kelsin/sync-roms/compare/v2.13.0...v2.14.0) (2026-11-16)


### :video_game: Features

* **emudeck:** write custom collections and gamelists into ES-DE's data folder ([#314](https://github.com/kelsin/sync-roms/issues/314)) ([963a50f](https://github.com/kelsin/sync-roms/commit/963a50fbc130f0b39c6a2fa8684bdbe82a548818))

## [2.13.0](https://github.com/kelsin/sync-roms/compare/v2.12.0...v2.13.0) (2026-11-16)


### :video_game: Features

* **sync:** print transfers as they finish and list the ones in flight ([#312](https://github.com/kelsin/sync-roms/issues/312)) ([f851d47](https://github.com/kelsin/sync-roms/commit/f851d4716adaa70e8d74818a01c3d2dbb9c076a1))

## [2.12.0](https://github.com/kelsin/sync-roms/compare/v2.11.0...v2.12.0) (2026-11-15)


### :video_game: Features

* **cardedit:** show each system's size as a full system ([#311](https://github.com/kelsin/sync-roms/issues/311)) ([9f91dcd](https://github.com/kelsin/sync-roms/commit/9f91dcd0370c0170842a657294576c581133c723))
* **picker:** show every list as a left-aligned table ([#310](https://github.com/kelsin/sync-roms/issues/310)) ([887c0c8](https://github.com/kelsin/sync-roms/commit/887c0c8ab296b75e937ba5a90f4bd425472b59e7))
* **surprise:** pick surprises from full systems too ([#308](https://github.com/kelsin/sync-roms/issues/308)) ([58c48f3](https://github.com/kelsin/sync-roms/commit/58c48f3cf25b907d1d512d594287904382d82791))

## [2.11.0](https://github.com/kelsin/sync-roms/compare/v2.10.0...v2.11.0) (2026-11-15)


### :video_game: Features

* **collections:** drop categories from collections ([#307](https://github.com/kelsin/sync-roms/issues/307)) ([c38cd0c](https://github.com/kelsin/sync-roms/commit/c38cd0c084ae6d737d8380d175c541ef8b4e96d0))
* **scrape:** default the scrape confirmation to yes ([#304](https://github.com/kelsin/sync-roms/issues/304)) ([72c6593](https://github.com/kelsin/sync-roms/commit/72c6593d11c318ed016601bf50563eb119e722c7))


### :bug: Bug Fixes

* **picker:** make enter leave the search in every list ([#306](https://github.com/kelsin/sync-roms/issues/306)) ([60f6478](https://github.com/kelsin/sync-roms/commit/60f64789c3a03493cde1f0d7e2a7d02d4fbcc232))

## [2.10.0](https://github.com/kelsin/sync-roms/compare/v2.9.0...v2.10.0) (2026-11-14)


### :video_game: Features

* set up official PICO-8 on cards and download BBS Featured carts ([#302](https://github.com/kelsin/sync-roms/issues/302)) ([904b3a3](https://github.com/kelsin/sync-roms/commit/904b3a3d30e56409f13901da55c47b8dc5089b9b))

## [2.9.0](https://github.com/kelsin/sync-roms/compare/v2.8.0...v2.9.0) (2026-11-14)


### :video_game: Features

* **edit:** keep prompts and notes inside the editor app ([#300](https://github.com/kelsin/sync-roms/issues/300)) ([0ee7529](https://github.com/kelsin/sync-roms/commit/0ee7529f51e742b009f8ad629788ab64506680b3))
* **edit:** show each set's emoji next to its name ([#299](https://github.com/kelsin/sync-roms/issues/299)) ([b6a650c](https://github.com/kelsin/sync-roms/commit/b6a650cd21806dabbdfbb6a25aa9562b21afe2b8))


### :bug: Bug Fixes

* **collections:** let the editor save a collection with no games ([#297](https://github.com/kelsin/sync-roms/issues/297)) ([acf71e8](https://github.com/kelsin/sync-roms/commit/acf71e8aed5d86ce7f61b6cfc66a979f93608246))
* **edit:** show mame and fbneo game names in the card editor's rows ([#296](https://github.com/kelsin/sync-roms/issues/296)) ([ec24033](https://github.com/kelsin/sync-roms/commit/ec24033b8a824d41886afdc29c7ef4b67d05ddc6))


### :zap: Performance Improvements

* **picker:** load game pictures in the background from a thumbnail cache ([#301](https://github.com/kelsin/sync-roms/issues/301)) ([b9f7aff](https://github.com/kelsin/sync-roms/commit/b9f7aff10becc94c3edfb9cd694a450b08aa9ff2))

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
