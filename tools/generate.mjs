// mashpad raccoon art — batch generator.
// Same model, STYLE contract, and style-refs as boxofraccoons-website
// scripts/generate-images.mjs (brand match is the whole point).
// Usage: node generate.mjs [jobname ...]

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const SITE = 'C:/Users/hardy/code/boxofraccoons-website';
const OUT_DIR = resolve('./raw');

const MODEL = 'gemini-2.5-flash-image';
const ENDPOINT = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`;

// STYLE — verbatim from the website's generate-images.mjs (do not drift).
const STYLE = `Match EXACTLY the art style of the attached reference images: a cute \
flat-vector sticker illustration of a friendly cartoon raccoon. Soft rounded body shapes; \
thin, clean dark outlines (NOT heavy black); soft MEDIUM NEUTRAL-GREY fur (a calm desaturated grey \
matching the reference exactly — NOT brown, NOT warm, NOT dark) with a dark charcoal bandit mask \
across the eyes, a pale cream muzzle and belly, small rounded ears with a cream inner-ear; the eyes \
are just TWO SMALL SOLID-BLACK DOTS sitting inside the dark mask, exactly like the reference — NO \
large white eye-patches, NO white rings around the eyes, NO big round glossy anime eyes; a small \
dark nose; gentle soft cel-shading (no harsh gradients). A wholesome, friendly, approachable \
expression. Muted, cozy colour palette — calm neutral greys, cream, and soft sage-green / teal \
accents. Sticker aesthetic. Plain solid PURE-WHITE \
background everywhere for a clean cut-out. No text, no drop shadows, no border, no frame.`;

// Every prop keeps the brand palette: soft sage-teal (#6cb49c), cream, warm tan wood.
const SOLO = `SCENE: a SINGLE cute raccoon`;
const TAIL = `Square composition, the raccoon large and centered filling most of the frame, \
simple bold shapes that stay readable when shrunk small, plain solid white background.`;

const EYES = "CRITICAL EYE RULE: the eyes are TWO SMALL SOLID-BLACK DOTS placed symmetrically INSIDE the dark charcoal bandit-mask patches (one dot centered in each mask patch), with the pale cream brow band above the mask — the dots NEVER sit outside the mask or on bare grey/cream fur. Copy the eye treatment of the attached references exactly. ";
const REFS = ['assets/style-refs/family-desk.png', 'assets/style-refs/family-standing.png'];

const JOBS = [
  { name: 'wave', prompt: `${SOLO} standing and waving hello with one raised paw, warm happy smile. ${TAIL}` },
  { name: 'heart', prompt: `${SOLO} hugging a BIG soft plush heart to its chest with both paws, eyes closed in a content smile; the heart is a soft muted TEAL (#6cb49c) with a cream highlight. ${TAIL}` },
  { name: 'bubbles', prompt: `${SOLO} joyfully blowing soap bubbles through a small teal bubble wand, several round translucent bubbles floating up; delighted expression. ${TAIL}` },
  { name: 'blocks', prompt: `${SOLO} sitting and happily stacking a small tower of toy building blocks; the blocks alternate soft muted TEAL (#6cb49c), cream, and warm tan — no bright primary colors. ${TAIL}` },
  { name: 'balloon', prompt: `${SOLO} standing and holding the string of one round soft muted TEAL (#6cb49c) balloon floating above it, looking up at it happily. ${TAIL}` },
  { name: 'peekaboo', prompt: `${SOLO} playing peekaboo — both paws over its eyes, big playful open-mouth grin peeking below the paws, ears perked. ${TAIL}` },
  { name: 'drum', prompt: `${SOLO} sitting behind a toy drum and happily banging it with two small drumsticks; the drum shell is soft muted TEAL (#6cb49c) with a cream drumhead and tan rim. ${TAIL}` },
  { name: 'teddy', prompt: `${SOLO} standing and cuddling a small warm-tan teddy bear against its cheek, eyes closed, cozy content smile. ${TAIL}` },
  { name: 'crayons', prompt: `${SOLO} lying on its tummy drawing on a sheet of cream paper with a crayon; a few crayons beside it in muted teal, sage, and tan; happy focused expression. ${TAIL}` },
  { name: 'sandwich', prompt: `${SOLO} holding a sandwich with both paws and taking a big happy bite; the sandwich has cream bread and simple muted fillings; crumbs optional, cheeks slightly puffed. ${TAIL}` },
  { name: 'water', prompt: `${EYES}${SOLO} drinking from a clear glass of water held in both paws, eyes peeking over the rim, content expression. ${TAIL}` },
  { name: 'book', prompt: `${EYES}Each black dot eye has ONE tiny white catchlight glint in its upper part, exactly like the reference eyes. ${SOLO} sitting cross-legged reading an open book with a soft muted TEAL (#6cb49c) cover, looking down at the pages with a gentle absorbed smile. ${TAIL}` },
  { name: 'sleep', prompt: `${SOLO} curled up fast asleep, eyes closed with a peaceful little smile, tail wrapped around itself like a crescent, two small "z" sleep marks floating above. IMPORTANT: soft ROUNDED ears with pale cream inner-ear, never pointed or cat-like. ${TAIL}` },
];

function part(bytes, mime = 'image/png') {
  return { inline_data: { mime_type: mime, data: bytes.toString('base64') } };
}

async function runJob(job, key) {
  const parts = [];
  for (const ref of REFS) parts.push(part(await readFile(resolve(SITE, ref))));
  parts.push({ text: `${STYLE} ${job.prompt}` });

  const res = await fetch(ENDPOINT, {
    method: 'POST',
    headers: { 'x-goog-api-key': key, 'Content-Type': 'application/json' },
    body: JSON.stringify({ contents: [{ parts }] }),
  });
  if (!res.ok) throw new Error(`Gemini API ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const data = await res.json();
  const images = (data.candidates?.[0]?.content?.parts ?? []).filter((p) => p.inline_data ?? p.inlineData);
  if (!images.length) throw new Error(`no image (finishReason: ${data.candidates?.[0]?.finishReason})`);
  const inline = images[0].inline_data ?? images[0].inlineData;
  const out = resolve(OUT_DIR, `${job.name}.png`);
  await writeFile(out, Buffer.from(inline.data, 'base64'));
  console.log(`  ok ${job.name}`);
}

async function main() {
  const envText = await readFile(resolve(SITE, '.env'), 'utf8');
  const key = envText.match(/GEMINI_API_KEY=(\S+)/)?.[1];
  if (!key) throw new Error('GEMINI_API_KEY not found in website .env');
  await mkdir(OUT_DIR, { recursive: true });

  const requested = process.argv.slice(2);
  const jobs = requested.length ? JOBS.filter((j) => requested.includes(j.name)) : JOBS;
  let failed = 0;
  for (const job of jobs) {
    if (!requested.length && existsSync(resolve(OUT_DIR, `${job.name}.png`))) {
      console.log(`  skip ${job.name} (exists)`);
      continue;
    }
    try {
      await runJob(job, key);
    } catch (err) {
      failed++;
      console.error(`  FAIL ${job.name}: ${err.message}`);
    }
  }
  console.log(`done, ${failed} failed`);
  if (failed) process.exit(1);
}

main();
