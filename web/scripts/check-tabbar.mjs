/*
 * The tab bar must not show what is passing under it.
 *
 * The contract is in catalog/docs/architecture.md: anything pinned to an edge is
 * fixed, and a fixed bar is opaque behind its own controls. The bug this
 * guards against is not a layout one — nothing overflows, nothing overlaps
 * wrongly, and every element is exactly where it was put. It is that the bar's
 * background reached full opacity over only part of its height while its
 * contents were centred over all of it, so the top of every icon was painted
 * onto whatever card happened to be sliding underneath.
 *
 * Which is why this is measured photographically rather than geometrically.
 * There is no number in the DOM for "how much of this gradient is see-through
 * where the icons are": the paint is the answer, so the paint is what gets
 * compared. Take the bar's picture with the list at the top, move the list
 * under it, take it again. A bar that is opaque behind its controls cannot be
 * changed by what passes beneath it; one that is not changes in exactly the
 * places where it is see-through.
 *
 * A fade above the bar is not what this forbids and not what it sees: the
 * crop is the bar's own border box, and a `::before` placed above it falls
 * outside that box.
 *
 * Needs the same running stack as check-scroll.mjs — see scripts/lib/stack.mjs
 * for what it checks before measuring anything. Where `pnpm dev` cannot have
 * sudo for mkcert, run it with VITE_NO_HTTPS=1 and pass
 * BASE=http://localhost:5173.
 */

import { chromium } from 'playwright';

import { BASE, phoneContext, preflight, VIEWPORTS } from './lib/stack.mjs';

/** The screens that carry the bar and have something long enough to move. */
const ROUTES = ['/', '/results', '/chats'];

/** How far to push the list. Further than the bar is tall, so a whole new row
 *  of content passes behind it rather than the same one shifting slightly. */
const TRAVEL = 220;

const browser = await chromium.launch();
const failures = [];
/** A screen that should carry the bar and did not: a broken check. */
const broken = [];
/** A list that had nowhere to go — a thin database, not a see-through bar. */
const unmoved = [];
/** Which routes were photographed at least once, so a route that was never
 *  measured at any size cannot pass as a clean one. */
const measured = new Set();
/** How many pictures were actually taken, so the summary claims the coverage
 *  it has rather than the coverage it set out for. */
let photographs = 0;

/** Move the list, and say whether it actually moved. #root is the scroller —
 *  the document scrolls nowhere; see the note on it in index.css. */
async function scrollUnder(page) {
  return page.evaluate((travel) => {
    const root = document.getElementById('root');
    if (!root) return 0;
    const before = root.scrollTop;
    root.scrollTop = before + travel;
    return root.scrollTop - before;
  }, TRAVEL);
}

/**
 * How the two pictures of the same bar differ: how many pixels, and how wide
 * the bar was when they were taken.
 *
 * Decoded in the browser that took them, because comparing the PNG bytes is
 * not comparing pixels: two pictures that differ anywhere compress to
 * different lengths, so the byte count answers "different" and never "by how
 * much" — and everything below depends on how much.
 */
async function comparePictures(page, before, after) {
  return page.evaluate(
    async ([first, second]) => {
      const decode = async (base64) => {
        const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
        const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
        const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
        const ctx = canvas.getContext('2d');
        ctx.drawImage(bitmap, 0, 0);
        return ctx.getImageData(0, 0, bitmap.width, bitmap.height);
      };

      const [a, b] = await Promise.all([decode(first), decode(second)]);
      if (a.width !== b.width || a.height !== b.height) {
        return { resized: true, width: a.width, differing: 0 };
      }

      let differing = 0;
      for (let at = 0; at < a.data.length; at += 4) {
        if (
          a.data[at] !== b.data[at] ||
          a.data[at + 1] !== b.data[at + 1] ||
          a.data[at + 2] !== b.data[at + 2] ||
          a.data[at + 3] !== b.data[at + 3]
        ) {
          differing += 1;
        }
      }
      return { resized: false, width: a.width, differing };
    },
    [before.toString('base64'), after.toString('base64')],
  );
}

await preflight(browser);

for (const viewport of VIEWPORTS) {
  const size = `${viewport.width}x${viewport.height}`;
  const context = await phoneContext(browser, viewport);
  const page = await context.newPage();

  for (const path of ROUTES) {
    const where = `${path} at ${size}`;
    // Caught rather than left to the top level: an unhandled rejection here
    // exits 1, which is the code this script keeps for "the bar is
    // see-through" — so a dev server that died mid-run would report as a bar
    // defect, and take the browser down with it unclosed.
    try {
      await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' });
    } catch (error) {
      console.error(`Cannot reach ${BASE}${path}: ${error.message}`);
      await browser.close();
      process.exit(2);
    }
    await page.waitForTimeout(900);

    const bar = page.locator('nav[class*="tabs"]').first();
    if ((await bar.count()) === 0) {
      broken.push(`${where}: this screen carries no tab bar`);
      continue;
    }

    const still = await bar.screenshot();
    const travelled = await scrollUnder(page);
    if (travelled < TRAVEL) {
      unmoved.push(
        `${where}: the list moved ${travelled}px of ${TRAVEL}, so nothing passed behind the bar`,
      );
      continue;
    }
    await page.waitForTimeout(400);
    const moved = await bar.screenshot();

    const { resized, width, differing } = await comparePictures(page, still, moved);
    measured.add(path);
    photographs += 1;

    if (resized) {
      failures.push(
        `${where}: the bar changed size while the list moved under it — ` +
          'that is a layout defect, not a see-through one',
      );
      continue;
    }

    // One row of the crop, and not a pixel more. An opaque bar owes an exact
    // answer: nothing beneath it reaches the picture, so the honest
    // expectation is zero. The allowance is for the boundary alone — the bar's
    // height carries the home indicator's inset, which on a real phone is
    // fractional, so the crop can end mid device-pixel and take a blended row
    // of the fade that sits above it. A bar that is actually see-through
    // differs over the whole band where it is, which is many rows.
    if (differing > width) {
      failures.push(
        `${where}: the bar changed when the list moved under it ` +
          `(${differing} pixels of it differ, ${width} to a row) — ` +
          'something is showing through it',
      );
    }
  }

  await context.close();
}

await browser.close();

for (const line of unmoved) console.warn(`unmoved     ${line}`);
for (const line of broken) console.error(`broken      ${line}`);
for (const line of failures) console.error(`see-through ${line}`);

const never = ROUTES.filter((path) => !measured.has(path));
for (const path of never) {
  console.error(`unmeasured  ${path} was never photographed, at any size`);
}

if (broken.length || never.length) {
  console.error(
    'A check that reports an unmeasured screen as a clean one is not a check.',
  );
  process.exit(2);
}
if (failures.length) process.exit(1);
console.log(
  `tab bar opaque in ${photographs} of ${ROUTES.length * VIEWPORTS.length} screen-and-size pairs`,
);
