/**
 * The moderator console's plumbing, apart from the screens that draw it.
 *
 * The console reads two backends. The catalog's `/api/v1/admin/*` takes the
 * same initData as every other catalog call. This repository's webapi keeps a
 * session instead: a cookie opened by `POST /api/auth/webapp` with the signed
 * initData, for super admins only. `consoleRequester` opens that session when
 * a request meets its absence, once, and never retries a refusal.
 */

/**
 * Why a console request failed, which decides what the screen says:
 * - `refused`: signed in, and webapi said this account is not a super admin;
 * - `stale`: no initData, or one webapi no longer accepts (it takes an hour's
 *   worth); reopening the app gives a fresh one;
 * - `not-kept`: signed in, and the next request still had no session, so the
 *   cookie was not kept (Telegram Web's iframe, for one); signing in again
 *   would only add sessions;
 * - `failed`: anything else, which may pass on another try.
 */
export type ConsoleFailureReason = 'refused' | 'stale' | 'not-kept' | 'failed';

export class ConsoleError extends Error {
  readonly status: number;
  readonly reason: ConsoleFailureReason;

  constructor(status: number, reason: ConsoleFailureReason = 'failed') {
    super(`console request failed: ${status} (${reason})`);
    this.name = 'ConsoleError';
    this.status = status;
    this.reason = reason;
  }
}

/**
 * Whether trying again can change the answer: not for the reasons above, and
 * not for a request the server understood and refused (a 404, a 422).
 */
export function isFinal(error: unknown): boolean {
  if (!(error instanceof ConsoleError)) return false;
  return error.reason !== 'failed' || error.status < 500;
}

export type ConsoleGet = <T>(path: string, init?: RequestInit) => Promise<T>;

/**
 * A requester for webapi's session endpoints. The fetch and the initData are
 * passed in: `api.ts` builds the real one, the tests a scripted one.
 */
export function consoleRequester(
  fetcher: typeof fetch,
  initData: () => string | undefined,
): ConsoleGet {
  // Shared by whatever requests meet the missing session at the same time:
  // one sign-in, not one per screen tile.
  let signingIn: Promise<void> | null = null;
  // Once a session was opened and not kept, opening more cannot help.
  let notKept = false;

  const signIn = async () => {
    const raw = initData();
    if (!raw) throw new ConsoleError(401, 'stale');
    const response = await fetcher('/api/auth/webapp', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ init_data: raw }),
    });
    if (response.status === 401) throw new ConsoleError(401, 'stale');
    if (response.status === 403) throw new ConsoleError(403, 'refused');
    if (!response.ok) throw new ConsoleError(response.status);
  };

  const send = (path: string, init: RequestInit) =>
    fetcher(path, {
      ...init,
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      },
    });

  return async <T>(path: string, init: RequestInit = {}): Promise<T> => {
    let response = await send(path, init);
    if (response.status === 401) {
      if (notKept) throw new ConsoleError(401, 'not-kept');
      signingIn ??= signIn().finally(() => {
        signingIn = null;
      });
      await signingIn;
      response = await send(path, init);
      if (response.status === 401) {
        notKept = true;
        throw new ConsoleError(401, 'not-kept');
      }
    }
    if (!response.ok) throw new ConsoleError(response.status);
    return (response.status === 204 ? undefined : await response.json()) as T;
  };
}

// ── webapi's shapes, as far as the console reads them ─────────────────────

export type ChatStatus = 'discovered' | 'approved' | 'disabled';

export interface ConsoleChat {
  id: number;
  title: string | null;
  resource_status: ChatStatus;
  member_count: number | null;
  public_link: string | null;
  parent_chat_id: number | null;
  is_captcha_enabled: boolean;
  is_welcome_enabled: boolean;
  is_service_cleanup_enabled: boolean;
}

export interface ChatSender {
  user_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  message_count: number;
  last_seen: string;
  blocked: boolean;
}

export interface ConsoleChatDetail extends ConsoleChat {
  welcome_message: string | null;
  recent_senders: ChatSender[];
}

/** The fields the console changes on a chat; only the ones sent are applied. */
export type ChatUpdate = Partial<
  Pick<
    ConsoleChatDetail,
    | 'resource_status'
    | 'is_captcha_enabled'
    | 'is_welcome_enabled'
    | 'is_service_cleanup_enabled'
    | 'welcome_message'
  > & { public_link: string }
>;

export interface HomeStats {
  spam_pings: { count_24h: number; count_7d: number };
}

// ── what the summary says ─────────────────────────────────────────────────

export type AttentionKey = 'ads' | 'review' | 'profiles';

/** What needs a look, in the order the summary lists it; zero is not news. */
export function attention(input: {
  adsToday: number;
  chats: Pick<ConsoleChat, 'resource_status'>[];
  profilesWeek: number;
}): { key: AttentionKey; count: number }[] {
  const items: { key: AttentionKey; count: number }[] = [
    { key: 'ads', count: input.adsToday },
    {
      key: 'review',
      count: input.chats.filter((chat) => chat.resource_status === 'discovered').length,
    },
    { key: 'profiles', count: input.profilesWeek },
  ];
  return items.filter((item) => item.count > 0);
}

/** Clicks per impression as a percentage, one decimal; nothing without views. */
export function clickRate(
  impressions: number,
  clicks: number,
  locale = 'ru',
): string | null {
  if (impressions <= 0) return null;
  const rate = (clicks / impressions) * 100;
  const number = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(rate);
  return `${number} %`;
}

/** Whole days between an ISO time and now; today is zero. */
export function daysSince(iso: string, now: Date = new Date()): number {
  return Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000));
}
