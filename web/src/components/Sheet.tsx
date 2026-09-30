/**
 * A panel that comes up from the bottom edge.
 *
 * Used where a question has three or four answers and a whole screen would be
 * too much ceremony: which language, what kind of thing you are posting. The
 * answer arrives without losing the screen behind it, which is the point —
 * navigating away to choose a language and navigating back is two more taps
 * than the choice is worth.
 */

import { type ReactNode, useEffect } from 'react';

import { CheckIcon } from './icons';
import css from './ui.module.css';

export function Sheet({
  title,
  onClose,
  closeLabel,
  children,
}: {
  title: ReactNode;
  onClose: () => void;
  /** For the scrim, which is a button and would otherwise be unnamed. */
  closeLabel: string;
  children: ReactNode;
}) {
  // Escape closes it. Bound to the document rather than to the panel because
  // nothing inside it is focused when it opens, so a key handler on the panel
  // would never hear anything.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <>
      <button
        type="button"
        className={css.scrim}
        aria-label={closeLabel}
        onClick={onClose}
      />
      <div className={css.sheet} role="dialog" aria-modal="true">
        <span className={css.grabber} />
        <span className={css.sheetTitle}>{title}</span>
        {children}
      </div>
    </>
  );
}

export function Pick({
  leading,
  name,
  hint,
  selected = false,
  onClick,
}: {
  leading?: ReactNode;
  name: ReactNode;
  hint?: ReactNode;
  selected?: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" className={css.pick} aria-pressed={selected} onClick={onClick}>
      {leading}
      <span className={css.pickBody}>
        <span className={css.pickName}>{name}</span>
        {hint ? <span className={css.pickHint}>{hint}</span> : null}
      </span>
      {selected ? <CheckIcon size={17} className={css.pickCheck} /> : null}
    </button>
  );
}
