import type { ReactNode } from 'react';

import { iconForService } from '@/components/icons';
import { ServiceGroupLabel } from '@/components/Phrase';
import { Cell, Grid, Label, Tile } from '@/components/Ui';
import { groupRuns } from '@/lib/groups';
import type { ServiceGroup } from '@/lib/types';

/**
 * The tiles, on both screens that show them.
 *
 * The home screen and the screen where someone offers a service are the same
 * grid read in opposite directions — "who can help me with this" and "this is
 * what I can help with" — so they are one component. Two copies would drift the
 * first time a group was renamed, and the person who offers tutoring is the
 * person who was looking for it last term.
 *
 * Grouping happens here, off the `group` field, rather than being handed down
 * as nested arrays: the server already returns whole groups in order, and a
 * caller that had to pre-split them could get the split wrong without the
 * component noticing.
 *
 * Selection is keyed by `code`, not by id. `HomeSection` has no id — it is a
 * screen section, not a row — and both screens have to feed the same
 * component. `OfferPrices` maps the codes back to `service_type_id`.
 */

export interface ServiceTile {
  code: string;
  group: ServiceGroup;
  name: string;
  hint?: string | null;
  /** Which of the six tile colours. Comes from the server on both screens, so
   *  a category is the same colour in the catalog as where it is offered. */
  tone: number;
}

export function ServiceGrid<T extends ServiceTile>({
  items,
  selected,
  onToggle,
  onPick,
  renderTrailing,
  renderNote,
}: {
  items: T[];
  /** Present only when the grid is a multiple choice. */
  selected?: Set<string>;
  onToggle?: (code: string) => void;
  onPick?: (item: T) => void;
  /**
   * Home puts its counts and faces here without this file knowing about them.
   * `wide` is passed because a full-width cell has room for more of them.
   */
  renderTrailing?: (item: T, wide: boolean) => ReactNode;
  /** Something to say under one group's heading, before its tiles. */
  renderNote?: (group: ServiceGroup) => ReactNode;
}) {
  return (
    <>
      {groupRuns(items, (item) => item.group).map(
        ({ id, value: group, items: tiles }) => (
          <div key={id}>
            <Label>
              <ServiceGroupLabel group={group} />
            </Label>
            {renderNote?.(group)}
            <Grid>
              {tiles.map((item, index) => {
                const Icon = iconForService(item.code);
                const isOn = selected?.has(item.code) ?? false;
                // Two columns leave an odd group's last tile alone in its
                // row, which reads as something having failed to load.
                // Widening the first one makes the count even again.
                const wide = tiles.length % 2 === 1 && index === 0;
                return (
                  <Cell
                    key={item.code}
                    wide={wide}
                    onClick={() =>
                      onToggle ? onToggle(item.code) : onPick ? onPick(item) : undefined
                    }
                    selected={selected ? isOn : undefined}
                    leading={
                      <Tile tone={item.tone}>
                        <Icon size={19} />
                      </Tile>
                    }
                    title={item.name}
                    hint={item.hint ?? undefined}
                    trailing={renderTrailing?.(item, wide)}
                  />
                );
              })}
            </Grid>
          </div>
        ),
      )}
    </>
  );
}
