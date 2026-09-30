import assert from 'node:assert/strict';
import { test } from 'node:test';

import { consoleSections, statusCounts } from '../src/console/chats.ts';
import type { ConsoleChat } from '../src/console/session.ts';

function chat(id: number, title: string, over: Partial<ConsoleChat> = {}): ConsoleChat {
  return {
    id,
    title,
    resource_status: 'approved',
    member_count: null,
    public_link: null,
    parent_chat_id: null,
    is_captcha_enabled: false,
    is_welcome_enabled: false,
    is_service_cleanup_enabled: false,
    ...over,
  };
}

const CHATS = [
  chat(1, 'ČVUT | ЧВУТ'),
  chat(2, 'ČVUT FIT', { parent_chat_id: 1 }),
  chat(3, 'VŠE FIS 2026', { resource_status: 'discovered' }),
  chat(4, 'Strahov blok 7', { resource_status: 'discovered', parent_chat_id: 1 }),
  chat(5, 'Flood', { resource_status: 'disabled' }),
  chat(6, 'ČVUT FS', { parent_chat_id: 1 }),
];

const titles = (sections: ReturnType<typeof consoleSections>) =>
  sections.map((section) => [section.key, section.title, section.chats.map((c) => c.id)]);

test('chats awaiting review come first, then one section per parent, then the rest', () => {
  assert.deepEqual(titles(consoleSections(CHATS, 'all', '')), [
    ['review', null, [3, 4]],
    ['group', 'ČVUT | ЧВУТ', [1, 2, 6]],
    ['rest', null, [5]],
  ]);
});

test('a status filter keeps only that status, still grouped', () => {
  assert.deepEqual(titles(consoleSections(CHATS, 'approved', '')), [
    ['group', 'ČVUT | ЧВУТ', [1, 2, 6]],
  ]);
  assert.deepEqual(titles(consoleSections(CHATS, 'discovered', '')), [
    ['review', null, [3, 4]],
  ]);
});

test('search finds a title without its diacritics, and an id', () => {
  assert.deepEqual(titles(consoleSections(CHATS, 'all', 'cvut fit')), [
    ['group', 'ČVUT | ЧВУТ', [2]],
  ]);
  assert.deepEqual(titles(consoleSections(CHATS, 'all', '5')), [['rest', null, [5]]]);
});

test('a chat whose parent is not listed goes with the rest', () => {
  const orphans = [chat(7, 'MUNI Law', { parent_chat_id: 99 })];
  assert.deepEqual(titles(consoleSections(orphans, 'all', '')), [['rest', null, [7]]]);
});

test('each status is counted, and all of them together', () => {
  assert.deepEqual(statusCounts(CHATS), {
    all: 6,
    discovered: 2,
    approved: 3,
    disabled: 1,
  });
});
