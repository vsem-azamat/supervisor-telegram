import { Trans } from '@lingui/react/macro';
import { useQuery } from '@tanstack/react-query';

import { AdsContact } from '@/components/AdsContact';
import { AppHeader } from '@/components/AppHeader';
import { PartnerBlock } from '@/components/PartnerBlock';
import { Label, Row, Rows, Screen, Sub, Title } from '@/components/Ui';
import { api } from '@/lib/api';

/**
 * A card in the app: what it looks like and where it appears.
 *
 * The example is a real placement from «Не про учёбу» when there is one, so
 * what a business is shown is what students see. With none, the page says
 * where cards appear and shows no invented one.
 */
export default function AdsAppPage() {
  const { data } = useQuery({
    // A preview: shown to a business, so it must not count as a student's
    // impression. Its own key, so it never shares a cache with «Не про учёбу».
    queryKey: ['placements', 'screen_life', 'preview'],
    queryFn: ({ signal }) =>
      api.getPlacements({ slot: 'screen_life', preview: true }, signal),
  });
  const example = data?.[0];

  return (
    <Screen>
      <AppHeader />
      <Title>
        <Trans>Карточка в приложении</Trans>
      </Title>
      <div style={{ marginTop: 6 }}>
        <Sub>
          <Trans>Показываем тому, кому она нужна сейчас, а не всем подряд.</Trans>
        </Sub>
      </div>

      {example ? (
        <>
          <Label>
            <Trans>Так она выглядит</Trans>
          </Label>
          <PartnerBlock placement={example} preview />
        </>
      ) : null}

      <Label>
        <Trans>Где её видно</Trans>
      </Label>
      <Rows>
        <Row
          title={<Trans>«Не про учёбу»</Trans>}
          hint={<Trans>страховка, визы, банк, переводы</Trans>}
        />
      </Rows>
      <div style={{ marginTop: 12 }}>
        <Sub>
          <Trans>Показ можно ограничить месяцами и языком интерфейса.</Trans>
        </Sub>
      </div>

      <AdsContact />
    </Screen>
  );
}
