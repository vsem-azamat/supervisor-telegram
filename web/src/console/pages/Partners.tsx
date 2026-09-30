import { Trans, useLingui } from '@lingui/react/macro';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router';

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
import { adminPartnersQuery } from '@/console/queries';
import { clickRate } from '@/console/session';
import { hapticSelection } from '@/hooks/useTelegram';
import { api } from '@/lib/api';
import type { AdminPlacement, PlacementSlot } from '@/lib/generated/types.gen';

/**
 * Partner placements and how they did over the last month; a new one, and
 * a tap on one to switch it off or on. Nothing is deleted, so a stopped card
 * keeps its numbers. See teachers-catalog's docs/architecture.md.
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
      <NewCard />
      <Partners />
    </ConsoleGate>
  );
}

function NewCard() {
  const navigate = useNavigate();
  return (
    <div style={{ marginTop: 14 }}>
      <Actions>
        <Action
          onClick={() => {
            hapticSelection();
            navigate('/console/partners/new');
          }}
        >
          <Trans>Добавить карточку</Trans>
        </Action>
      </Actions>
    </div>
  );
}

function Partners() {
  const { t } = useLingui();
  const queryClient = useQueryClient();
  const { data, isPending, error, refetch } = useQuery(adminPartnersQuery);
  const [picked, setPicked] = useState<AdminPlacement | null>(null);
  const toggle = useMutation({
    mutationFn: (row: AdminPlacement) =>
      api.switchPlacement(row.placement_id, !row.is_active),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: adminPartnersQuery.queryKey });
      void queryClient.invalidateQueries({ queryKey: ['placements'] });
      setPicked(null);
    },
  });
  const close = () => {
    if (toggle.isPending) return;
    toggle.reset();
    setPicked(null);
  };

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
              <Placement key={row.placement_id} row={row} onPick={setPicked} />
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
              <Placement key={row.placement_id} row={row} onPick={setPicked} />
            ))}
          </Rows>
        </>
      ) : null}
      {picked ? (
        <Sheet
          title={picked.is_active ? t`Выключить карточку?` : t`Включить карточку?`}
          closeLabel={t`Отмена`}
          onClose={close}
        >
          <Sub>
            {picked.title ? `${picked.title} · ${picked.partner}` : picked.partner}
          </Sub>
          <Hint>
            {picked.is_active ? (
              <Trans>Студенты перестанут её видеть. Показы и клики сохранятся.</Trans>
            ) : (
              <Trans>Вернётся на своё место по приоритету.</Trans>
            )}
          </Hint>
          {toggle.isError ? (
            <Hint>
              <Trans>Не получилось. Попробуйте ещё раз.</Trans>
            </Hint>
          ) : null}
          <div className={ui.actionsStacked}>
            <Action disabled={toggle.isPending} onClick={() => toggle.mutate(picked)}>
              {picked.is_active ? <Trans>Выключить</Trans> : <Trans>Включить</Trans>}
            </Action>
            {/* Not while the switch is on its way: closing would not stop it. */}
            <Action quiet disabled={toggle.isPending} onClick={close}>
              <Trans>Отмена</Trans>
            </Action>
          </div>
        </Sheet>
      ) : null}
    </>
  );
}

function Placement({
  row,
  onPick,
}: {
  row: AdminPlacement;
  onPick: (row: AdminPlacement) => void;
}) {
  const { i18n } = useLingui();
  const rate = clickRate(row.impressions, row.clicks, i18n.locale);
  return (
    <Row
      onClick={() => {
        hapticSelection();
        onPick(row);
      }}
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
