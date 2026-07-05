# tools — raccoon sticker pipeline (dev machine only)

Generates the `assets/images/raccoon*.png` sticker art. Not needed on the Pi.

- `generate.mjs` — Gemini 2.5 Flash Image batch generator. Brand style is
  anchored by the STYLE contract string and the style-ref images from
  `boxofraccoons-website/assets/style-refs/` (repo expected as a sibling
  checkout; reads `GEMINI_API_KEY` from that repo's `.env`). Writes raw
  white-background generations to `./raw/`.
- `halo.mjs` — sticker processor: soft-alpha knockout of the white background,
  uniform #f7f7f0 distance-transform halo (same method as the website's
  `process-stickers.mjs`), 512px output to `./stickers/`. All fully-transparent
  pixels carry the halo color, NOT black — pygame's smoothscale is not
  premultiplied and bleeds transparent-pixel RGB into edges when scaling.

Setup/run (from this directory):

```sh
npm install sharp
node generate.mjs          # all jobs (skips existing raw files)
node generate.mjs book     # one job (overwrites)
node halo.mjs              # process all raws into stickers
```

Shipped mapping (`assets/images/`, filename = spoken word): hello=wave scene,
love=heart-hug, bubbles, blocks, balloon, peekaboo, drum, hug=teddy,
draw=crayons, sandwich, water, book, sleep. ("love" not "heart" — `heart.png`
would reskin the heart *shape*.) The generate.mjs job names still use the
scene names (wave, heart, teddy, crayons); rename when copying into assets.

Touching up shipped art in an image editor is fine — they're plain PNGs. If
edges look dark/jagged in the app after a re-export, the editor probably wrote
black into transparent pixels; run the file through `halo.mjs` again (drop it
in `raw/` only if it still has a white background — otherwise fix the export
settings or ask Claude to re-process it).
