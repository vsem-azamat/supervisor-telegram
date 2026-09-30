import { Trans } from '@lingui/react/macro';
import { openTelegramLink } from '@tma.js/sdk-react';

import { type Activity, chipFor, initials, type PublicChat } from '@/lib/chats';

import { Chevron, Letters, Row, Tile } from './Ui';
import css from './ui.module.css';

/** Supervisor's word for how much a chat talks, and nothing for `unknown`. */
export function ActivityChip({ activity }: { activity: Activity }) {
  const chip = chipFor(activity);
  if (chip === null) return null;
  return (
    <span
      className={chip === 'busy' ? `${css.activity} ${css.activityBusy}` : css.activity}
    >
      {chip === 'busy' ? (
        <Trans>оживлённый</Trans>
      ) : chip === 'active' ? (
        <Trans>активный</Trans>
      ) : (
        <Trans>тихий</Trans>
      )}
    </span>
  );
}

/**
 * One chat. A tap opens it in Telegram, which is where it lives: the app
 * holds no conversations, only the way in.
 */
export function ChatRow({ chat, tone }: { chat: PublicChat; tone: number }) {
  return (
    <Row
      leading={
        <Tile tone={tone}>
          <Letters text={initials(chat.title)} />
        </Tile>
      }
      title={chat.title}
      hint={
        chipFor(chat.activity) ? <ActivityChip activity={chat.activity} /> : undefined
      }
      trailing={<Chevron />}
      onClick={() => openTelegramLink(chat.link)}
    />
  );
}
