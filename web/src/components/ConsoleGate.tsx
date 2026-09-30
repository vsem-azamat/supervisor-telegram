import { Trans } from '@lingui/react/macro';
import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { AppHeader } from '@/components/AppHeader';
import { Empty, Row, Rows, Screen, SkeletonRows } from '@/components/Ui';
import { api } from '@/lib/api';
import { ConsoleError } from '@/lib/console';

/**
 * The console's screens, for its operators only.
 *
 * What the screen says to anybody else is only manners: every request behind
 * it is refused on the server all the same.
 */
export function ConsoleGate({ children }: { children: ReactNode }) {
  const me = useQuery({ queryKey: ['me'], queryFn: ({ signal }) => api.getMe(signal) });

  return (
    <Screen>
      <AppHeader />
      {me.isPending ? (
        <div style={{ marginTop: 16 }}>
          <SkeletonRows count={3} />
        </div>
      ) : me.data?.is_admin ? (
        children
      ) : (
        <Empty
          title={<Trans>Консоль только для администраторов</Trans>}
          body={<Trans>Здесь ведут чаты и смотрят за каталогом.</Trans>}
        />
      )}
    </Screen>
  );
}

/** A section that did not load, with a way to try again. */
export function ConsoleFailure({ error, retry }: { error: unknown; retry: () => void }) {
  // webapi's refusal: this person is an operator of the catalog but not a
  // super admin of the moderator bot. Trying again would change nothing.
  if (error instanceof ConsoleError && error.status === 403) {
    return (
      <Rows>
        <Row
          title={<Trans>Нет доступа к чатам</Trans>}
          hint={<Trans>Аккаунта нет среди главных администраторов бота.</Trans>}
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
