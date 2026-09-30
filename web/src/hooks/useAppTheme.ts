import { useSyncExternalStore } from 'react';

import {
  getTheme,
  getThemeChoice,
  setThemeChoice,
  subscribeTheme,
  type Theme,
  type ThemeChoice,
} from '@/lib/theme';

export interface AppTheme {
  /** What the person chose: system, light or dark. */
  choice: ThemeChoice;
  /** What that resolves to right now. */
  theme: Theme;
  set: (choice: ThemeChoice) => void;
}

/**
 * The palette, and the control over it.
 *
 * A thin view onto `lib/theme.ts`, which owns the choice and applies it. That
 * is the whole point of `useSyncExternalStore` here: the state has to survive
 * the profile screen unmounting, and every reader has to see the same value —
 * two components each holding their own copy would disagree the moment one of
 * them changed it.
 */
export function useAppTheme(): AppTheme {
  const choice = useSyncExternalStore(subscribeTheme, getThemeChoice, getThemeChoice);
  const theme = useSyncExternalStore(subscribeTheme, getTheme, getTheme);
  return { choice, theme, set: setThemeChoice };
}
