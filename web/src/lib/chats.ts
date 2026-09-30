/**
 * The chat directory, as the Chats tab reads it.
 *
 * The chats are supervisor-telegram's (`GET /api/public/catalog`), served on
 * this origin by the router. What may be read and why is in
 * docs/architecture.md, «Two backends, one origin»; how the directory is
 * built from it is the paragraph after.
 */

/** Supervisor's own words for how much a chat talks. `unknown` is an answer. */
export type Activity = 'unknown' | 'quiet' | 'active' | 'busy';

/** One chat as supervisor publishes it: four fields, no ids, no counts. */
export interface PublicChat {
  title: string;
  link: string;
  /** The parent chat's title: supervisor's grouping. No name is written in the app. */
  group: string | null;
  activity: Activity;
}

const ACTIVITIES: readonly Activity[] = ['unknown', 'quiet', 'active', 'busy'];

/** Where a chat may lead: Telegram's own hosts, which openTelegramLink accepts. */
const TELEGRAM_LINK = /^https:\/\/(t\.me|telegram\.me|telegram\.dog)\//;

/**
 * The directory as it arrived, checked rather than trusted.
 *
 * It comes from another service through a proxy, so anything can: a
 * Cloudflare page instead of JSON, an item without a title, an activity added
 * later. An item that cannot be drawn or opened is dropped; an activity this
 * app does not know is `unknown`, which draws nothing.
 */
export function sanitize(payload: unknown[]): PublicChat[] {
  const chats: PublicChat[] = [];
  for (const item of payload) {
    if (!item || typeof item !== 'object') continue;
    const { title, link, group, activity } = item as Record<string, unknown>;
    if (typeof title !== 'string' || !title.trim()) continue;
    if (typeof link !== 'string' || !TELEGRAM_LINK.test(link)) continue;
    chats.push({
      title,
      link,
      group: typeof group === 'string' && group ? group : null,
      activity: ACTIVITIES.includes(activity as Activity)
        ? (activity as Activity)
        : 'unknown',
    });
  }
  return chats;
}

/** A line of the directory: a group with its own screen, or a chat. */
export type Entry =
  | { kind: 'section'; name: string; chats: PublicChat[] }
  | { kind: 'chat'; chat: PublicChat };

export interface Directory {
  entries: Entry[];
  /** Chats without a group, shown last under their own heading. */
  rest: PublicChat[];
}

/**
 * Entries in the order supervisor gave, with one exception each way.
 *
 * A group with a single chat is that chat: a screen with one line behind it
 * is a tap for nothing. A group the server returned in two runs is still one
 * group, since the directory is a list of places, not a transcript of rows.
 */
export function directory(chats: PublicChat[]): Directory {
  const groups = new Map<string, PublicChat[]>();
  const rest: PublicChat[] = [];
  for (const chat of chats) {
    if (chat.group === null) {
      rest.push(chat);
      continue;
    }
    const members = groups.get(chat.group);
    if (members) members.push(chat);
    else groups.set(chat.group, [chat]);
  }

  const entries: Entry[] = [];
  for (const [name, members] of groups) {
    const [only] = members;
    entries.push(
      members.length === 1 && only
        ? { kind: 'chat', chat: only }
        : { kind: 'section', name, chats: members },
    );
  }
  return { entries, rest };
}

/** How many chat names a section's row lists under its own. */
const HINT_CHATS = 3;

/**
 * A few of a section's chats, for the row that opens it.
 *
 * The section's own general chat, named like the section, is skipped: the
 * row's title already says it. Found by name rather than by position, because
 * where supervisor puts it has changed before.
 */
export function sectionHint(section: Extract<Entry, { kind: 'section' }>): string {
  return section.chats
    .filter((chat) => chat.title !== section.name)
    .slice(0, HINT_CHATS)
    .map((chat) => chat.title)
    .join(', ');
}

/** Lower case, without diacritics: «ČVUT» and «cvut» are the same word here. */
export function fold(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}

/**
 * The chats every word of the query appears in, title or group, in any order.
 *
 * Flat on purpose: somebody who typed «fit» wants the chat, not the section
 * it sits in. An empty query narrows nothing.
 */
export function search(chats: PublicChat[], query: string): PublicChat[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return chats;
  return chats.filter((chat) => {
    const haystack = fold(`${chat.title} ${chat.group ?? ''}`);
    return words.every((word) => haystack.includes(word));
  });
}

/** Which chip a chat wears. None for `unknown`: an empty space is the honest answer. */
export function chipFor(activity: Activity): Exclude<Activity, 'unknown'> | null {
  return activity === 'unknown' ? null : activity;
}

/**
 * A tile's letters, from the name before any «|»: chats name themselves
 * twice, «ČVUT | ЧВУТ», and the two halves' initials read as one name.
 */
export function initials(title: string): string {
  const [name = title] = title.split('|');
  const words = name
    .replace(/[^\p{L}\p{N} ]/gu, ' ')
    .split(/\s+/)
    .filter(Boolean);
  const [first = '#', second] = words;
  // «ČVUT FIT»: a university's abbreviation, then the faculty's. The
  // faculty's is what tells it from its neighbours. «Fyzika v ČR» ends in an
  // abbreviation too, but does not start with one.
  const last = words.at(-1) ?? '';
  const isAbbreviation = (word: string) =>
    word.length <= 5 && (word.match(/\p{Lu}/gu)?.length ?? 0) >= 2;
  // «VŠE», «VŠCHT»: an abbreviation is the name, and cutting it to two
  // letters makes neighbours identical.
  if (words.length === 1 && isAbbreviation(first)) return first.toUpperCase();
  if (
    words.length > 1 &&
    isAbbreviation(first) &&
    isAbbreviation(last) &&
    last.length <= 4
  ) {
    return last.toUpperCase();
  }
  if (second) return (first.charAt(0) + second.charAt(0)).toUpperCase();
  return first.slice(0, 2).toUpperCase();
}
