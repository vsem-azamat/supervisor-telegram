import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';

/**
 * The product is Konnekt: the chats and the help are one app now, and the old
 * name on a screen, in the tab title or in a first message says otherwise.
 * Storage keys are not a name anybody reads, and keep theirs.
 */

const OLD_NAME = /Students\s*(<[^>]*>\s*)?CZ/;

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return entry === 'generated' ? [] : sources(path);
    return /\.(tsx?|po)$/.test(entry) ? [path] : [];
  });
}

test('no screen, catalog or first message says the old name', () => {
  const found = sources('src').filter((path) =>
    OLD_NAME.test(readFileSync(path, 'utf8')),
  );
  assert.deepEqual(found, []);
});

test('the tab title says Konnekt', () => {
  const html = readFileSync('index.html', 'utf8');
  assert.match(html, /<title>Konnekt\b/);
  assert.doesNotMatch(html, OLD_NAME);
});
