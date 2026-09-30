import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  localHeatmap,
  memberTrend,
  parentChoices,
  personName,
} from '../src/console/activity.ts';
import type { ConsoleChat } from '../src/console/session.ts';

test('the heatmap is read in local time, so a Prague evening is not UTC afternoon', () => {
  // Monday 18:00 UTC is Monday 20:00 in Prague summer time.
  const { grid, max } = localHeatmap([{ weekday: 0, hour: 18, count: 5 }], 120);
  assert.equal(grid[0]?.[20], 5);
  assert.equal(grid[0]?.[18], 0);
  assert.equal(max, 5);
});

test('an hour pushed past Sunday midnight lands on Monday', () => {
  const { grid } = localHeatmap([{ weekday: 6, hour: 23, count: 2 }], 120);
  assert.equal(grid[0]?.[1], 2);
});

test('west of Greenwich an early Monday hour goes back to Sunday', () => {
  const { grid } = localHeatmap([{ weekday: 0, hour: 1, count: 3 }], -300);
  assert.equal(grid[6]?.[20], 3);
});

test('an empty week has nothing to scale by', () => {
  const { grid, max } = localHeatmap([], 0);
  assert.equal(max, 0);
  assert.equal(grid.length, 7);
  assert.ok(grid.every((day) => day.length === 24 && day.every((n) => n === 0)));
});

test('a trend needs two counts, and says how far it moved', () => {
  assert.equal(
    memberTrend([{ captured_at: '2026-09-01T00:00:00', member_count: 10 }]),
    null,
  );
  const trend = memberTrend([
    { captured_at: '2026-09-01T00:00:00', member_count: 100 },
    { captured_at: '2026-09-02T00:00:00', member_count: 120 },
    { captured_at: '2026-09-03T00:00:00', member_count: 110 },
  ]);
  assert.ok(trend);
  assert.equal(trend.change, 10);
  assert.equal(trend.first, 100);
  assert.equal(trend.last, 110);
  // Lowest count at the bottom edge, highest at the top.
  assert.equal(trend.points, '0,32 50,0 100,16');
});

test('a flat trend is drawn through the middle, not along an edge', () => {
  const trend = memberTrend([
    { captured_at: '2026-09-01T00:00:00', member_count: 50 },
    { captured_at: '2026-09-02T00:00:00', member_count: 50 },
  ]);
  assert.equal(trend?.points, '0,16 100,16');
});

function chat(id: number, title: string, parent: number | null = null): ConsoleChat {
  return {
    id,
    title,
    resource_status: 'approved',
    member_count: null,
    public_link: null,
    parent_chat_id: parent,
    is_captcha_enabled: false,
    is_welcome_enabled: false,
    is_service_cleanup_enabled: false,
  };
}

test('a chat goes under a top-level chat, never under itself or a child', () => {
  const chats = [
    chat(1, 'ČVUT'),
    chat(2, 'ČVUT FIT', 1),
    chat(3, 'VŠE'),
    chat(4, 'Flood'),
    chat(5, 'Anglická', null),
  ];
  assert.deepEqual(
    parentChoices(chats, 4).map((c) => c.id),
    [5, 1, 3],
  );
  // A child is never offered: the list groups one level deep.
  assert.ok(!parentChoices(chats, 3).some((c) => c.id === 2));
});

test('a chat others sit under cannot go under anything', () => {
  const chats = [chat(1, 'ČVUT'), chat(2, 'ČVUT FIT', 1), chat(3, 'VŠE')];
  assert.deepEqual(parentChoices(chats, 1), []);
});

test('a person is their name, else their handle, else their id', () => {
  assert.equal(
    personName({ user_id: 7, first_name: 'Jan', last_name: 'N.', username: 'jan' }),
    'Jan N.',
  );
  assert.equal(
    personName({ user_id: 7, first_name: null, last_name: null, username: 'jan' }),
    '@jan',
  );
  assert.equal(
    personName({ user_id: 7, first_name: null, last_name: null, username: null }),
    '7',
  );
});
