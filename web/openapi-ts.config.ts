import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { defineConfig } from '@hey-api/openapi-ts';

/**
 * Generates a typed client from the catalog API's OpenAPI document.
 *
 * The document is `catalog-openapi.json`, committed beside this file: the
 * catalog API lives in another repository (teachers-catalog, where it is
 * `apps/api/openapi.json`), and a committed copy is what makes this check
 * deterministic. `.github/workflows/catalog-contract.yml` compares the copy
 * with the catalog's own; when they differ, copy the new one over and run
 * `pnpm api:generate`.
 *
 * An absolute path, and never a URL: given a URL, or a path the generator
 * takes for one, it writes it into the client as a literal
 * `ClientOptions.baseUrl`, and the client carries whichever machine made it.
 *
 * Not wired into `pnpm build`. Everything the generator has not covered yet
 * is hand-written in `src/lib/types.ts`.
 */
const input = fileURLToPath(new URL('./catalog-openapi.json', import.meta.url));

// openapi-ts exits 0 without writing anything when its input is missing or
// empty, and a generator that quietly did nothing leaves a stale client
// looking identical to itself.
if (!readFileSync(input, 'utf8').includes('"openapi"')) {
  throw new Error(`${input} is not an OpenAPI document.`);
}

export default defineConfig({
  input,
  // Biome is excluded from the generated directory, so leave formatting and
  // linting to it rather than having the generator shell out to a second tool.
  output: './src/lib/generated',
  plugins: ['@hey-api/typescript'],
});
