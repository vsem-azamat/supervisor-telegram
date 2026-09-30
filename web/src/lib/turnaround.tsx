import { Trans } from '@lingui/react/macro';

/**
 * How long a written work takes, in the words a person would use.
 *
 * A closed set and not a number field: five taps cover what people actually
 * offer, a keyboard on a phone is a keyboard on a phone, and "asap" typed into
 * a text box sorts against nothing. Anything outside them is «договоримся»,
 * which is what `null` means — an answer, not a gap.
 *
 * Shared by the screen that asks and the page that shows, for the reason
 * `workFormat` gives: two copies of a rule about wording are two copies that
 * drift, and these two already have to agree that seven days is "a week".
 */
export const TURNAROUNDS = [1, 3, 7, 14, 30] as const;

export function TurnaroundLabel({ days }: { days: number }) {
  if (days === 1) return <Trans>За день</Trans>;
  if (days === 3) return <Trans>3 дня</Trans>;
  if (days === 7) return <Trans>Неделя</Trans>;
  if (days === 14) return <Trans>Две недели</Trans>;
  if (days === 30) return <Trans>Месяц</Trans>;
  // A number the form cannot produce — an older row, or an import. Shown as
  // what it is rather than rounded to the nearest chip, which would misquote
  // somebody's promise.
  return <Trans>{days} дн.</Trans>;
}
