import { Trans } from '@lingui/react/macro';
import { useQuery } from '@tanstack/react-query';

import { AppHeader } from '@/components/AppHeader';
import { PartnerBlock } from '@/components/PartnerBlock';
import { Empty, Hint, Label, Screen, SkeletonRows, Sub, Title } from '@/components/Ui';
import { api } from '@/lib/api';

/**
 * The things a foreign student here has to buy anyway.
 *
 * Insurance, a language course that carries a visa, a bank statement, a sworn
 * translation. None of it is ours and all of it is labelled. It sits on a page
 * that is useful even if nothing is tapped — the deadlines are the reason to
 * come, the offers are attached to them — because a page that only sells gets
 * visited once.
 */
export default function LifePage() {
  const { data, isPending, isError } = useQuery({
    queryKey: ['placements', 'screen_life'],
    queryFn: ({ signal }) => api.getPlacements({ slot: 'screen_life' }, signal),
  });

  return (
    <Screen>
      <AppHeader />
      <Title>
        <Trans>Не про учёбу</Trans>
      </Title>
      <div style={{ marginTop: 6 }}>
        <Sub>
          <Trans>
            Но без этого не доучишься. Сроки и требования — наши, предложения —
            партнёрские.
          </Trans>
        </Sub>
      </div>

      {isPending ? (
        <>
          <Label>
            <Trans>Загружаем</Trans>
          </Label>
          <SkeletonRows count={3} />
        </>
      ) : isError || data.length === 0 ? (
        <Empty
          title={<Trans>Пока пусто</Trans>}
          body={<Trans>Здесь появятся страховка, визы, банк и переводы.</Trans>}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 18 }}>
          {data.map((placement) => (
            <PartnerBlock key={placement.id} placement={placement} />
          ))}
        </div>
      )}

      <div style={{ marginTop: 18 }}>
        <Hint>
          <Trans>
            Это не наши услуги. Мы получаем комиссию с партнёра, со студента — ничего.
          </Trans>
        </Hint>
      </div>
    </Screen>
  );
}
