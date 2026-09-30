/*
 * The tests, and a check that there were any.
 *
 * `node --test "tests/**\/*.test.ts"` exits 0 reporting "tests 0" when the
 * pattern matches nothing, so a renamed directory would leave `pnpm test`,
 * `make check` and CI green with nothing executed — the same failure the
 * contract check guards against, and the same fix: look at the input before
 * trusting the exit code.
 */

import { spawnSync } from 'node:child_process';
import { globSync } from 'node:fs';

const files = globSync('tests/**/*.test.ts').sort();
if (files.length === 0) {
  console.error('No test files under apps/web/tests. Nothing ran.');
  process.exit(1);
}

const { status } = spawnSync(process.execPath, ['--test', ...files], {
  stdio: 'inherit',
});
process.exit(status ?? 1);
