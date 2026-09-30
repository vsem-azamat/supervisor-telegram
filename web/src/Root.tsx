import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { Outlet } from 'react-router';

import { useBackButton } from '@/hooks/useTelegram';
import { activateLocale, isLocale } from '@/i18n';
import { api } from '@/lib/api';

/**
 * The shell every route renders inside.
 *
 * Deliberately bare: no chrome, no styling. Its one job is to wire the Telegram
 * back button to the router, which has to happen above the routes and below the
 * router so it can see the navigation history.
 */
export default function Root() {
  useBackButton();

  // Telegram's language_code seeds the interface before the first paint, but
  // the account may have chosen otherwise, and the API localises subject and
  // faculty names by the stored value. Following it here is what stops a
  // Russian interface listing Czech names.
  const { data: me } = useQuery({
    queryKey: ['me'],
    queryFn: ({ signal }) => api.getMe(signal),
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!me || !isLocale(me.ui_lang)) return;
    void activateLocale(me.ui_lang).then(() => {
      document.documentElement.lang = me.ui_lang;
    });
  }, [me]);

  return <Outlet />;
}
