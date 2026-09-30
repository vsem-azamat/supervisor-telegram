import { i18n } from '@lingui/core';

/** Interface languages we ship. Mirrors the API's `UiLang` enum. */
export const LOCALES = ['ru', 'cs', 'en', 'uk'] as const;

export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = 'ru';

/** Endonyms — a language picker that names languages in English is useless. */
export const LOCALE_NAMES: Record<Locale, string> = {
  ru: 'Русский',
  cs: 'Čeština',
  en: 'English',
  uk: 'Українська',
};

const OVERRIDE_KEY = 'students-cz.locale';
/** What the key was called before the rename. See `readLocaleOverride`. */
const LEGACY_OVERRIDE_KEY = 'konnekt.locale';

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (LOCALES as readonly string[]).includes(value);
}

/**
 * Map an IETF language tag onto a locale we actually ship.
 *
 * Telegram may send a region (`en-US`), so only the primary subtag matters.
 * The legacy bot used `cz` and `ua`, which are not valid tags but do turn up in
 * imported data, so they are mapped rather than rejected.
 */
export function normalizeLocale(tag: string | null | undefined): Locale {
  if (!tag) return DEFAULT_LOCALE;
  const primary = tag.split('-', 1)[0]?.toLowerCase() ?? '';
  const aliased = primary === 'cz' ? 'cs' : primary === 'ua' ? 'uk' : primary;
  return isLocale(aliased) ? aliased : DEFAULT_LOCALE;
}

/** A locale the user picked by hand, which outranks whatever Telegram says. */
export function readLocaleOverride(): Locale | null {
  try {
    const stored = localStorage.getItem(OVERRIDE_KEY);
    if (isLocale(stored)) return stored;

    // Somebody who picked a language before the rename. Without this their
    // choice is silently replaced by whatever Telegram reports, which is
    // exactly the thing picking it by hand was meant to overrule.
    const legacy = localStorage.getItem(LEGACY_OVERRIDE_KEY);
    if (isLocale(legacy)) {
      localStorage.setItem(OVERRIDE_KEY, legacy);
      localStorage.removeItem(LEGACY_OVERRIDE_KEY);
      return legacy;
    }
    return null;
  } catch {
    // Private mode, or storage disabled. Not worth failing a launch over.
    return null;
  }
}

export function writeLocaleOverride(locale: Locale | null): void {
  try {
    if (locale === null) localStorage.removeItem(OVERRIDE_KEY);
    else localStorage.setItem(OVERRIDE_KEY, locale);
  } catch {
    // Ignore — the choice simply will not survive a restart.
  }
}

/**
 * Resolve the locale to launch with.
 *
 * Precedence: an explicit override, then the Telegram user's `language_code`,
 * then the default. The Telegram tag is passed in rather than read here so this
 * module stays independent of the SDK and remains testable.
 */
export function resolveLocale(telegramLanguageCode?: string | null): Locale {
  return readLocaleOverride() ?? normalizeLocale(telegramLanguageCode);
}

/**
 * Load exactly one catalog and activate it.
 *
 * Static `import()` with a template literal is what lets the bundler split each
 * catalog into its own chunk, so a Russian user never downloads the Czech
 * messages.
 */
export async function activateLocale(locale: Locale): Promise<void> {
  const { messages } = await import(`../locales/${locale}/messages.po`);
  i18n.loadAndActivate({ locale, messages });
}

export { i18n };
