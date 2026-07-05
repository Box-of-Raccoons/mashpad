// mashpad raccoon art — sticker halo processor (v2, anti-aliased subject edge).
// Method from boxofraccoons-website scripts/process-stickers.mjs, plus a soft
// subject mask: the original art meets a pure-white background, so pixels near
// white are edge anti-aliasing — v1 binary-classified them (jagged edges); v2
// gives the subject a whiteness-ramped alpha and blends edge pixels into the
// halo color, so the art→halo boundary is smooth.

import sharp from 'sharp';
import { mkdir, readdir } from 'node:fs/promises';
import { resolve } from 'node:path';

const RAW = resolve('./raw');
const OUT = resolve('./stickers');
const HALO = 16;               // ring thickness on the 1024px canvas (same as site)
const HALO_RGB = [247, 247, 240]; // #f7f7f0 — the site's sticker off-white
const W_LO = 232;              // min channel <= this → fully subject (alpha 255)
const W_HI = 250;              // min channel >= this → fully background (alpha 0)
const RAMP = 2.5;              // anti-aliased outer edge width of the halo, px
const FINAL = 512;             // shipped size (mashpad rescales at runtime)

function distanceTransform(subj, W, H) {
  const N = W * H, INF = 1e9, d = new Float32Array(N);
  for (let p = 0; p < N; p++) d[p] = subj[p] ? 0 : INF;
  const D1 = 1, D2 = 1.4142;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const p = y * W + x; let v = d[p];
    if (x > 0) v = Math.min(v, d[p - 1] + D1);
    if (y > 0) v = Math.min(v, d[p - W] + D1);
    if (x > 0 && y > 0) v = Math.min(v, d[p - W - 1] + D2);
    if (x < W - 1 && y > 0) v = Math.min(v, d[p - W + 1] + D2);
    d[p] = v;
  }
  for (let y = H - 1; y >= 0; y--) for (let x = W - 1; x >= 0; x--) {
    const p = y * W + x; let v = d[p];
    if (x < W - 1) v = Math.min(v, d[p + 1] + D1);
    if (y < H - 1) v = Math.min(v, d[p + W] + D1);
    if (x < W - 1 && y < H - 1) v = Math.min(v, d[p + W + 1] + D2);
    if (x > 0 && y < H - 1) v = Math.min(v, d[p + W - 1] + D2);
    d[p] = v;
  }
  return d;
}

async function haloOne(name) {
  const img = sharp(resolve(RAW, `${name}.png`)).ensureAlpha();
  const { data, info } = await img.raw().toBuffer({ resolveWithObject: true });
  const { width: W, height: H, channels: CH } = info;
  const N = W * H;

  // Soft subject alpha from "distance to white": 255 at W_LO, 0 at W_HI.
  const subjA = new Uint8Array(N);
  const seed = new Uint8Array(N); // DT seeds: solidly-subject pixels only
  for (let p = 0; p < N; p++) {
    const i = p * CH;
    const mn = Math.min(data[i], data[i + 1], data[i + 2]);
    const a = mn <= W_LO ? 255 : mn >= W_HI ? 0 : Math.round(255 * (W_HI - mn) / (W_HI - W_LO));
    subjA[p] = a;
    if (a >= 128) seed[p] = 1;
  }

  const dist = distanceTransform(seed, W, H);
  const out = Buffer.alloc(N * 4);
  for (let p = 0; p < N; p++) {
    const i = p * CH, o = p * 4;
    const d = dist[p];
    // Halo ring alpha: opaque within HALO px of the subject, ramped outer edge.
    const haloA = d <= HALO ? 255 : d >= HALO + RAMP ? 0 : Math.round(255 * (1 - (d - HALO) / RAMP));
    const sa = subjA[p] / 255;
    // Art blended over the halo color by its soft alpha; ring supplies the base.
    out[o]     = Math.round(data[i]     * sa + HALO_RGB[0] * (1 - sa));
    out[o + 1] = Math.round(data[i + 1] * sa + HALO_RGB[1] * (1 - sa));
    out[o + 2] = Math.round(data[i + 2] * sa + HALO_RGB[2] * (1 - sa));
    out[o + 3] = Math.max(subjA[p], haloA);
  }

  await sharp(out, { raw: { width: W, height: H, channels: 4 } })
    .trim()
    .png()
    .toBuffer()
    .then((buf) =>
      sharp(buf)
        .resize(FINAL, FINAL, { fit: 'contain', background: { r: HALO_RGB[0], g: HALO_RGB[1], b: HALO_RGB[2], alpha: 0 } })
        .raw()
        .toBuffer({ resolveWithObject: true })
    )
    .then(async ({ data: fd, info: fi }) => {
      // Premultiplied resize zeroes the RGB of transparent pixels (black bleed
      // in non-premultiplied scalers like pygame smoothscale). Rewrite them.
      for (let p = 0; p < fi.width * fi.height; p++) {
        const i = p * 4;
        if (fd[i + 3] === 0) { fd[i] = HALO_RGB[0]; fd[i + 1] = HALO_RGB[1]; fd[i + 2] = HALO_RGB[2]; }
      }
      await sharp(fd, { raw: { width: fi.width, height: fi.height, channels: 4 } })
        .png()
        .toFile(resolve(OUT, `${name}.png`));
    });
  console.log(`  halo ${name}`);
}

const names = process.argv.length > 2
  ? process.argv.slice(2)
  : (await readdir(RAW)).filter((f) => f.endsWith('.png')).map((f) => f.replace('.png', ''));
await mkdir(OUT, { recursive: true });
for (const n of names) await haloOne(n);
console.log('done');
