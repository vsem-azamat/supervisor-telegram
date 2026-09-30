/** The console's blacklist screen, apart from the screen. */

import { fold } from '../lib/chats.ts';
import type { BlockedUser } from './session.ts';

/** By name, by handle with or without its @, or by a part of the id. */
export function searchBlocked(users: BlockedUser[], query: string): BlockedUser[] {
  const wanted = fold(query.trim().replace(/^@/, ''));
  if (!wanted) return users;
  return users.filter((user) => {
    const haystack = fold(
      [user.first_name, user.last_name, user.username, String(user.user_id)]
        .filter(Boolean)
        .join(' '),
    );
    return haystack.includes(wanted);
  });
}
