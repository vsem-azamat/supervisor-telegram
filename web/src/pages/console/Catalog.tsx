import { Plural, Trans } from '@lingui/react/macro';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router';

import { ConsoleFailure, ConsoleGate } from '@/components/ConsoleGate';
import { SearchIcon, TargetIcon } from '@/components/icons';
import {
  Chevron,
  Count,
  Hint,
  Label,
  Letters,
  Row,
  Rows,
  SkeletonRows,
  Tile,
  Title,
  ui,
} from '@/components/Ui';
import { hapticSelection } from '@/hooks/useTelegram';
import { adminCatalogQuery } from '@/lib/api';
import { daysSince } from '@/lib/console';

/**
 * The catalog as the operator reads it: new profiles, requests nobody
 * answered, and what people searched for and did not find. Reads only.
 * See teachers-catalog's docs/architecture.md, «The operator reads, and only reads».
 */
export default function ConsoleCatalogPage() {
  return (
    <ConsoleGate>
      <Title>
        <Trans>Каталог</Trans>
      </Title>
      <Catalog />
    </ConsoleGate>
  );
}

function Days({ since }: { since: string }) {
  const days = daysSince(since);
  return days === 0 ? (
    <Trans>сегодня</Trans>
  ) : (
    <Plural value={days} one="# дн" few="# дн" many="# дн" other="# дн" />
  );
}

function Catalog() {
  const navigate = useNavigate();
  const { data, isPending, error, refetch } = useQuery(adminCatalogQuery);

  if (isPending) {
    return (
      <div style={{ marginTop: 16 }}>
        <SkeletonRows count={4} />
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

  const { counts } = data;
  return (
    <>
      <div className={ui.stats}>
        <div className={ui.stat}>
          <b>{counts.profiles_week}</b>
          <span>
            <Trans>анкет за 7 дней</Trans>
          </span>
        </div>
        <div className={ui.stat}>
          <b>{counts.requests_week}</b>
          <span>
            <Trans>заявок за 7 дней</Trans>
          </span>
        </div>
        <div className={ui.stat}>
          <b>{counts.unanswered}</b>
          <span>
            <Trans>без откликов</Trans>
          </span>
        </div>
      </div>

      <Label>
        <Trans>Новые анкеты</Trans>
      </Label>
      {data.profiles.length > 0 ? (
        <Rows>
          {data.profiles.map((profile) => (
            <Row
              key={profile.user_id}
              leading={
                <Tile tone={0}>
                  <Letters text={profile.name.slice(0, 1).toUpperCase()} />
                </Tile>
              }
              title={profile.name}
              hint={profile.services.join(', ')}
              trailing={
                <>
                  <Count>
                    <Days since={profile.published_at} />
                  </Count>
                  <Chevron />
                </>
              }
              onClick={() => {
                hapticSelection();
                navigate(`/helper/${profile.user_id}`);
              }}
            />
          ))}
        </Rows>
      ) : (
        <Hint>
          <Trans>За неделю новых анкет не было.</Trans>
        </Hint>
      )}

      <Label
        aside={counts.unanswered > data.unanswered.length ? counts.unanswered : null}
      >
        <Trans>Заявки без откликов</Trans>
      </Label>
      {data.unanswered.length > 0 ? (
        <Rows>
          {data.unanswered.map((request) => (
            <Row
              key={request.id}
              leading={
                <Tile tone={4}>
                  <TargetIcon size={19} />
                </Tile>
              }
              title={request.text}
              trailing={
                <Count>
                  <Days since={request.created_at} />
                </Count>
              }
            />
          ))}
        </Rows>
      ) : (
        <Hint>
          <Trans>На все открытые заявки кто-то откликнулся.</Trans>
        </Hint>
      )}

      <Label aside={<Trans>30 дней</Trans>}>
        <Trans>Искали и не нашли</Trans>
      </Label>
      {data.failed_searches.length > 0 ? (
        <Rows>
          {data.failed_searches.map((search) => (
            <Row
              key={search.text}
              leading={
                <Tile tone={5}>
                  <SearchIcon size={19} />
                </Tile>
              }
              title={search.text}
              trailing={
                <Count>
                  <Plural
                    value={search.times}
                    one="# раз"
                    few="# раза"
                    many="# раз"
                    other="# раза"
                  />
                </Count>
              }
            />
          ))}
        </Rows>
      ) : (
        <Hint>
          <Trans>Всё, что искали, нашлось.</Trans>
        </Hint>
      )}
    </>
  );
}
