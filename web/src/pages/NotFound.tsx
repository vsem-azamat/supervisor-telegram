import { Trans } from '@lingui/react/macro';

import { AppHeader } from '@/components/AppHeader';
import { Screen, Sub, Title } from '@/components/Ui';

/**
 * The catch-all.
 *
 * A `<Screen>` like every other page, and not a bare div: the header, the
 * insets and the clearance at the foot are what every screen is entitled to,
 * and a page shaped unlike all the others is a page that every tool walking
 * them has to special-case — `scripts/check-scroll.mjs` measured this one as
 * spotless because it could not find a screen in it at all.
 */
export default function NotFoundPage() {
  return (
    <Screen>
      <AppHeader />
      <Title>
        <Trans>Такой страницы нет</Trans>
      </Title>
      <div style={{ marginTop: 6 }}>
        <Sub>
          <Trans>Ссылка устарела или в ней опечатка.</Trans>
        </Sub>
      </div>
    </Screen>
  );
}
