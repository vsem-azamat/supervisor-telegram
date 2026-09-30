import { Trans } from '@lingui/react/macro';
import type { ReactNode } from 'react';

import type { ServiceType, WorkFormat } from '@/lib/types';

/**
 * How to word the "how do you work" question, or that it should not be asked.
 *
 * One column, three readings. `work_format` is `online` / `offline` / `both`,
 * which reads as online-or-in-person for a lesson and remotely-or-alongside-you
 * for an errand — the same three answers under different words. A person who
 * only writes theses is asked nothing: a written work is always remote, and
 * asking how they *teach* is what this whole distinction exists to stop.
 *
 * Shared by the two screens that ask it, because two copies of a rule about
 * wording are two copies that drift — and they already had, one screen asking
 * about teaching while the other asked the same thing of a bank statement.
 */
export type WorkFormatAsk = 'lesson' | 'errand' | 'both' | null;

export function askedFormat(
  codes: readonly string[],
  serviceTypes: ServiceType[] | undefined,
): WorkFormatAsk {
  // Nothing to go on — the reference list has not arrived, or the person has
  // not added a service yet — is not the same as "do not ask". Both would take
  // the question and the address off a screen that still has a Save button, and
  // an empty profile is exactly where somebody fills these in first.
  if (!serviceTypes || !codes.length) return 'both';
  const shapeOf = new Map(serviceTypes.map((type) => [type.code, type.form_shape]));
  const shapes = new Set(codes.map((code) => shapeOf.get(code)));
  // A code the reference list does not carry is a kind of help that has been
  // deactivated since somebody offered it: `/taxonomy/service-types` returns
  // only active ones while the cabinet returns every offer. Unknown is nothing
  // to go on, which is the neutral question and not silence.
  if (shapes.has(undefined)) return 'both';
  const lesson = shapes.has('lesson');
  const errand = shapes.has('errand');
  if (lesson && errand) return 'both';
  if (lesson) return 'lesson';
  if (errand) return 'errand';
  // Only written work, which is always remote.
  return null;
}

export function formatQuestion(asked: WorkFormatAsk): ReactNode {
  return asked === 'lesson' ? (
    <Trans>Как занимаешься</Trans>
  ) : (
    <Trans>Как работаешь</Trans>
  );
}

export function formatOptions(
  asked: WorkFormatAsk,
): { value: WorkFormat; label: ReactNode }[] {
  return [
    {
      value: 'online',
      label: asked === 'lesson' ? <Trans>Онлайн</Trans> : <Trans>Удалённо</Trans>,
    },
    {
      value: 'offline',
      label:
        asked === 'lesson' ? (
          <Trans>Очно</Trans>
        ) : asked === 'errand' ? (
          <Trans>Хожу вместе</Trans>
        ) : (
          <Trans>Лично</Trans>
        ),
    },
    { value: 'both', label: <Trans>И так, и так</Trans> },
  ];
}
