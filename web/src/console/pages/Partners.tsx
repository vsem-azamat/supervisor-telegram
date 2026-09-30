import { Trans, useLingui } from '@lingui/react/macro';
import { useQuery } from '@tanstack/react-query';
import {
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
import { adminPartnersQuery } from '@/console/queries';
import { clickRate } from '@/console/session';
import type { AdminPlacement, PlacementSlot } from '@/lib/generated/types.gen';

/**
 * Partner placements and how they did over the last month.
 *
 * Read-only: placements are still added in the database; the form for a new
 * one comes later. See teachers-catalog's docs/architecture.md.
 */
export default function ConsolePartnersPage() {
  return (
    <ConsoleGate>
      <Title>
        <Trans>Партнёры</Trans>
      </Title>
      <div style={{ marginTop: 6 }}>
        <Sub>
          <Trans>Показы и клики за 30 дней.</Trans>
        </Sub>
      </div>
      <Partners />
    </ConsoleGate>
  );
}

function Partners() {
  const { data, isPending, error, refetch } = useQuery(adminPartnersQuery);

  if (isPending) {
    return (
      <div style={{ marginTop: 16 }}>
        <SkeletonRows count={3} />
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

  const active = data.filter((row) => row.is_active);
  const inactive = data.filter((row) => !row.is_active);
  if (data.length === 0) {
    return (
      <Hint>
        <Trans>Карточек партнёров пока нет.</Trans>
      </Hint>
    );
  }
  return (
    <>
      {active.length > 0 ? (
        <>
          <Label>
            <Trans>Активные</Trans>
          </Label>
          <Rows>
            {active.map((row) => (
              <Placement key={row.placement_id} row={row} />
            ))}
          </Rows>
        </>
      ) : null}
      {inactive.length > 0 ? (
        <>
          <Label>
            <Trans>Выключенные</Trans>
          </Label>
          <Rows>
            {inactive.map((row) => (
              <Placement key={row.placement_id} row={row} />
            ))}
          </Rows>
        </>
      ) : null}
    </>
  );
}

function Placement({ row }: { row: AdminPlacement }) {
  const { i18n } = useLingui();
  const rate = clickRate(row.impressions, row.clicks, i18n.locale);
  return (
    <Row
      leading={
        <Tile tone={row.is_active ? 2 : 5}>
          <Letters text={row.partner.slice(0, 2).toUpperCase()} />
        </Tile>
      }
      title={row.title || row.partner}
      hint={
        <>
          {row.partner} · <SlotName slot={row.slot as PlacementSlot} />
        </>
      }
      trailing={
        <span className={ui.figure}>
          <b>{i18n.number(row.impressions)}</b>
          <small>
            {i18n.number(row.clicks)}
            {rate ? ` · ${rate}` : ''}
          </small>
        </span>
      }
    />
  );
}

/** Where a placement shows, in the words of the ads page. */
function SlotName({ slot }: { slot: PlacementSlot }) {
  switch (slot) {
    case 'screen_life':
      return <Trans>«Не про учёбу»</Trans>;
    case 'screen_nostrification':
      return <Trans>рядом с нострификацией</Trans>;
    case 'screen_languages':
      return <Trans>рядом с языками</Trans>;
    case 'screen_search_empty':
      return <Trans>когда поиск пуст</Trans>;
    case 'after_request_created':
      return <Trans>после заявки</Trans>;
    case 'profile_footer':
      return <Trans>в профиле</Trans>;
  }
}
