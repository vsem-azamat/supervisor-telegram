import { Trans, useLingui } from '@lingui/react/macro';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useState } from 'react';
import { useNavigate } from 'react-router';

import { PartnerBlock } from '@/components/PartnerBlock';
import { Action, Actions, Hint, Label, Sub, Title, ui } from '@/components/Ui';
import { ConsoleGate } from '@/console/ConsoleGate';
import {
  type CardDraft,
  type CardProblem,
  cardBody,
  cardProblems,
  EMPTY_CARD,
} from '@/console/partners';
import { adminPartnersQuery } from '@/console/queries';
import { api } from '@/lib/api';

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
            Встанет первой на вкладке «Не про учёбу». Там видно три карточки: самая нижняя
            уйдёт, пока другую не выключат.
          </Trans>
        </Sub>
      </div>
      <CardForm />
    </ConsoleGate>
  );
}

function CardForm() {
  const { t } = useLingui();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<CardDraft>(EMPTY_CARD);
  const [tried, setTried] = useState(false);
  const problems = cardProblems(draft);
  const create = useMutation({
    mutationFn: () => api.createPlacement(cardBody(draft)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: adminPartnersQuery.queryKey });
      void queryClient.invalidateQueries({ queryKey: ['placements'] });
      navigate('/console/partners', { replace: true });
    },
  });
  const set = (key: keyof CardDraft) => (value: string) =>
    setDraft((current) => ({ ...current, [key]: value }));
  // Said once somebody tried to save, not while they are still typing.
  const wrong = (problem: CardProblem) => tried && problems.includes(problem);

  return (
    <>
      <Field
        label={t`Партнёр`}
        value={draft.partner}
        onChange={set('partner')}
        placeholder={t`например: Pojišťovna VZP`}
        maxLength={200}
        problem={wrong('partner') ? <Trans>Нужно название.</Trans> : null}
      />
      <Field
        label={t`Ссылка`}
        value={draft.url}
        onChange={set('url')}
        placeholder="https://…"
        maxLength={1024}
        inputMode="url"
        problem={
          wrong('url') ? (
            <Trans>Ссылка должна начинаться с https:// и быть без пробелов.</Trans>
          ) : null
        }
      />
      <Field
        label={t`Заголовок`}
        value={draft.title}
        onChange={set('title')}
        placeholder={t`например: Страховка для студентов`}
        maxLength={200}
        problem={wrong('title') ? <Trans>Нужен заголовок.</Trans> : null}
      />
      <Field
        label={t`Подзаголовок`}
        value={draft.subtitle}
        onChange={set('subtitle')}
        placeholder={t`например: подходит для продления визы`}
        maxLength={240}
      />
      <Field
        label={t`Цена`}
        value={draft.price_text}
        onChange={set('price_text')}
        placeholder={t`например: от 8 900 Kč`}
        maxLength={64}
      />
      <Field
        label={t`Пояснение над карточкой`}
        value={draft.context_note}
        onChange={set('context_note')}
        placeholder={t`например: Без страховки визу не продлят.`}
        maxLength={600}
        multiline
      />
      <Field
        label={t`Монограмма`}
        value={draft.logo_text}
        onChange={set('logo_text')}
        placeholder={t`например: VZP`}
        maxLength={4}
        problem={wrong('logo') ? <Trans>Не больше четырёх букв.</Trans> : null}
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
            <Trans>Не сохранилось. Проверьте поля и попробуйте ещё раз.</Trans>
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
              // The first thing to fix may be a screen above the button.
              requestAnimationFrame(() =>
                document
                  .querySelector('[data-problem]')
                  ?.scrollIntoView({ block: 'center', behavior: 'smooth' }),
              );
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
  maxLength,
  inputMode,
  multiline = false,
  problem = null,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  maxLength: number;
  inputMode?: 'url';
  multiline?: boolean;
  problem?: ReactNode;
}) {
  return (
    <>
      <Label>{label}</Label>
      <div
        className={ui.field}
        style={multiline ? { alignItems: 'flex-start' } : undefined}
      >
        {multiline ? (
          <textarea
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={placeholder}
            aria-label={label}
            rows={3}
            maxLength={maxLength}
            style={{ all: 'unset', width: '100%', resize: 'none', lineHeight: 1.5 }}
          />
        ) : (
          <input
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={placeholder}
            maxLength={maxLength}
            inputMode={inputMode}
            aria-label={label}
            style={{ all: 'unset', flex: 1, minWidth: 0 }}
          />
        )}
      </div>
      {problem ? (
        <div style={{ marginTop: 6 }} data-problem>
          <Hint>{problem}</Hint>
        </div>
      ) : null}
    </>
  );
}
