/** The console's partner card form, apart from the screen. */

export interface CardDraft {
  partner: string;
  url: string;
  title: string;
  subtitle: string;
  price_text: string;
  context_note: string;
  logo_text: string;
}

export type CardField = keyof CardDraft;

export const EMPTY_CARD: CardDraft = {
  partner: '',
  url: 'https://',
  title: '',
  subtitle: '',
  price_text: '',
  context_note: '',
  logo_text: '',
};

/** The catalog's limits, field by field (AdminPlacementIn). */
export const CARD_LIMITS: Record<CardField, number> = {
  partner: 200,
  url: 1024,
  title: 200,
  subtitle: 240,
  price_text: 64,
  context_note: 600,
  logo_text: 4,
};

const REQUIRED: CardField[] = ['partner', 'url', 'title'];

/** Anything a link cannot hold: blanks and control characters. */
const NOT_IN_A_LINK = /[\s\p{Cc}]/u;

/**
 * The fields that stop the card from being saved, by the catalog's rules: a
 * name and a title, an https link with a host and nothing blank in it, and
 * every field within its length. The monogram is measured upper-cased, as
 * it is sent: «ß» becomes two letters.
 */
export function cardProblems(draft: CardDraft): CardField[] {
  const sent = cardBody(draft);
  const problems = new Set<CardField>();
  for (const field of REQUIRED) {
    if (!sent[field]) problems.add(field);
  }
  // Checked on the text itself, not through URL(), which would repair
  // «https:///a.test» into a link the server then refuses.
  const host = /^https:\/\/([^/?#]+)/.exec(sent.url)?.[1] ?? '';
  if (!host || NOT_IN_A_LINK.test(sent.url)) problems.add('url');
  for (const [field, limit] of Object.entries(CARD_LIMITS) as [CardField, number][]) {
    if ((sent[field] ?? '').length > limit) problems.add(field);
  }
  // In the form's order, so the first one is the first to fix.
  return (Object.keys(CARD_LIMITS) as CardField[]).filter((field) => problems.has(field));
}

/** The body the catalog takes: trimmed, with an empty optional field as null. */
export function cardBody(draft: CardDraft) {
  const optional = (value: string) => value.trim() || null;
  return {
    partner: draft.partner.trim(),
    url: draft.url.trim(),
    title: draft.title.trim(),
    subtitle: optional(draft.subtitle),
    price_text: optional(draft.price_text),
    context_note: optional(draft.context_note),
    logo_text: optional(draft.logo_text.toUpperCase()),
  };
}
