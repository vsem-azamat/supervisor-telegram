/**
 * Which palette the page wears, and who decides.
 *
 * Three choices, not two. "System" is the honest default — most people never
 * touch this — but it cannot be the only option: a Mini App is opened from
 * inside a client that has a theme of its own, and someone reading in a dark
 * Telegram at midday is entitled to a light catalog. The resolved answer is
 * written to `data-theme` on the root element, which is the only thing
 * `styles/tokens.css` looks at.
 *
 * A module, not a hook. The choice outlives any one screen: the switch is on
 * the profile page, and it has to keep holding while the person is anywhere
 * else. Two things follow — the operating system is watched from here rather
 * than from a component, and the choice is remembered in memory as well as in
 * storage, so a browser that refuses to store it still honours it for the rest
 * of the session instead of snapping back the next time the profile mounts.
 *
 * The same key and the same resolution are duplicated, deliberately, by the
 * inline script in index.html — that copy runs before the first paint, so the
 * page never flashes the wrong palette. Keep the two in step.
 */

export const THEME_CHOICES = ['system', 'light', 'dark'] as const;

export type ThemeChoice = (typeof THEME_CHOICES)[number];

/** What `data-theme` ends up saying: "system" is not a palette. */
export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'students-cz.theme';
/** What the key was called before the rename. Read once, then forgotten.
 *  Delete this and the branch in `readStored` once enough time has passed that
 *  anybody still carrying it has opened the app since. */
const LEGACY_STORAGE_KEY = 'konnekt.theme';
const DARK_QUERY = '(prefers-color-scheme: dark)';

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return (
    typeof value === 'string' && (THEME_CHOICES as readonly string[]).includes(value)
  );
}

function readStored(): ThemeChoice {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isThemeChoice(stored)) return stored;

    // Somebody who chose a theme before the rename. Moving it across is the
    // difference between a rename and everybody's setting quietly resetting to
    // whatever their phone happens to be on.
    const legacy = localStorage.getItem(LEGACY_STORAGE_KEY);
    if (isThemeChoice(legacy)) {
      localStorage.setItem(STORAGE_KEY, legacy);
      localStorage.removeItem(LEGACY_STORAGE_KEY);
      return legacy;
    }
    return 'system';
  } catch {
    // Private mode, or storage disabled. Following the system is a fine
    // answer for someone whose choice we cannot remember across a reload.
    return 'system';
  }
}

function writeStored(choice: ThemeChoice): void {
  try {
    if (choice === 'system') localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, choice);
  } catch {
    // Ignore — `choice` below still holds it for this session.
  }
}

export function systemTheme(): Theme {
  return typeof matchMedia === 'function' && matchMedia(DARK_QUERY).matches
    ? 'dark'
    : 'light';
}

export function resolveTheme(value: ThemeChoice): Theme {
  return value === 'system' ? systemTheme() : value;
}

let choice: ThemeChoice = readStored();
let theme: Theme = resolveTheme(choice);

const listeners = new Set<() => void>();

function apply(): void {
  theme = resolveTheme(choice);
  document.documentElement.dataset.theme = theme;
  for (const listener of listeners) listener();
}

export function getThemeChoice(): ThemeChoice {
  return choice;
}

export function getTheme(): Theme {
  return theme;
}

export function setThemeChoice(next: ThemeChoice): void {
  choice = next;
  writeStored(next);
  apply();
}

/**
 * Called whenever the palette changes, for anything outside React that has to
 * keep up — Telegram's own chrome does not read our stylesheet.
 */
export function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// Follow the operating system for as long as nobody has overridden it. Set up
// once, at import: a phone that switches to dark at sunset does it while the
// app is open, and on whatever screen the person happens to be looking at.
if (typeof matchMedia === 'function') {
  matchMedia(DARK_QUERY).addEventListener('change', () => {
    if (choice === 'system') apply();
  });
}

// The inline script in index.html has already written the attribute; doing it
// again here costs nothing and makes this module's state and the document
// agree even if that script never ran.
apply();
