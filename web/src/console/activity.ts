/** A chat's activity and its place in the tree, apart from the screen. */

import type { ConsoleChat } from './session.ts';

export interface HeatmapCell {
  /** 0 is Monday, in UTC. */
  weekday: number;
  /** 0–23, UTC. */
  hour: number;
  count: number;
}

export interface MemberSnapshot {
  captured_at: string;
  member_count: number;
}

const WEEK_HOURS = 7 * 24;

/**
 * Messages per weekday and hour in the reader's own time: webapi counts in
 * UTC, and a Prague evening read as UTC would look like the afternoon.
 * `offsetMinutes` is east of UTC, the opposite sign of getTimezoneOffset().
 */
export function localHeatmap(
  cells: HeatmapCell[],
  offsetMinutes: number,
): { grid: number[][]; max: number } {
  const week = Array<number>(WEEK_HOURS).fill(0);
  const shift = Math.floor(offsetMinutes / 60);
  for (const cell of cells) {
    const at =
      (((cell.weekday * 24 + cell.hour + shift) % WEEK_HOURS) + WEEK_HOURS) % WEEK_HOURS;
    week[at] = (week[at] ?? 0) + cell.count;
  }
  const grid = Array.from({ length: 7 }, (_, day) => week.slice(day * 24, day * 24 + 24));
  const max = Math.max(0, ...week);
  return { grid, max };
}

/**
 * Member counts as a line 100 wide and 32 high, oldest on the left, with how
 * far the count moved. Nothing to draw from fewer than two counts.
 */
export function memberTrend(
  snapshots: MemberSnapshot[],
): { points: string; first: number; last: number; change: number } | null {
  if (snapshots.length < 2) return null;
  const counts = snapshots.map((snapshot) => snapshot.member_count);
  const low = Math.min(...counts);
  const high = Math.max(...counts);
  const step = 100 / (counts.length - 1);
  const y = (count: number) =>
    high === low ? 16 : 32 - ((count - low) / (high - low)) * 32;
  const round = (n: number) => Math.round(n * 10) / 10;
  const points = counts
    .map((count, i) => `${round(i * step)},${round(y(count))}`)
    .join(' ');
  const first = counts[0] ?? 0;
  const last = counts.at(-1) ?? 0;
  return { points, first, last, change: last - first };
}

/**
 * The chats this one may go under. The console's list groups one level deep,
 * so only a top-level chat is offered, and a chat others already sit under
 * stays at the top itself.
 */
export function parentChoices(chats: ConsoleChat[], chatId: number): ConsoleChat[] {
  if (chats.some((chat) => chat.parent_chat_id === chatId)) return [];
  return chats
    .filter((chat) => chat.id !== chatId && chat.parent_chat_id === null)
    .sort((a, b) => (a.title ?? '').localeCompare(b.title ?? ''));
}

/** The name Telegram gave, else the handle, else the id. */
export function personName(person: {
  user_id: number;
  first_name: string | null;
  last_name: string | null;
  username: string | null;
}): string {
  const name = [person.first_name, person.last_name].filter(Boolean).join(' ');
  return name || (person.username ? `@${person.username}` : String(person.user_id));
}
