/**
 * How far an advertising post in the chats reaches, as the ads page says it.
 *
 * The numbers are supervisor-telegram's (`GET /api/public/reach`), summed per
 * group and never per chat. The rules for saying them are in
 * docs/architecture.md, «The ads page is a showcase, not a shop».
 */

export interface ReachGroup {
  name: string;
  chats: number;
  members: number;
}

/** Supervisor's reach: `measured_chats` is how honest `members` is. */
export interface Reach {
  chats: number;
  members: number;
  measured_chats: number;
  groups: ReachGroup[];
}

export interface MemberFigure {
  value: number;
  /** Fewer chats measured than exist: the real figure is higher. */
  approximate: boolean;
}

export interface ReachFigures {
  chats: number;
  /** Absent when nothing was measured: "0 people" would be read and believed. */
  members: MemberFigure | null;
  /** Set when only some chats were measured: the total is a lower bound,
   *  and the page says over how many chats it was counted. */
  coverage: { measured: number; of: number } | null;
  groups: { name: string; chats: number; members: number | null }[];
}

export function reachFigures(reach: Reach): ReachFigures {
  const counted = reach.measured_chats > 0;
  return {
    chats: reach.chats,
    members: counted
      ? { value: reach.members, approximate: reach.measured_chats < reach.chats }
      : null,
    coverage:
      counted && reach.measured_chats < reach.chats
        ? { measured: reach.measured_chats, of: reach.chats }
        : null,
    groups: reach.groups.map((group) => ({
      name: group.name,
      chats: group.chats,
      members: counted && group.members > 0 ? group.members : null,
    })),
  };
}

/** The payload, checked: another service's shape is not trusted blind. */
export function isReach(payload: unknown): payload is Reach {
  if (!payload || typeof payload !== 'object') return false;
  const r = payload as Record<string, unknown>;
  return (
    typeof r.chats === 'number' &&
    typeof r.members === 'number' &&
    typeof r.measured_chats === 'number' &&
    Array.isArray(r.groups) &&
    r.groups.every(
      (g) =>
        g !== null &&
        typeof g === 'object' &&
        typeof (g as ReachGroup).name === 'string' &&
        typeof (g as ReachGroup).chats === 'number' &&
        typeof (g as ReachGroup).members === 'number',
    )
  );
}
