import { Plural, Trans } from '@lingui/react/macro';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router';

import { AppHeader } from '@/components/AppHeader';
import { ChatRow } from '@/components/ChatRow';
import { TabBar } from '@/components/TabBar';
import { Empty, Row, Rows, Screen, SkeletonRows, Sub, Title } from '@/components/Ui';
import { chatsQuery } from '@/lib/api';

/**
 * One group's chats: a university with its faculties and dorms.
 *
 * The same query as the directory, so opening a section costs no request.
 * The group is found by the name in the address, which is the one thing the
 * directory can link by; a name that no longer exists says so rather than
 * showing an empty list.
 */
export default function ChatSectionPage() {
  const { group = '' } = useParams();

  const { data, isPending, isError, refetch } = useQuery(chatsQuery);

  // Straight from the data, not through the directory's entries: a group
  // that has shrunk to one chat is still a group somebody may have linked to.
  const chats = (data ?? []).filter((chat) => chat.group === group);

  return (
    <>
      <Screen withTabs>
        <AppHeader />
        <Title>{group}</Title>
        {isPending ? (
          <SkeletonRows count={5} />
        ) : isError ? (
          <Rows>
            <Row
              title={<Trans>Не удалось загрузить чаты</Trans>}
              hint={<Trans>Нажми, чтобы попробовать ещё раз</Trans>}
              onClick={() => void refetch()}
            />
          </Rows>
        ) : chats.length === 0 ? (
          <Empty
            title={<Trans>Такой группы больше нет</Trans>}
            body={<Trans>Вернись к списку чатов.</Trans>}
          />
        ) : (
          <>
            <div style={{ marginTop: 6, marginBottom: 16 }}>
              <Sub>
                <Plural
                  value={chats.length}
                  one="# чат"
                  few="# чата"
                  many="# чатов"
                  other="# чата"
                />
              </Sub>
            </div>
            <Rows>
              {chats.map((chat, index) => (
                <ChatRow key={chat.link} chat={chat} tone={index} />
              ))}
            </Rows>
          </>
        )}
      </Screen>
      <TabBar />
    </>
  );
}
