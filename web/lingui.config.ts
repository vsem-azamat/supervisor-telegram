import { defineConfig } from '@lingui/cli';
import type { LinguiConfig } from '@lingui/conf';
import { formatter } from '@lingui/format-po';

/**
 * Four interface languages, matching the `UiLang` enum on the API side.
 *
 * Only chrome lives here. Names of subjects, faculties and service types are
 * translated in the database and arrive from the API already localised, so they
 * must never end up in these catalogs.
 */
const config: LinguiConfig = defineConfig({
  sourceLocale: 'ru',
  locales: ['ru', 'cs', 'en', 'uk'],
  catalogs: [
    {
      path: '<rootDir>/src/locales/{locale}/messages',
      include: ['<rootDir>/src'],
      exclude: ['**/node_modules/**', '**/locales/**'],
    },
  ],
  // Line numbers churn on every unrelated edit and make catalog diffs
  // unreadable; the file path alone is enough context for a translator.
  format: formatter({ lineNumbers: false }),
  compileNamespace: 'ts',
  orderBy: 'messageId',
});

export default config;
