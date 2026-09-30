import assert from 'node:assert/strict';
import { test } from 'node:test';

import { cardBody, cardProblems, EMPTY_CARD } from '../src/console/partners.ts';

const GOOD = {
  ...EMPTY_CARD,
  partner: 'Pojišťovna VZP',
  url: 'https://example.test/vzp',
  title: 'Страховка для студентов',
};

test('a card with a name, an https link and a title is ready', () => {
  assert.deepEqual(cardProblems(GOOD), []);
});

test('an empty form says everything that is missing', () => {
  assert.deepEqual(cardProblems(EMPTY_CARD), ['partner', 'url', 'title']);
});

test('a link must be https and have nothing blank in it', () => {
  for (const url of [
    'http://example.test',
    'javascript:alert(1)',
    'https://exa mple.test',
    'https://',
  ]) {
    assert.deepEqual(cardProblems({ ...GOOD, url }), ['url'], url);
  }
});

test('a monogram is four letters at most', () => {
  assert.deepEqual(cardProblems({ ...GOOD, logo_text: 'VZPCZ' }), ['logo_text']);
  assert.deepEqual(cardProblems({ ...GOOD, logo_text: 'VZP' }), []);
});

test('the body is trimmed, and an empty optional field is null', () => {
  assert.deepEqual(
    cardBody({ ...GOOD, partner: '  VZP ', subtitle: '  ', logo_text: 'vzp' }),
    {
      partner: 'VZP',
      url: 'https://example.test/vzp',
      title: 'Страховка для студентов',
      subtitle: null,
      price_text: null,
      context_note: null,
      logo_text: 'VZP',
    },
  );
});

test("every field keeps to the catalog's length, a pasted one included", () => {
  assert.deepEqual(cardProblems({ ...GOOD, title: 'x'.repeat(201) }), ['title']);
  assert.deepEqual(cardProblems({ ...GOOD, url: `https://a.test/${'x'.repeat(1024)}` }), [
    'url',
  ]);
  assert.deepEqual(cardProblems({ ...GOOD, price_text: 'x'.repeat(65) }), ['price_text']);
  assert.deepEqual(cardProblems({ ...GOOD, context_note: 'x'.repeat(600) }), []);
});

test('the monogram is measured as it is sent, upper-cased', () => {
  assert.deepEqual(cardProblems({ ...GOOD, logo_text: 'ßßß' }), ['logo_text']);
});
