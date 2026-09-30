import { mockTelegramEnv } from '@tma.js/sdk-react';

/**
 * Pretend to be Telegram when we are not.
 *
 * Opening the app in a desktop browser gives no launch parameters, so the SDK
 * cannot initialise and every screen dies before it renders. This substitutes a
 * plausible environment so the interface can be worked on in a normal browser
 * with normal devtools.
 *
 * Two things this is not:
 *
 * - It is not a way to skip authentication. The init data below is unsigned
 *   nonsense, so the API will reject it with 401. That is correct — to exercise
 *   real endpoints, open the app through Telegram, or point the API at a
 *   development bot token and paste real init data into `VITE_MOCK_INIT_DATA`.
 * - It is not shipped. This module is imported only under `import.meta.env.DEV`
 *   and is tree-shaken out of the production bundle.
 */

const MOCK_USER = {
  id: 1,
  first_name: 'Dev',
  last_name: 'User',
  username: 'devuser',
  // Drives the initial interface language. Change it to check the other three.
  language_code: 'ru',
  is_premium: false,
  allows_write_to_pm: true,
};

/**
 * Init data as the raw query string Telegram sends. It has to be raw: the SDK
 * hands this exact string to the API in the `Authorization: tma` header, and
 * re-serializing a parsed object would change the byte order the signature
 * covers.
 */
function buildInitData(): string {
  const params = new URLSearchParams({
    user: JSON.stringify(MOCK_USER),
    auth_date: Math.floor(Date.now() / 1000).toString(),
    // Both are structurally required by the parser. Neither will verify.
    hash: '0'.repeat(64),
    signature: 'mock-signature',
  });
  return params.toString();
}

/**
 * Is there a real Telegram client on the other side of this page?
 *
 * Not `isTMA()`: that returns true once launch parameters exist anywhere,
 * including the ones this module wrote into session storage a moment ago. On a
 * reload it therefore reported "already in Telegram", the mock was skipped, and
 * the SDK threw UnknownEnvError because the window-level bridge — which does
 * not survive a navigation — was gone. The question that actually matters is
 * whether the bridge is present right now.
 */
function insideRealTelegram(): boolean {
  const w = window as unknown as { TelegramWebviewProxy?: unknown };
  return Boolean(w.TelegramWebviewProxy) || window.parent !== window;
}

export function mockEnv(): void {
  if (insideRealTelegram()) return;

  const initDataRaw = import.meta.env.VITE_MOCK_INIT_DATA || buildInitData();

  mockTelegramEnv({
    launchParams: {
      tgWebAppData: initDataRaw,
      tgWebAppPlatform: 'tdesktop',
      tgWebAppVersion: '9.0',
      tgWebAppThemeParams: {
        accent_text_color: '#6ab2f2',
        bg_color: '#17212b',
        button_color: '#5288c1',
        button_text_color: '#ffffff',
        destructive_text_color: '#ec3942',
        header_bg_color: '#17212b',
        hint_color: '#708499',
        link_color: '#6ab3f3',
        secondary_bg_color: '#232e3c',
        section_bg_color: '#17212b',
        section_header_text_color: '#6ab3f3',
        subtitle_text_color: '#708499',
        text_color: '#f5f5f5',
      },
    },
  });

  console.info(
    '[mockEnv] Telegram environment mocked. Init data is unsigned, so the API ' +
      'will answer 401 — open the app through Telegram for authenticated calls.',
  );
}
