import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  attention,
  ConsoleError,
  clickRate,
  consoleRequester,
  daysSince,
} from '../src/lib/console.ts';

type Call = { url: string; method: string; body?: string };

/** A fetch that answers from a script, and remembers what it was asked. */
function scripted(answers: Record<string, number[]>) {
  const calls: Call[] = [];
  const fetcher = async (url: string, init: RequestInit = {}) => {
    calls.push({ url, method: init.method ?? 'GET', body: init.body as string });
    const status = answers[url]?.shift() ?? 500;
    return new Response(status === 204 ? null : JSON.stringify({ url }), { status });
  };
  return { calls, fetcher: fetcher as typeof fetch };
}

test('a request without a session signs in with initData, then goes through', async () => {
  const { calls, fetcher } = scripted({
    '/api/stats/home': [401, 200],
    '/api/auth/webapp': [200],
  });
  const get = consoleRequester(fetcher, () => 'user=1&hash=x');

  assert.deepEqual(await get('/api/stats/home'), { url: '/api/stats/home' });
  assert.deepEqual(
    calls.map((c) => `${c.method} ${c.url}`),
    ['GET /api/stats/home', 'POST /api/auth/webapp', 'GET /api/stats/home'],
  );
  assert.deepEqual(JSON.parse(calls[1]?.body ?? '{}'), { init_data: 'user=1&hash=x' });
});

test('a refused sign-in is the answer, not a loop', async () => {
  const { calls, fetcher } = scripted({
    '/api/stats/home': [401],
    '/api/auth/webapp': [403],
  });
  const get = consoleRequester(fetcher, () => 'user=2&hash=x');

  await assert.rejects(get('/api/stats/home'), (error: unknown) => {
    assert.ok(error instanceof ConsoleError);
    assert.equal(error.status, 403);
    return true;
  });
  assert.equal(calls.length, 2);
});

test('without initData there is nothing to sign in with', async () => {
  const { calls, fetcher } = scripted({ '/api/stats/home': [401] });
  const get = consoleRequester(fetcher, () => undefined);

  await assert.rejects(get('/api/stats/home'), ConsoleError);
  assert.equal(calls.length, 1);
});

test('requests that meet a missing session together sign in once', async () => {
  const { calls, fetcher } = scripted({
    '/api/stats/home': [401, 200],
    '/api/chats': [401, 200],
    '/api/auth/webapp': [200],
  });
  const get = consoleRequester(fetcher, () => 'user=1&hash=x');

  await Promise.all([get('/api/stats/home'), get('/api/chats')]);
  assert.equal(calls.filter((c) => c.url === '/api/auth/webapp').length, 1);
});

test('what needs attention is what has a number above zero', () => {
  const items = attention({
    adsToday: 7,
    chats: [
      { resource_status: 'discovered' },
      { resource_status: 'approved' },
      { resource_status: 'discovered' },
    ],
    profilesWeek: 0,
  });
  assert.deepEqual(items, [
    { key: 'ads', count: 7 },
    { key: 'review', count: 2 },
  ]);
});

test('the click rate is a percentage with one decimal, and nothing without views', () => {
  assert.equal(clickRate(1204, 38), '3,2 %');
  assert.equal(clickRate(311, 19), '6,1 %');
  assert.equal(clickRate(0, 0), null);
});

test('days since counts whole days, today being zero', () => {
  const now = new Date('2026-09-30T12:00:00Z');
  assert.equal(daysSince('2026-09-30T01:00:00Z', now), 0);
  assert.equal(daysSince('2026-09-27T13:00:00Z', now), 2);
});
