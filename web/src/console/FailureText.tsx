import { Trans } from '@lingui/react/macro';

import { ConsoleError } from '@/console/session';

/** What a failed change means for the person who tried it. */
export function FailureText({ error }: { error: unknown }) {
  const reason = error instanceof ConsoleError ? error.reason : 'failed';
  if (reason === 'stale') return <Trans>Вход устарел: откройте приложение заново.</Trans>;
  if (reason === 'not-kept') {
    return <Trans>Вход не сохранился: откройте консоль в приложении Telegram.</Trans>;
  }
  if (reason === 'refused') {
    return <Trans>Аккаунта нет среди главных администраторов бота.</Trans>;
  }
  if (error instanceof ConsoleError && error.status === 422) {
    return <Trans>Ссылка должна вести на чат в Telegram: https://t.me/…</Trans>;
  }
  if (error instanceof ConsoleError && error.status === 400) {
    return <Trans>Сервер отказал: главного администратора забанить нельзя.</Trans>;
  }
  return <Trans>Не сохранилось. Попробуйте ещё раз.</Trans>;
}
