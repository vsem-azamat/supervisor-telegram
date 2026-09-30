import { Plural, Trans } from '@lingui/react/macro';
import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';

import { ConsoleFailure, ConsoleGate } from '@/components/ConsoleGate';
import {
  BagIcon,
  ChatIcon,
  DocumentIcon,
  PersonIcon,
  ShieldIcon,
} from '@/components/icons';
import {
  Chevron,
  Count,
  Hint,
  Label,
  Row,
  Rows,
  SkeletonRows,
  Sub,
  Tile,
  Title,
} from '@/components/Ui';
import { hapticSelection } from '@/hooks/useTelegram';
import {
  adminCatalogQuery,
  adminPartnersQuery,
  consoleChatsQuery,
  consoleStatsQuery,
} from '@/lib/api';
import { type AttentionKey, attention } from '@/lib/console';

/**
 * The console's first screen: what needs a look, then its sections.
 *
 * Chats and the system still open the old console under /admin, a separate
 * build, until their screens move here.
 */
export default function ConsoleSummaryPage() {
  return (
    <ConsoleGate>
      <Title>
        <Trans>Консоль</Trans>
      </Title>
      <Summary />
    </ConsoleGate>
  );
}

function Summary() {
  const navigate = useNavigate();
  const stats = useQuery(consoleStatsQuery);
  const chats = useQuery(consoleChatsQuery);
  const catalog = useQuery(adminCatalogQuery);
  const partners = useQuery(adminPartnersQuery);

  const open = (path: string) => {
    hapticSelection();
    navigate(path);
  };
  // Another build: a full load, not a route of this router.
  const leave = (path: string) => {
    hapticSelection();
    window.location.assign(path);
  };

  const loading = stats.isPending || chats.isPending || catalog.isPending;
  const failed = stats.error ?? chats.error ?? catalog.error;
  const items =
    stats.data && chats.data && catalog.data
      ? attention({
          adsToday: stats.data.spam_pings.count_24h,
          chats: chats.data,
          profilesWeek: catalog.data.counts.profiles_week,
        })
      : [];
  const approved = chats.data?.filter(
    (chat) => chat.resource_status === 'approved',
  ).length;
  const activePlacements = partners.data?.filter((row) => row.is_active).length;

  const attentionRow: Record<AttentionKey, (count: number) => ReactNode> = {
    ads: (count) => (
      <Row
        key="ads"
        leading={
          <Tile tone={4}>
            <ShieldIcon size={19} />
          </Tile>
        }
        title={<Trans>Реклама за сутки</Trans>}
        hint={
          <Trans>
            детектор, все чаты · {stats.data?.spam_pings.count_7d ?? 0} за неделю
          </Trans>
        }
        trailing={<Count>{count}</Count>}
      />
    ),
    review: (count) => (
      <Row
        key="review"
        leading={
          <Tile tone={1}>
            <ChatIcon size={19} />
          </Tile>
        }
        title={<Trans>Чаты на проверке</Trans>}
        hint={<Trans>бот в них есть, но они не одобрены</Trans>}
        trailing={<Count>{count}</Count>}
        onClick={() => leave('/admin/chats')}
      />
    ),
    profiles: (count) => (
      <Row
        key="profiles"
        leading={
          <Tile tone={0}>
            <PersonIcon size={19} />
          </Tile>
        }
        title={<Trans>Новые анкеты за неделю</Trans>}
        trailing={<Count>{count}</Count>}
        onClick={() => open('/console/catalog')}
      />
    ),
  };

  return (
    <>
      <div style={{ marginTop: 6 }}>
        <Sub>
          <Trans>Что происходит в чатах и в каталоге.</Trans>
        </Sub>
      </div>

      <Label>
        <Trans>Требует внимания</Trans>
      </Label>
      {loading ? (
        <SkeletonRows count={2} />
      ) : failed ? (
        <ConsoleFailure
          error={failed}
          retry={() => {
            void stats.refetch();
            void chats.refetch();
            void catalog.refetch();
          }}
        />
      ) : items.length > 0 ? (
        <Rows>{items.map((item) => attentionRow[item.key](item.count))}</Rows>
      ) : (
        <Hint>
          <Trans>Сейчас ничего не ждёт.</Trans>
        </Hint>
      )}

      <Label>
        <Trans>Разделы</Trans>
      </Label>
      <Rows>
        <Row
          leading={
            <Tile tone={3}>
              <ChatIcon size={19} />
            </Tile>
          }
          title={<Trans>Чаты</Trans>}
          hint={
            chats.data ? (
              <Trans>
                <Plural
                  value={chats.data.length}
                  one="# чат"
                  few="# чата"
                  many="# чатов"
                  other="# чата"
                />{' '}
                · одобрено {approved}
              </Trans>
            ) : (
              <Trans>иерархия, защита, модерация</Trans>
            )
          }
          trailing={<Chevron />}
          onClick={() => leave('/admin/chats')}
        />
        <Row
          leading={
            <Tile tone={0}>
              <DocumentIcon size={19} />
            </Tile>
          }
          title={<Trans>Каталог</Trans>}
          hint={<Trans>анкеты, заявки, поиски без ответа</Trans>}
          trailing={<Chevron />}
          onClick={() => open('/console/catalog')}
        />
        <Row
          leading={
            <Tile tone={2}>
              <BagIcon size={19} />
            </Tile>
          }
          title={<Trans>Партнёры</Trans>}
          hint={
            activePlacements !== undefined ? (
              <Trans>
                <Plural
                  value={activePlacements}
                  one="# карточка"
                  few="# карточки"
                  many="# карточек"
                  other="# карточки"
                />{' '}
                · показы и клики
              </Trans>
            ) : (
              <Trans>показы и клики</Trans>
            )
          }
          trailing={<Chevron />}
          onClick={() => open('/console/partners')}
        />
        <Row
          leading={
            <Tile tone={5}>
              <ShieldIcon size={19} />
            </Tile>
          }
          title={<Trans>Система</Trans>}
          hint={<Trans>сессии, настройки</Trans>}
          trailing={<Chevron />}
          onClick={() => leave('/admin/settings')}
        />
      </Rows>
    </>
  );
}
