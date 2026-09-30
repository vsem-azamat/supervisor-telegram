import { Trans } from '@lingui/react/macro';
import { useQuery } from '@tanstack/react-query';
import { openTelegramLink } from '@tma.js/sdk-react';

import { api } from '@/lib/api';

import { Action, Actions } from './Ui';

/**
 * «Написать в Telegram», when somebody is there to answer.
 *
 * The address is `ADS_CONTACT` on the server. Unset, there is no button: a
 * page that invites a business to write to nobody is worse than one that
 * does not invite it. See teachers-catalog's docs/architecture.md.
 */
export function AdsContact() {
  const { data } = useQuery({
    queryKey: ['ads'],
    queryFn: ({ signal }) => api.getAds(signal),
    staleTime: 60 * 60_000,
  });
  const url = data?.contact_url;
  if (!url) return null;
  return (
    <div style={{ marginTop: 22 }}>
      <Actions>
        <Action onClick={() => openTelegramLink(url)}>
          <Trans>Написать в Telegram</Trans>
        </Action>
      </Actions>
    </div>
  );
}
