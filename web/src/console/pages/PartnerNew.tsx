import { Trans, useLingui } from '@lingui/react/macro';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useId, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';

import { PartnerBlock } from '@/components/PartnerBlock';
import { Action, Actions, Hint, Label, Sub, Title, ui } from '@/components/Ui';
import { ConsoleGate } from '@/console/ConsoleGate';
import {
  CARD_LIMITS,
  type CardDraft,
  type CardField,
  cardBody,
  cardProblems,
  EMPTY_CARD,
} from '@/console/partners';
import { adminPartnersQuery } from '@/console/queries';
import { ApiError, api, UnauthorizedError } from '@/lib/api';

/**
 * A new partner card for the Life screen, drawn as students will see it
 * while it is being written. See teachers-catalog's docs/architecture.md.
 */
export default function ConsolePartnerNewPage() {
  return (
    <ConsoleGate>
      <Title>
        <Trans>Новая карточка</Trans>
      </Title>
      <div style={{ marginTop: 6 }}>
        <Sub>
          <Trans>
            Встанет первой в разделе «Не про учёбу». Там видно три карточки: самая нижняя
            уйдёт, пока другую не выключат.
          </Trans>
        </Sub>
      </div>
      <CardForm />
    </ConsoleGate>
  );
}

/** Why the card did not go out, in terms of what to do next. */
function SaveFailure({ error }: { error: unknown }) {
  if (error instanceof UnauthorizedError) {
    return <Trans>Вход устарел: откройте приложение заново.</Trans>;
  }
  if (error instanceof ApiError && error.status === 403) {
    return <Trans>Этого аккаунта нет среди операторов каталога.</Trans>;
  }
  if (error instanceof ApiError && error.status === 422) {
    return <Trans>Каталог не принял карточку: проверьте ссылку и длину полей.</Trans>;
  }
  // The card may have been saved with the answer lost on the way back.
  return (
    <Trans>
      Ответ не дошёл. Прежде чем пробовать снова, проверьте список: карточка могла
      сохраниться.
    </Trans>
  );
}

function CardForm() {
  const { t } = useLingui();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<CardDraft>(EMPTY_CARD);
  const [tried, setTried] = useState(false);
  const problems = cardProblems(draft);
  const create = useMutation({
    mutationFn: () => api.createPlacement(cardBody(draft)),
    // Settled, not only succeeded: an answer lost after the save is still a card.
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: adminPartnersQuery.queryKey });
      void queryClient.invalidateQueries({ queryKey: ['placements'] });
    },
    onSuccess: () => {
      // Back to the list it came from, so Telegram's back button does not land on it twice.
      if (location.key !== 'default') navigate(-1);
      else navigate('/console/partners', { replace: true });
    },
  });
  const set = (key: CardField) => (value: string) =>
    setDraft((current) => ({ ...current, [key]: value }));
  // Said once somebody tried to save, not while they are still typing.
  const wrong = (field: CardField) => tried && problems.includes(field);
  const tooLong = <Trans>Слишком длинно для каталога.</Trans>;

  return (
    <>
      <Field
        label={t`Партнёр`}
        value={draft.partner}
        onChange={set('partner')}
        placeholder={t`например: Pojišťovna VZP`}
        limit={CARD_LIMITS.partner}
        problem={
          wrong('partner') ? (
            draft.partner.trim() ? (
              tooLong
            ) : (
              <Trans>Нужно название.</Trans>
            )
          ) : null
        }
      />
      <Field
        label={t`Ссылка`}
        value={draft.url}
        onChange={set('url')}
        placeholder="https://…"
        limit={CARD_LIMITS.url}
        inputMode="url"
        problem={
          wrong('url') ? (
            <Trans>
              Ссылка должна начинаться с https://, вести на сайт и быть без пробелов, не
              длиннее 1024 знаков.
            </Trans>
          ) : null
        }
      />
      <Field
        label={t`Заголовок`}
        value={draft.title}
        onChange={set('title')}
        placeholder={t`например: Страховка для студентов`}
        limit={CARD_LIMITS.title}
        problem={
          wrong('title') ? (
            draft.title.trim() ? (
              tooLong
            ) : (
              <Trans>Нужен заголовок.</Trans>
            )
          ) : null
        }
      />
      <Field
        label={t`Подзаголовок`}
        optional
        value={draft.subtitle}
        onChange={set('subtitle')}
        placeholder={t`например: подходит для продления визы`}
        limit={CARD_LIMITS.subtitle}
        problem={wrong('subtitle') ? tooLong : null}
      />
      <Field
        label={t`Цена`}
        optional
        value={draft.price_text}
        onChange={set('price_text')}
        placeholder={t`например: от 8 900 Kč`}
        limit={CARD_LIMITS.price_text}
        problem={wrong('price_text') ? tooLong : null}
      />
      <Field
        label={t`Пояснение над карточкой`}
        optional
        value={draft.context_note}
        onChange={set('context_note')}
        placeholder={t`например: Без страховки визу не продлят.`}
        limit={CARD_LIMITS.context_note}
        multiline
        problem={wrong('context_note') ? tooLong : null}
      />
      <Field
        label={t`Монограмма`}
        optional
        value={draft.logo_text}
        onChange={set('logo_text')}
        placeholder={t`например: VZP`}
        limit={CARD_LIMITS.logo_text}
        problem={wrong('logo_text') ? <Trans>Не больше четырёх букв.</Trans> : null}
      />

      <Label>
        <Trans>Как увидят студенты</Trans>
      </Label>
      <PartnerBlock
        preview
        placement={{
          id: 0,
          title: draft.title.trim() || t`Заголовок`,
          subtitle: draft.subtitle.trim() || null,
          price_text: draft.price_text.trim() || null,
          context_note: draft.context_note.trim() || null,
          logo_text: draft.logo_text.trim().toUpperCase() || null,
          logo_bg: null,
          url: draft.url.trim(),
        }}
      />

      {create.isError ? (
        <div style={{ marginTop: 12 }}>
          <Hint>
            <SaveFailure error={create.error} />
          </Hint>
        </div>
      ) : null}
      <div style={{ marginTop: 16 }}>
        <Actions>
          <Action
            disabled={create.isPending}
            onClick={() => {
              setTried(true);
              if (problems.length === 0) {
                create.mutate();
                return;
              }
              // The first thing to fix may be a screen above the button: take
              // the reader there, and a screen reader with them.
              requestAnimationFrame(() => {
                const first = document.querySelector<HTMLElement>(
                  '[aria-invalid="true"]',
                );
                first?.focus();
                first?.scrollIntoView({ block: 'center', behavior: 'smooth' });
              });
            }}
          >
            <Trans>Опубликовать</Trans>
          </Action>
        </Actions>
      </div>
    </>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  limit,
  inputMode,
  optional = false,
  multiline = false,
  problem = null,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  /** The catalog's limit. The input allows more, so a paste is refused, not cut. */
  limit: number;
  inputMode?: 'url';
  optional?: boolean;
  multiline?: boolean;
  problem?: ReactNode;
}) {
  const id = useId();
  const hint = `${id}-problem`;
  const common = {
    id,
    value,
    placeholder,
    maxLength: limit * 2 + 16,
    'aria-invalid': problem ? true : undefined,
    'aria-describedby': problem ? hint : undefined,
  };
  return (
    <>
      <Label aside={optional ? <Trans>необязательно</Trans> : null}>
        <label htmlFor={id}>{label}</label>
      </Label>
      <div
        className={ui.field}
        style={multiline ? { alignItems: 'flex-start' } : undefined}
      >
        {multiline ? (
          <textarea
            {...common}
            onChange={(event) => onChange(event.target.value)}
            rows={3}
            style={{ all: 'unset', width: '100%', resize: 'none', lineHeight: 1.5 }}
          />
        ) : (
          <input
            {...common}
            onChange={(event) => onChange(event.target.value)}
            inputMode={inputMode}
            style={{ all: 'unset', flex: 1, minWidth: 0 }}
          />
        )}
      </div>
      {problem ? (
        <div id={hint} style={{ marginTop: 6 }}>
          <Hint>{problem}</Hint>
        </div>
      ) : null}
    </>
  );
}
