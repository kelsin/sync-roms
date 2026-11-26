# ToTK - James and ToTK - Kelsin theme art

- `cards/<id>-f.png` and `cards/<id>-n.png` (`sidon`, `riju`, `mineru`, `rauru`): focused and normal main menu cards, 156x328.
- `bg-title.png` and `bg-title-kelsin.png`: the Triforce and "James" (`ToTK - James`) or "Kelsin" (`ToTK - Kelsin`) in the ToTK theme's own font, 196x51.
- `collections/Imgs|Imgs_med|Imgs_small/<id>.png`: ToTK-style collection art for spruce cards (336x480, 210x300, 140x200), from the outline drawings of `tools/gen_theme_art.py`. Regenerate with `uv run python tools/gen_zelda_art.py` (reads HYLIA from the ToTK theme; `--sheet` writes a contact sheet to the cache).

Regenerate with `uv run python tools/gen_totk_james.py` (reads the ToTK theme from storage, downloads the renders into the cache, writes a review sheet there).

## Credits

- Character art (c) Nintendo, from Zelda Wiki:
  - https://cdn.wikimg.net/en/zeldawiki/images/5/54/TotK_Sidon_Artwork_2.png
  - https://cdn.wikimg.net/en/zeldawiki/images/1/14/TotK_Riju_Artwork_2.png
  - https://cdn.wikimg.net/en/zeldawiki/images/1/10/TotK_Mineru_Artwork.png
  - https://cdn.wikimg.net/en/zeldawiki/images/a/a4/TotK_Rauru_Artwork_2.png
- Card frame, swirl background, Triforce and the HYLIA font: the ToTK PyUI theme, adapted by CraigN (CruxisMithos) from NaraMakesGames' Onion theme; HYLIA font by Ruidacosta.
