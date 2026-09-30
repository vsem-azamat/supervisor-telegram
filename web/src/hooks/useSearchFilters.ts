import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { api } from '@/lib/api';
import type { SearchParams } from '@/lib/types';

/**
 * The filters a query string describes, as the search endpoint takes them.
 *
 * Shared by the two screens that read the same query string: the search screen,
 * which shows how many people it finds and the first two of them, and the
 * results screen, which lists them. Those two numbers have to be the same
 * number — that is the whole point of showing one at all — and a second copy of
 * this mapping is the way they would stop being.
 *
 * The clarifying answer travels as a service *code* rather than an id, because
 * the screen that asks the question has no reason to hold the reference list.
 * Resolving it needs that list, so `filters` is null until it is here: filtering
 * by nothing instead would count everyone who teaches the subject and then hand
 * over to a screen that does apply the filter.
 */
export function useSearchFilters(query: string | URLSearchParams): {
  filters: SearchParams | null;
  isError: boolean;
} {
  // The string is the input, whichever shape it arrived in: one caller builds a
  // fresh URLSearchParams on every render, and that object is a new identity
  // each time even when nothing about the query changed.
  const key = typeof query === 'string' ? query : query.toString();
  const params = useMemo(() => new URLSearchParams(key), [key]);

  const code = params.get('service');
  // An explicit id in the query string is already the answer, so a code beside
  // it is nothing to wait for. Without this a link carrying both would block on
  // a lookup it does not need, and fail with it.
  const lookup = code && !params.get('service_type_id') ? code : null;

  const { data, isError } = useQuery({
    queryKey: ['service-types'],
    queryFn: ({ signal }) => api.getServiceTypes(signal),
    staleTime: 60 * 60 * 1000,
    enabled: lookup !== null,
  });

  const filters = useMemo(() => {
    const byCode = lookup ? data?.find((type) => type.code === lookup)?.id : undefined;
    if (lookup && byCode === undefined) return null;

    return {
      subject_id: numeric(params.get('subject_id')),
      institution_id: numeric(params.get('institution_id')),
      service_type_id: numeric(params.get('service_type_id')) ?? byCode,
      max_price: numeric(params.get('max_price')),
    };
  }, [params, lookup, data]);

  // Only when this hook is the one that asked. `['service-types']` is a key
  // several screens share, so an unguarded flag would hand a failure caused by
  // the offer screen to a search that needs no reference data at all — and both
  // screens would report a failure while their own request had succeeded.
  return { filters, isError: isError && lookup !== null };
}

function numeric(value: string | null): number | undefined {
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}
