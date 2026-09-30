import { Trans, useLingui } from '@lingui/react/macro';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { SearchIcon } from '@/components/icons';
import { Sheet } from '@/components/Sheet';
import {
  Action,
  Hint,
  Label,
  Letters,
  Row,
  Rows,
  SkeletonRows,
  Sub,
  Tile,
  Title,
  ui,
} from '@/components/Ui';
import { blockedName, searchBlocked } from '@/console/blacklist';
import { ConsoleFailure, ConsoleGate } from '@/console/ConsoleGate';
import { blockedQuery, consoleChanges } from '@/console/queries';
import { type BlockedUser, utc } from '@/console/session';
import { hapticSelection } from '@/hooks/useTelegram';
import { initials } from '@/lib/chats';

/**
 * Everybody banned from every chat, and the way to let somebody back. The
 * same list /blacklist shows in the bot; banning happens where the person
 * wrote, with /banall or from a chat's screen here.
 */
export default function ConsoleBlacklistPage() {
  return (
    <ConsoleGate>
      <Title>
        <Trans>Чёрный список</Trans>
      </Title>
      <Blacklist />
    </ConsoleGate>
  );
}

function Blacklist() {
  const { t, i18n } = useLingui();
  const queryClient = useQueryClient();
  const { data, isPending, error, refetch } = useQuery(blockedQuery);
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<BlockedUser | null>(null);
  const unblock = useMutation({
    mutationFn: (user: BlockedUser) => consoleChanges.unblock(user.user_id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: blockedQuery.queryKey });
      // Chats' sender lists mark who is banned.
      void queryClient.invalidateQueries({ queryKey: ['console', 'chat'] });
      setPicked(null);
    },
  });

  if (isPending) {
    return (
      <div style={{ marginTop: 16 }}>
        <SkeletonRows count={5} />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div style={{ marginTop: 16 }}>
        <ConsoleFailure error={error} retry={() => void refetch()} />
      </div>
    );
  }

  const shown = searchBlocked(data, query);
  const close = () => {
    unblock.reset();
    setPicked(null);
  };

  return (
    <>
      <div style={{ marginTop: 6 }}>
        <Sub>
          <Trans>Забанены во всех чатах. Банят командой /banall или с экрана чата.</Trans>
        </Sub>
      </div>
      {data.length > 0 ? (
        <div className={ui.field} style={{ marginTop: 12 }}>
          <SearchIcon size={18} className={ui.fieldIcon} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t`Имя, @username или id`}
            maxLength={80}
            style={{ all: 'unset', flex: 1, minWidth: 0 }}
          />
        </div>
      ) : null}

      <Label aside={data.length}>
        <Trans>Заблокированы</Trans>
      </Label>
      {data.length === 0 ? (
        <Hint>
          <Trans>Список пуст.</Trans>
        </Hint>
      ) : shown.length === 0 ? (
        <Hint>
          <Trans>Никого не нашлось.</Trans>
        </Hint>
      ) : (
        <Rows>
          {shown.map((user) => {
            const name = blockedName(user);
            return (
              <Row
                key={user.user_id}
                leading={
                  <Tile tone={4}>
                    <Letters text={initials(name.replace('@', ''))} />
                  </Tile>
                }
                title={name}
                hint={
                  <>
                    {[
                      user.username && name !== `@${user.username}`
                        ? `@${user.username}`
                        : null,
                      user.user_id,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                    {' · '}
                    {/* Not «since»: the row also changes on a rename. */}
                    <Trans>
                      изменено{' '}
                      {i18n.date(utc(user.changed_at), {
                        day: 'numeric',
                        month: 'short',
                        year: 'numeric',
                      })}
                    </Trans>
                  </>
                }
                onClick={() => {
                  hapticSelection();
                  setPicked(user);
                }}
              />
            );
          })}
        </Rows>
      )}

      {picked ? (
        <Sheet title={t`Снять бан во всех чатах?`} closeLabel={t`Отмена`} onClose={close}>
          <Sub>{blockedName(picked)}</Sub>
          {unblock.isError ? (
            <Hint>
              <Trans>Не получилось. Попробуйте ещё раз.</Trans>
            </Hint>
          ) : null}
          <div className={ui.actionsStacked}>
            <Action disabled={unblock.isPending} onClick={() => unblock.mutate(picked)}>
              <Trans>Снять бан</Trans>
            </Action>
            <Action quiet onClick={close}>
              <Trans>Отмена</Trans>
            </Action>
          </div>
        </Sheet>
      ) : null}
    </>
  );
}
