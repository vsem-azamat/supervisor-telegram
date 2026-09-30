import { Trans, useLingui } from '@lingui/react/macro';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Sheet } from '@/components/Sheet';
import { Action, Hint, Row, Rows, Sub, ui } from '@/components/Ui';
import { personName } from '@/console/activity';
import { FailureText } from '@/console/FailureText';
import { blockedQuery, consoleChanges, consoleSystemQuery } from '@/console/queries';
import { type SpamPing, utc } from '@/console/session';
import { hapticSelection } from '@/hooks/useTelegram';

/**
 * Ad-detector hits as rows: who, what they linked to, and where. The chat is
 * named only where the list mixes chats.
 */
export function PingRows({
  pings,
  showChat,
  onPick,
}: {
  pings: SpamPing[];
  showChat: boolean;
  onPick: (ping: SpamPing) => void;
}) {
  const { t, i18n } = useLingui();
  const when = (iso: string) =>
    i18n.date(utc(iso), {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  return (
    <Rows>
      {pings.map((ping) => (
        <Row
          key={ping.id}
          title={
            <>
              {personName(ping)}
              {ping.blocked ? ` · ${t`заблокирован`}` : null}
            </>
          }
          hint={[
            ping.matches.join(', '),
            showChat ? (ping.chat_title ?? String(ping.chat_id)) : null,
            when(ping.detected_at),
          ]
            .filter(Boolean)
            .join(' · ')}
          onClick={() => {
            hapticSelection();
            onPick(ping);
          }}
        />
      ))}
    </Rows>
  );
}

/**
 * One hit up close: the message as the bot saw it, and the ban that answers
 * it. A ban is global, as /banall is; «стереть» also deletes everything of
 * theirs the bot recorded.
 */
export function PingSheet({
  ping,
  onClose,
  onOpenChat,
}: {
  ping: SpamPing;
  onClose: () => void;
  onOpenChat?: () => void;
}) {
  const { t } = useLingui();
  const queryClient = useQueryClient();
  const system = useQuery(consoleSystemQuery);
  const admin = system.data?.super_admin_ids.includes(ping.user_id) ?? false;
  const ban = useMutation({
    mutationFn: (revoke: boolean) => consoleChanges.block(ping.user_id, revoke),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['console', 'spam'] });
      void queryClient.invalidateQueries({ queryKey: ['console', 'chat'] });
      void queryClient.invalidateQueries({ queryKey: blockedQuery.queryKey });
      onClose();
    },
  });
  const close = () => {
    ban.reset();
    onClose();
  };

  return (
    <Sheet title={t`Реклама`} closeLabel={t`Отмена`} onClose={close}>
      <Sub>
        {personName(ping)}
        {ping.username && personName(ping) !== `@${ping.username}`
          ? ` · @${ping.username}`
          : null}
        {' · '}
        {ping.chat_title ?? ping.chat_id}
      </Sub>
      {ping.snippet ? <blockquote className={ui.quote}>{ping.snippet}</blockquote> : null}
      <Hint>{ping.matches.join(', ')}</Hint>
      {ban.error ? (
        <Hint>
          <FailureText error={ban.error} />
        </Hint>
      ) : null}
      <div className={ui.actionsStacked}>
        {ping.blocked ? (
          <Hint>
            <Trans>Уже в чёрном списке.</Trans>
          </Hint>
        ) : admin ? (
          <Hint>
            <Trans>Это главный администратор.</Trans>
          </Hint>
        ) : (
          <>
            <Action disabled={ban.isPending} onClick={() => ban.mutate(false)}>
              <Trans>Забанить везде</Trans>
            </Action>
            <Action quiet disabled={ban.isPending} onClick={() => ban.mutate(true)}>
              <Trans>Забанить и стереть все его сообщения</Trans>
            </Action>
          </>
        )}
        {onOpenChat ? (
          <Action quiet onClick={onOpenChat}>
            <Trans>Открыть чат</Trans>
          </Action>
        ) : null}
        <Action quiet onClick={close}>
          <Trans>Отмена</Trans>
        </Action>
      </div>
    </Sheet>
  );
}
