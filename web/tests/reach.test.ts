import assert from 'node:assert/strict';
import { test } from 'node:test';

import { isReach, type Reach, reachFigures } from '../src/lib/reach.ts';

function reach(over: Partial<Reach> = {}): Reach {
  return {
    chats: 19,
    members: 10748,
    measured_chats: 19,
    groups: [
      { name: 'ČVUT | ЧВУТ', chats: 8, members: 2900 },
      { name: 'VŠE', chats: 1, members: 0 },
    ],
    ...over,
  };
}

test('members are stated plainly when every chat was measured', () => {
  assert.deepEqual(reachFigures(reach()).members, { value: 10748, approximate: false });
});

test('members carry ≈ when only some chats were measured', () => {
  assert.deepEqual(reachFigures(reach({ measured_chats: 12 })).members, {
    value: 10748,
    approximate: true,
  });
});

test('members are left out when nothing was measured', () => {
  assert.equal(reachFigures(reach({ measured_chats: 0, members: 0 })).members, null);
});

test('a group with no measured members shows no count, not zero', () => {
  const [cvut, vse] = reachFigures(reach()).groups;
  assert.equal(cvut?.members, 2900);
  assert.equal(vse?.members, null);
});

test('a group list with nothing measured shows no member column at all', () => {
  const figures = reachFigures(reach({ measured_chats: 0, members: 0 }));
  assert.ok(figures.groups.every((group) => group.members === null));
});

test('a reach of the wrong shape is refused at the boundary', async () => {
  assert.equal(isReach(reach()), true);
  const { measured_chats: _, ...missing } = reach();
  assert.equal(isReach(missing), false);
  assert.equal(
    isReach({ ...reach(), groups: [{ name: 'x', chats: 1, members: '5' }] }),
    false,
  );
  assert.equal(isReach({ ...reach(), groups: [null] }), false);
  assert.equal(isReach('<html>'), false);
});

test('a partial measurement says how many chats it covers', () => {
  assert.deepEqual(reachFigures(reach({ measured_chats: 12 })).coverage, {
    measured: 12,
    of: 19,
  });
  assert.equal(reachFigures(reach()).coverage, null);
});
