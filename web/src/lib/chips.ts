import { formatDay } from '@/components/Phrase';
import type { Chip } from '@/lib/types';

/**
 * How a parsed chip is keyed and worded.
 *
 * Two screens read the same chips now — the search shows them back as what it
 * understood, and the sheet that turns a search into a request shows the same
 * set with the same words. Two copies of "a budget chip reads `≤ 600 Kč`" are
 * two copies that drift.
 */
export function chipKey(chip: Chip): string {
  return `${chip.kind}:${chip.value ?? chip.label}`;
}

export function chipLabel(chip: Chip, locale: string): string {
  if (chip.kind === 'deadline') return formatDay(chip.label, locale);
  if (chip.kind === 'budget') return `≤ ${chip.label} Kč`;
  return chip.label;
}
