/**
 * Contiguous runs of items that share a key.
 *
 * Kinds of help appear under their group heading in two components — the grid
 * of tiles, which draws the home screen and the screen where a service is
 * offered, and the screen where prices are set. All of them take the order the
 * server chose rather than sorting again here.
 *
 * Runs, not a lookup: a group that came back split shows up as two headings
 * instead of silently merging into one, which is the honest rendering of a
 * server that has gone wrong.
 */
export interface Run<T, K> {
  /** What every item in the run has in common. */
  value: K;
  /**
   * What to give React. One per run rather than one per value, because the
   * split group above has to survive as two headings — keyed by the value
   * alone it would hand React the same key twice and collapse into a warning.
   */
  id: string;
  items: T[];
}

// Runs are merged with ===, so the key is constrained to something that
// compares by value. Without that bound an object key would type-check and
// then give one run per item.
export function groupRuns<T, K extends PropertyKey>(
  items: T[],
  keyOf: (item: T) => K,
): Run<T, K>[] {
  const runs: Run<T, K>[] = [];
  for (const item of items) {
    const value = keyOf(item);
    const last = runs.at(-1);
    if (last && last.value === value) last.items.push(item);
    else runs.push({ value, id: `${String(value)}#${runs.length}`, items: [item] });
  }
  return runs;
}
