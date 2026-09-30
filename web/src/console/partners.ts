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

export type CardProblem = 'partner' | 'url' | 'title' | 'logo';

export const EMPTY_CARD: CardDraft = {
  partner: '',
  url: 'https://',
  title: '',
  subtitle: '',
  price_text: '',
  context_note: '',
  logo_text: '',
};

/**
 * What stops the card from being saved, by the catalog's own rules: a name,
 * a title, an https link with nothing blank in it, and a monogram of at most
 * four letters. Checked here so the button can say so before the server does.
 */
export function cardProblems(draft: CardDraft): CardProblem[] {
  const problems: CardProblem[] = [];
  if (!draft.partner.trim()) problems.push('partner');
  const url = draft.url.trim();
  let host = '';
  try {
    host = new URL(url).host;
  } catch {
    host = '';
  }
  if (!url.startsWith('https://') || !host || /\s/.test(url)) problems.push('url');
  if (!draft.title.trim()) problems.push('title');
  if (draft.logo_text.trim().length > 4) problems.push('logo');
  return problems;
}

/** The body the catalog takes: trimmed, with an empty optional field absent. */
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
