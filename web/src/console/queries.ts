/**
 * The console's queries. Webapi's go through its session (see session.ts);
 * the catalog's are ordinary `/api/v1` calls that only operators may make.
 */

import { api, rawInitData } from '@/lib/api';

import { type ConsoleChat, consoleRequester, type HomeStats } from './session';

/** The console's requester for webapi's session endpoints. See session.ts. */
export const consoleGet = consoleRequester((...args) => fetch(...args), rawInitData);

// The console reads while somebody looks at it; a minute is fresh enough.
const CONSOLE_STALE = 60_000;

export const adminCatalogQuery = {
  queryKey: ['console', 'catalog'] as const,
  queryFn: ({ signal }: { signal: AbortSignal }) => api.getAdminCatalog(signal),
  staleTime: CONSOLE_STALE,
};

export const adminPartnersQuery = {
  queryKey: ['console', 'partners'] as const,
  queryFn: ({ signal }: { signal: AbortSignal }) => api.getAdminPartners(signal),
  staleTime: CONSOLE_STALE,
};

export const consoleStatsQuery = {
  queryKey: ['console', 'stats'] as const,
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    consoleGet<HomeStats>('/api/stats/home', { signal }),
  staleTime: CONSOLE_STALE,
  // A refusal or a stale sign-in stays so for this launch; coming back to the
  // summary must not send the sign-in again.
  retryOnMount: false,
};

export const consoleChatsQuery = {
  queryKey: ['console', 'chats'] as const,
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    consoleGet<ConsoleChat[]>('/api/chats', { signal }),
  staleTime: CONSOLE_STALE,
  retryOnMount: false,
};
