import { Plural, Trans, useLingui } from '@lingui/react/macro';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useState } from 'react';
import { useParams } from 'react-router';

import { Sheet } from '@/components/Sheet';
import {
  Action,
  Actions,
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
import { ConsoleFailure, ConsoleGate } from '@/console/ConsoleGate';
import { chatDetailQuery, consoleChanges, consoleChatsQuery } from '@/console/queries';
import { Switch } from '@/console/Switch';
import type {
  ChatSender,
  ChatUpdate,
  ConsoleChat,
  ConsoleChatDetail,
} from '@/console/session';
import { ConsoleError } from '@/console/session';
import { hapticSelection } from '@/hooks/useTelegram';
import { initials } from '@/lib/chats';

/**
 * One chat, for the people who run it: whether it is approved and listed, how
 * it is protected, and who wrote in it lately. Every switch saves itself.
 */
export default function ConsoleChatPage() {
  const { id } = useParams();
  const chatId = Number(id);
  return (
    <ConsoleGate>
      {Number.isInteger(chatId) ? (
        <ChatScreen chatId={chatId} />
      ) : (
        <Hint>
          <Trans>Такого чата нет.</Trans>
        </Hint>
      )}
    </ConsoleGate>
  );
}

type Sheets =
  | { kind: 'publish' }
  | { kind: 'welcome' }
  | { kind: 'ban'; sender: ChatSender }
  | { kind: 'unban'; sender: ChatSender }
  | null;

function senderName(sender: ChatSender): string {
  const name = [sender.first_name, sender.last_name].filter(Boolean).join(' ');
  return name || (sender.username ? `@${sender.username}` : String(sender.user_id));
}

function ChatScreen({ chatId }: { chatId: number }) {
  const { t, i18n } = useLingui();
  const queryClient = useQueryClient();
  const detail = useQuery(chatDetailQuery(chatId));
  const [sheet, setSheet] = useState<Sheets>(null);
  const [failure, setFailure] = useState<ReactNode>(null);

  const settle = (changed: Partial<ConsoleChat>) => {
    queryClient.setQueryData<ConsoleChatDetail>(
      chatDetailQuery(chatId).queryKey,
      (old) => (old ? { ...old, ...changed } : old),
    );
    void queryClient.invalidateQueries({ queryKey: consoleChatsQuery.queryKey });
  };
  const failed = (error: unknown) => {
    setFailure(
      error instanceof ConsoleError && error.status === 422 ? (
        <Trans>Сервер не принял значение. Ссылка должна вести на чат в Telegram.</Trans>
      ) : (
        <Trans>Не сохранилось. Попробуйте ещё раз.</Trans>
      ),
    );
  };

  const update = useMutation({
    mutationFn: (change: ChatUpdate) => consoleChanges.updateChat(chatId, change),
    onMutate: () => setFailure(null),
    onSuccess: (chat, change) =>
      // The answer is the list view; the welcome text is not in it.
      settle({ ...chat, ...('welcome_message' in change ? change : {}) }),
    onError: failed,
  });
  const refresh = useMutation({
    mutationFn: () => consoleChanges.refreshChat(chatId),
    onMutate: () => setFailure(null),
    onSuccess: (chat) => settle(chat),
    onError: failed,
  });
  const block = useMutation({
    mutationFn: ({ sender, revoke }: { sender: ChatSender; revoke: boolean | null }) =>
      revoke === null
        ? consoleChanges.unblock(sender.user_id)
        : consoleChanges.block(sender.user_id, revoke),
    onMutate: () => setFailure(null),
    onSuccess: (answer, { sender }) => {
      queryClient.setQueryData<ConsoleChatDetail>(
        chatDetailQuery(chatId).queryKey,
        (old) =>
          old
            ? {
                ...old,
                recent_senders: old.recent_senders.map((row) =>
                  row.user_id === sender.user_id
                    ? { ...row, blocked: answer.blocked }
                    : row,
                ),
              }
            : old,
      );
      setSheet(null);
    },
    onError: failed,
  });

  if (detail.isPending) {
    return (
      <div style={{ marginTop: 16 }}>
        <SkeletonRows count={5} />
      </div>
    );
  }
  if (detail.error || !detail.data) {
    return (
      <div style={{ marginTop: 16 }}>
        <ConsoleFailure error={detail.error} retry={() => void detail.refetch()} />
      </div>
    );
  }

  const chat = detail.data;
  const title = chat.title ?? String(chat.id);
  const busy = update.isPending;
  const save = (change: ChatUpdate) => {
    hapticSelection();
    update.mutate(change);
  };
  const total = chat.recent_senders.reduce((sum, row) => sum + row.message_count, 0);

  return (
    <>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12 }}>
        <Tile tone={3}>
          <Letters text={initials(title)} />
        </Tile>
        <Title>{title}</Title>
      </div>
      <div style={{ marginTop: 6 }}>
        <Sub>
          {chat.member_count !== null ? (
            <>
              <Plural
                value={chat.member_count}
                one="# участник"
                few="# участника"
                many="# участников"
                other="# участника"
              />
              {' · '}
            </>
          ) : null}
          {chat.resource_status === 'approved' ? (
            <Trans>одобрен</Trans>
          ) : chat.resource_status === 'discovered' ? (
            <Trans>на проверке</Trans>
          ) : (
            <Trans>отключён</Trans>
          )}
        </Sub>
      </div>

      {failure ? (
        <div style={{ marginTop: 12 }}>
          <Hint>{failure}</Hint>
        </div>
      ) : null}

      {chat.resource_status !== 'approved' ? (
        <div style={{ marginTop: 16 }}>
          <Actions>
            <Action onClick={() => save({ resource_status: 'approved' })} disabled={busy}>
              {chat.resource_status === 'discovered' ? (
                <Trans>Одобрить</Trans>
              ) : (
                <Trans>Включить снова</Trans>
              )}
            </Action>
            {chat.resource_status === 'discovered' ? (
              <Action
                quiet
                onClick={() => save({ resource_status: 'disabled' })}
                disabled={busy}
              >
                <Trans>Отключить</Trans>
              </Action>
            ) : null}
          </Actions>
        </div>
      ) : null}

      <Label>
        <Trans>На публичной вкладке</Trans>
      </Label>
      <Rows>
        <Row
          title={
            chat.public_link ? (
              <Trans>Показан в «Чатах»</Trans>
            ) : (
              <Trans>Не показан</Trans>
            )
          }
          hint={chat.public_link ?? <Trans>нужна ссылка t.me</Trans>}
          trailing={
            <Switch
              checked={Boolean(chat.public_link)}
              busy={busy}
              label={t`На публичной вкладке`}
              onChange={(on) =>
                on ? setSheet({ kind: 'publish' }) : save({ public_link: '' })
              }
            />
          }
          onClick={() => setSheet({ kind: 'publish' })}
        />
      </Rows>

      <Label>
        <Trans>Защита</Trans>
      </Label>
      <Rows>
        <Row
          title={<Trans>Капча при входе</Trans>}
          trailing={
            <Switch
              checked={chat.is_captcha_enabled}
              busy={busy}
              label={t`Капча при входе`}
              onChange={(on) => save({ is_captcha_enabled: on })}
            />
          }
        />
        <Row
          title={<Trans>Приветствие</Trans>}
          hint={chat.welcome_message || <Trans>текст не задан</Trans>}
          trailing={
            <Switch
              checked={chat.is_welcome_enabled}
              busy={busy}
              label={t`Приветствие`}
              onChange={(on) => save({ is_welcome_enabled: on })}
            />
          }
          onClick={() => setSheet({ kind: 'welcome' })}
        />
        <Row
          title={<Trans>Прятать «вошёл» и «вышел»</Trans>}
          trailing={
            <Switch
              checked={chat.is_service_cleanup_enabled}
              busy={busy}
              label={t`Прятать «вошёл» и «вышел»`}
              onChange={(on) => save({ is_service_cleanup_enabled: on })}
            />
          }
        />
      </Rows>

      <Label aside={total > 0 ? <Trans>всего {i18n.number(total)}</Trans> : null}>
        <Trans>Кто писал за неделю</Trans>
      </Label>
      {chat.recent_senders.length > 0 ? (
        <Rows>
          {chat.recent_senders.map((sender) => (
            <Row
              key={sender.user_id}
              title={senderName(sender)}
              hint={
                <>
                  <Plural
                    value={sender.message_count}
                    one="# сообщение"
                    few="# сообщения"
                    many="# сообщений"
                    other="# сообщения"
                  />
                  {sender.blocked ? (
                    <>
                      {' · '}
                      <Trans>заблокирован</Trans>
                    </>
                  ) : null}
                </>
              }
              onClick={() => setSheet({ kind: sender.blocked ? 'unban' : 'ban', sender })}
            />
          ))}
        </Rows>
      ) : (
        <Hint>
          <Trans>За неделю здесь никто не писал.</Trans>
        </Hint>
      )}

      <div style={{ marginTop: 16 }}>
        <Rows>
          <Row
            title={<Trans>Обновить из Telegram</Trans>}
            hint={<Trans>название, фото и число участников</Trans>}
            onClick={() => {
              hapticSelection();
              refresh.mutate();
            }}
          />
        </Rows>
      </div>

      {sheet?.kind === 'publish' ? (
        <TextSheet
          title={t`Ссылка для публичной вкладки`}
          initial={chat.public_link ?? 'https://t.me/'}
          placeholder="https://t.me/cvut_fit"
          busy={busy}
          onClose={() => setSheet(null)}
          onSave={(link) =>
            update.mutate({ public_link: link }, { onSuccess: () => setSheet(null) })
          }
        />
      ) : null}
      {sheet?.kind === 'welcome' ? (
        <TextSheet
          multiline
          title={t`Приветствие`}
          initial={chat.welcome_message ?? ''}
          placeholder={t`Привет! Правила в закрепе.`}
          busy={busy}
          onClose={() => setSheet(null)}
          onSave={(text) =>
            update.mutate({ welcome_message: text }, { onSuccess: () => setSheet(null) })
          }
        />
      ) : null}
      {sheet?.kind === 'ban' ? (
        <Sheet
          title={t`Забанить во всех чатах?`}
          closeLabel={t`Отмена`}
          onClose={() => setSheet(null)}
        >
          <Sub>
            {senderName(sheet.sender)} ·{' '}
            <Trans>
              здесь за неделю{' '}
              <Plural
                value={sheet.sender.message_count}
                one="# сообщение"
                few="# сообщения"
                many="# сообщений"
                other="# сообщения"
              />
              . Снять бан можно здесь же.
            </Trans>
          </Sub>
          <div className={ui.actionsStacked}>
            <Action
              disabled={block.isPending}
              onClick={() => block.mutate({ sender: sheet.sender, revoke: false })}
            >
              <Trans>Забанить везде</Trans>
            </Action>
            <Action
              quiet
              disabled={block.isPending}
              onClick={() => block.mutate({ sender: sheet.sender, revoke: true })}
            >
              <Trans>Забанить и стереть сообщения</Trans>
            </Action>
            <Action quiet onClick={() => setSheet(null)}>
              <Trans>Отмена</Trans>
            </Action>
          </div>
        </Sheet>
      ) : null}
      {sheet?.kind === 'unban' ? (
        <Sheet
          title={t`Снять бан во всех чатах?`}
          closeLabel={t`Отмена`}
          onClose={() => setSheet(null)}
        >
          <Sub>{senderName(sheet.sender)}</Sub>
          <Actions>
            <Action
              disabled={block.isPending}
              onClick={() => block.mutate({ sender: sheet.sender, revoke: null })}
            >
              <Trans>Снять бан</Trans>
            </Action>
            <Action quiet onClick={() => setSheet(null)}>
              <Trans>Отмена</Trans>
            </Action>
          </Actions>
        </Sheet>
      ) : null}
    </>
  );
}

function TextSheet({
  title,
  initial,
  placeholder,
  multiline = false,
  busy,
  onClose,
  onSave,
}: {
  title: string;
  initial: string;
  placeholder: string;
  multiline?: boolean;
  busy: boolean;
  onClose: () => void;
  onSave: (value: string) => void;
}) {
  const { t } = useLingui();
  const [value, setValue] = useState(initial);
  return (
    <Sheet title={title} closeLabel={t`Отмена`} onClose={onClose}>
      <div
        className={ui.field}
        style={multiline ? { alignItems: 'flex-start' } : undefined}
      >
        {multiline ? (
          <textarea
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={placeholder}
            rows={4}
            maxLength={2000}
            style={{ all: 'unset', width: '100%', resize: 'none', lineHeight: 1.5 }}
          />
        ) : (
          <input
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={placeholder}
            maxLength={200}
            inputMode="url"
            style={{ all: 'unset', flex: 1, minWidth: 0 }}
          />
        )}
      </div>
      <Actions>
        <Action disabled={busy} onClick={() => onSave(value.trim())}>
          <Trans>Сохранить</Trans>
        </Action>
      </Actions>
    </Sheet>
  );
}
