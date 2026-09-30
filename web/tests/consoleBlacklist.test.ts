import assert from 'node:assert/strict';
import { test } from 'node:test';

import { blockedName, searchBlocked } from '../src/console/blacklist.ts';
import type { BlockedUser } from '../src/console/session.ts';

function user(id: number, over: Partial<BlockedUser> = {}): BlockedUser {
  return {
    user_id: id,
    username: null,
    first_name: null,
    last_name: null,
    changed_at: '2026-09-01T00:00:00',
    ...over,
  };
}

test('a name is the one Telegram gave, else the handle, else the id', () => {
  assert.equal(blockedName(user(1, { first_name: 'Ivan', last_name: 'P.' })), 'Ivan P.');
  assert.equal(blockedName(user(1, { username: 'spam_bot' })), '@spam_bot');
  assert.equal(blockedName(user(5512398877)), '5512398877');
});

test('search finds a name, a handle with or without @, and an id', () => {
  const rows = [
    user(1, { first_name: 'Ivan' }),
    user(2, { username: 'casino_ads' }),
    user(5512398877),
  ];
  const ids = (q: string) => searchBlocked(rows, q).map((row) => row.user_id);
  assert.deepEqual(ids('ivan'), [1]);
  assert.deepEqual(ids('@casino'), [2]);
  assert.deepEqual(ids('casino'), [2]);
  assert.deepEqual(ids('55123'), [5512398877]);
  assert.deepEqual(ids(''), [1, 2, 5512398877]);
});
