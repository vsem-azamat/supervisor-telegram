import { Plural, Trans, useLingui } from '@lingui/react/macro';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useState } from 'react';
import { useParams } from 'react-router';

import { Sheet } from '@/components/Sheet';
import {
  Action,
  Actions,
  Chevron,
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
import { isListed } from '@/console/chats';
import {
  blockedQuery,
  chatDetailQuery,
  consoleChanges,
  consoleChatsQuery,
  consoleSystemQuery,
} from '@/console/queries';
import { Switch } from '@/console/Switch';
import {
  type ChatSender,
  type ChatUpdate,
  type ConsoleChat,
  type ConsoleChatDetail,
  ConsoleError,
} from '@/console/session';
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
      {/* Keyed: what the screen remembers (a taken-down link) is one chat's. */}
      {Number.isInteger(chatId) ? (
        <ChatScreen key={chatId} chatId={chatId} />
      ) : (
        <NoSuchChat />
      )}
    </ConsoleGate>
  );
}

function NoSuchChat() {
  return (
    <div style={{ marginTop: 16 }}>
      <Hint>
        <Trans>Такого чата нет.</Trans>
      </Hint>
    </div>
  );
}

type Sheets =
  | { kind: 'publish' }
  | { kind: 'unpublish' }
  | { kind: 'disable' }
  | { kind: 'welcome'; enable: boolean }
  | { kind: 'ban'; sender: ChatSender }
  | { kind: 'unban'; sender: ChatSender }
  | null;

function senderName(sender: ChatSender): string {
  const name = [sender.first_name, sender.last_name].filter(Boolean).join(' ');
  return name || (sender.username ? `@${sender.username}` : String(sender.user_id));
}

/** What a failed change means for the person who tried it. */
function FailureText({ error }: { error: unknown }) {
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

function ChatScreen({ chatId }: { chatId: number }) {
  const { t, i18n } = useLingui();
  const queryClient = useQueryClient();
  const detail = useQuery(chatDetailQuery(chatId));
  const system = useQuery(consoleSystemQuery);
  const [sheet, setSheet] = useState<Sheets>(null);
  const [error, setError] = useState<unknown>(null);
  const [refreshed, setRefreshed] = useState(false);
  // The link a chat had before it was taken down, so publishing it again
  // does not mean finding an invite hash in Telegram once more.
  const [lastLink, setLastLink] = useState<string | null>(null);

  const open = (next: Sheets) => {
    setError(null);
    setSheet(next);
  };
  // A sheet's failure belongs to the sheet: it goes when the sheet does.
  const close = () => {
    setError(null);
    setSheet(null);
  };
  const settle = (changed: Partial<ConsoleChatDetail>) => {
    queryClient.setQueryData<ConsoleChatDetail>(
      chatDetailQuery(chatId).queryKey,
      (old) => (old ? { ...old, ...changed } : old),
    );
    void queryClient.invalidateQueries({ queryKey: consoleChatsQuery.queryKey });
  };

  const update = useMutation({
    mutationFn: (change: ChatUpdate) => consoleChanges.updateChat(chatId, change),
    onMutate: () => setError(null),
    onSuccess: (chat: ConsoleChat, change) =>
      // The answer is the list view; the welcome text is not in it.
      settle({ ...chat, ...('welcome_message' in change ? change : {}) }),
    onError: setError,
  });
  const refresh = useMutation({
    mutationFn: () => consoleChanges.refreshChat(chatId),
    onMutate: () => {
      setError(null);
      setRefreshed(false);
    },
    onSuccess: (chat) => {
      settle(chat);
      setRefreshed(true);
    },
    onError: setError,
  });
  const block = useMutation({
    mutationFn: ({ sender, revoke }: { sender: ChatSender; revoke: boolean | null }) =>
      revoke === null
        ? consoleChanges.unblock(sender.user_id)
        : consoleChanges.block(sender.user_id, revoke),
    onMutate: () => setError(null),
    onSuccess: () => {
      // A ban is every chat's: every chat's sender list may show it.
      void queryClient.invalidateQueries({ queryKey: ['console', 'chat'] });
      void queryClient.invalidateQueries({ queryKey: blockedQuery.queryKey });
      setSheet((current) =>
        current?.kind === 'ban' || current?.kind === 'unban' ? null : current,
      );
    },
    onError: setError,
  });

  if (detail.isPending) {
    return (
      <div style={{ marginTop: 16 }}>
        <SkeletonRows count={5} />
      </div>
    );
  }
  if (detail.error instanceof ConsoleError && detail.error.status === 404) {
    return <NoSuchChat />;
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
  // One change at a time: a refresh answer landing after a switch's would
  // put the switch back.
  const busy = update.isPending || refresh.isPending;
  const save = (change: ChatUpdate, after?: () => void) => {
    hapticSelection();
    update.mutate(change, { onSuccess: after });
  };
  const approved = chat.resource_status === 'approved';
  // What students see: the public tab lists approved chats with a link.
  const listed = isListed(chat);
  const admins = new Set(system.data?.super_admin_ids ?? []);
  const total = chat.recent_senders.reduce((sum, row) => sum + row.message_count, 0);
  const sheetError = sheet && error ? <FailureText error={error} /> : null;

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
          {approved ? (
            <Trans>одобрен</Trans>
          ) : chat.resource_status === 'discovered' ? (
            <Trans>на проверке</Trans>
          ) : (
            <Trans>отключён</Trans>
          )}
        </Sub>
      </div>

      {error && !sheet ? (
        <div style={{ marginTop: 12 }}>
          <Hint>
            <FailureText error={error} />
          </Hint>
        </div>
      ) : null}

      {!approved ? (
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
            listed ? (
              <Trans>Показан в «Чатах»</Trans>
            ) : chat.public_link && !approved ? (
              <Trans>Не виден: чат не одобрен</Trans>
            ) : chat.public_link ? (
              <Trans>Не виден: у чата нет названия</Trans>
            ) : (
              <Trans>Не показан</Trans>
            )
          }
          hint={
            chat.public_link && !approved ? (
              <Trans>появится после одобрения</Trans>
            ) : chat.public_link && !listed ? (
              <Trans>обновите его из Telegram</Trans>
            ) : chat.public_link ? null : (
              <Trans>нужна ссылка t.me</Trans>
            )
          }
          trailing={
            <Switch
              checked={Boolean(chat.public_link)}
              busy={busy}
              label={t`На публичной вкладке`}
              onChange={(on) => open({ kind: on ? 'publish' : 'unpublish' })}
            />
          }
        />
        {chat.public_link ? (
          <Row
            title={<Trans>Ссылка</Trans>}
            hint={chat.public_link}
            trailing={<Chevron />}
            onClick={() => open({ kind: 'publish' })}
          />
        ) : null}
      </Rows>

      <Label>
        <Trans>Защита</Trans>
      </Label>
      {!approved ? (
        // The bot ignores chats it is not approved in: nothing below runs there.
        <div style={{ marginBottom: 8 }}>
          <Hint>
            <Trans>Работает только в одобренном чате.</Trans>
          </Hint>
        </div>
      ) : null}
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
          trailing={
            <Switch
              checked={chat.is_welcome_enabled}
              busy={busy}
              label={t`Приветствие`}
              onChange={(on) =>
                // On with no text would greet nobody: ask for the text first.
                on && !chat.welcome_message
                  ? open({ kind: 'welcome', enable: true })
                  : save({ is_welcome_enabled: on })
              }
            />
          }
        />
        <Row
          title={<Trans>Текст приветствия</Trans>}
          hint={chat.welcome_message || <Trans>не задан</Trans>}
          trailing={<Chevron />}
          onClick={() => open({ kind: 'welcome', enable: false })}
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
          {chat.recent_senders.map((sender) => {
            const admin = admins.has(sender.user_id);
            return (
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
                    {admin ? (
                      <>
                        {' · '}
                        <Trans>администратор</Trans>
                      </>
                    ) : sender.blocked ? (
                      <>
                        {' · '}
                        <Trans>заблокирован</Trans>
                      </>
                    ) : null}
                  </>
                }
                onClick={
                  admin
                    ? undefined
                    : () => open({ kind: sender.blocked ? 'unban' : 'ban', sender })
                }
              />
            );
          })}
        </Rows>
      ) : (
        <Hint>
          <Trans>За неделю здесь никто не писал.</Trans>
        </Hint>
      )}

      <div style={{ marginTop: 16 }}>
        <Rows>
          <Row
            title={
              refresh.isPending ? (
                <Trans>Обновляем…</Trans>
              ) : (
                <Trans>Обновить из Telegram</Trans>
              )
            }
            hint={
              refreshed ? (
                <Trans>Обновлено</Trans>
              ) : (
                <Trans>название, фото и число участников</Trans>
              )
            }
            onClick={
              busy
                ? undefined
                : () => {
                    hapticSelection();
                    refresh.mutate();
                  }
            }
          />
        </Rows>
      </div>

      {approved ? (
        <div style={{ marginTop: 16 }}>
          <Actions>
            <Action quiet onClick={() => open({ kind: 'disable' })} disabled={busy}>
              <Trans>Отключить чат</Trans>
            </Action>
          </Actions>
        </div>
      ) : null}

      {sheet?.kind === 'publish' ? (
        <TextSheet
          title={t`Ссылка для публичной вкладки`}
          initial={chat.public_link ?? lastLink ?? 'https://t.me/'}
          placeholder="https://t.me/cvut_fit"
          busy={busy}
          error={sheetError}
          onClose={close}
          // Empty is not a link: taking the chat down is the switch's, and asks.
          canSave={(link) => link.length > 0}
          onSave={(link) => save({ public_link: link }, close)}
        />
      ) : null}
      {sheet?.kind === 'disable' ? (
        <Sheet title={t`Отключить чат?`} closeLabel={t`Отмена`} onClose={close}>
          <Sub>
            <Trans>
              Бот перестанет его модерировать: капча, приветствие и чёрный список там
              работать не будут. Включить можно здесь же.
            </Trans>
            {listed ? (
              <>
                {' '}
                <Trans>Чат пропадёт с публичной вкладки.</Trans>
              </>
            ) : null}
          </Sub>
          {sheetError ? <Hint>{sheetError}</Hint> : null}
          <div className={ui.actionsStacked}>
            <Action
              disabled={busy}
              onClick={() => save({ resource_status: 'disabled' }, close)}
            >
              <Trans>Отключить</Trans>
            </Action>
            <Action quiet onClick={close}>
              <Trans>Отмена</Trans>
            </Action>
          </div>
        </Sheet>
      ) : null}
      {sheet?.kind === 'unpublish' ? (
        <Sheet
          title={t`Снять с публичной вкладки?`}
          closeLabel={t`Отмена`}
          onClose={close}
        >
          <Sub>
            <Trans>Ссылка сотрётся: {chat.public_link}</Trans>
          </Sub>
          {sheetError ? <Hint>{sheetError}</Hint> : null}
          <div className={ui.actionsStacked}>
            <Action
              disabled={busy}
              onClick={() => {
                const link = chat.public_link;
                save({ public_link: '' }, () => {
                  setLastLink(link);
                  setSheet(null);
                });
              }}
            >
              <Trans>Снять</Trans>
            </Action>
            <Action quiet onClick={close}>
              <Trans>Отмена</Trans>
            </Action>
          </div>
        </Sheet>
      ) : null}
      {sheet?.kind === 'welcome' ? (
        <TextSheet
          multiline
          title={t`Приветствие`}
          note={<Trans>Бот пишет его новичку: «@имя, ваш текст».</Trans>}
          initial={chat.welcome_message ?? ''}
          placeholder={t`правила в закрепе, рекламу не публикуем.`}
          busy={busy}
          error={sheetError}
          onClose={close}
          // Switching on asks for the text, so it cannot be empty there. Clearing
          // it otherwise switches the greeting off: on with no text greets nobody.
          canSave={(text) => !sheet.enable || text.length > 0}
          onSave={(text) =>
            save(
              sheet.enable
                ? { welcome_message: text, is_welcome_enabled: true }
                : text
                  ? { welcome_message: text }
                  : { welcome_message: text, is_welcome_enabled: false },
              close,
            )
          }
        />
      ) : null}
      {sheet?.kind === 'ban' ? (
        <Sheet title={t`Забанить во всех чатах?`} closeLabel={t`Отмена`} onClose={close}>
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
              . «Стереть» удаляет все его сообщения, которые видел бот, во всех чатах.
            </Trans>
          </Sub>
          {sheetError ? <Hint>{sheetError}</Hint> : null}
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
              <Trans>Забанить и стереть все его сообщения</Trans>
            </Action>
            <Action quiet onClick={close}>
              <Trans>Отмена</Trans>
            </Action>
          </div>
        </Sheet>
      ) : null}
      {sheet?.kind === 'unban' ? (
        <Sheet title={t`Снять бан во всех чатах?`} closeLabel={t`Отмена`} onClose={close}>
          <Sub>{senderName(sheet.sender)}</Sub>
          {sheetError ? <Hint>{sheetError}</Hint> : null}
          <div className={ui.actionsStacked}>
            <Action
              disabled={block.isPending}
              onClick={() => block.mutate({ sender: sheet.sender, revoke: null })}
            >
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

function TextSheet({
  title,
  note,
  initial,
  placeholder,
  multiline = false,
  busy,
  error,
  canSave = () => true,
  onClose,
  onSave,
}: {
  title: string;
  note?: ReactNode;
  initial: string;
  placeholder: string;
  multiline?: boolean;
  busy: boolean;
  error: ReactNode;
  canSave?: (value: string) => boolean;
  onClose: () => void;
  onSave: (value: string) => void;
}) {
  const { t } = useLingui();
  const [value, setValue] = useState(initial);
  return (
    <Sheet title={title} closeLabel={t`Отмена`} onClose={onClose}>
      {note ? <Sub>{note}</Sub> : null}
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
      {error ? <Hint>{error}</Hint> : null}
      <Actions>
        <Action
          disabled={busy || !canSave(value.trim())}
          onClick={() => onSave(value.trim())}
        >
          <Trans>Сохранить</Trans>
        </Action>
      </Actions>
    </Sheet>
  );
}
