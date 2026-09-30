import { Trans } from '@lingui/react/macro';
import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { AppHeader } from '@/components/AppHeader';
import { Empty, Row, Rows, Screen, SkeletonRows } from '@/components/Ui';
import { ConsoleError } from '@/console/session';
import { meQuery, UnauthorizedError } from '@/lib/api';

/**
 * The console's screens, for its operators only.
 *
 * What the screen says to anybody else is only manners: every request behind
 * it is refused on the server all the same.
 */
export function ConsoleGate({ children }: { children: ReactNode }) {
  const me = useQuery(meQuery);

  return (
    <Screen>
      <AppHeader />
      {/* The account first: a failed background refresh keeps what was
          known, and must not hide a console already shown. */}
      {me.data ? (
        me.data.is_admin ? (
          children
        ) : (
          <Empty
            title={<Trans>Консоль только для администраторов</Trans>}
            body={<Trans>Здесь ведут чаты и смотрят за каталогом.</Trans>}
          />
        )
      ) : me.isPending ? (
        <div style={{ marginTop: 16 }}>
          <SkeletonRows count={3} />
        </div>
      ) : me.error instanceof UnauthorizedError ? (
        // The catalog no longer accepts this initData; only a fresh one helps.
        <Rows>
          <Row
            title={<Trans>Откройте приложение заново</Trans>}
            hint={<Trans>Данные входа устарели.</Trans>}
          />
        </Rows>
      ) : (
        <Rows>
          <Row
            title={<Trans>Не удалось загрузить</Trans>}
            hint={<Trans>Нажмите, чтобы попробовать ещё раз</Trans>}
            onClick={() => void me.refetch()}
          />
        </Rows>
      )}
    </Screen>
  );
}

/**
 * A section that did not load: why, and a way to try again only where trying
 * again can help. See `ConsoleFailureReason`.
 */
export function ConsoleFailure({ error, retry }: { error: unknown; retry: () => void }) {
  const reason = error instanceof ConsoleError ? error.reason : 'failed';
  if (reason === 'refused') {
    return (
      <Rows>
        <Row
          title={<Trans>Нет доступа к чатам</Trans>}
          hint={<Trans>Аккаунта нет среди главных администраторов бота.</Trans>}
        />
      </Rows>
    );
  }
  if (reason === 'stale') {
    return (
      <Rows>
        <Row
          title={<Trans>Откройте приложение заново</Trans>}
          hint={<Trans>Вход в консоль действует час после открытия приложения.</Trans>}
        />
      </Rows>
    );
  }
  if (reason === 'not-kept') {
    return (
      <Rows>
        <Row
          title={<Trans>Вход не сохранился</Trans>}
          hint={
            <Trans>
              Откройте консоль в приложении Telegram на телефоне или компьютере.
            </Trans>
          }
        />
      </Rows>
    );
  }
  return (
    <Rows>
      <Row
        title={<Trans>Не удалось загрузить</Trans>}
        hint={<Trans>Нажмите, чтобы попробовать ещё раз</Trans>}
        onClick={retry}
      />
    </Rows>
  );
}
