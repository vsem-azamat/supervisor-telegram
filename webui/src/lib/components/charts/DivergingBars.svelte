<script lang="ts">
	type Item = { label: string; value: number | null; secondary?: string };
	type Props = { items: Item[]; empty?: string };
	let { items, empty = 'No data' }: Props = $props();

	const max = $derived(
		Math.max(1, ...items.map((i) => Math.abs(i.value ?? 0)))
	);
</script>

{#if items.length === 0}
	<p class="text-xs text-zinc-500">{empty}</p>
{:else}
	<ul class="space-y-2">
		{#each items as item, i (i)}
			{@const v = item.value}
			{@const pct = v === null ? 0 : (Math.abs(v) / max) * 50}
			{@const positive = v !== null && v > 0}
			{@const zero = v === null || v === 0}
			<li class="space-y-1">
				<div class="flex items-baseline justify-between gap-2 text-xs">
					<span class="truncate text-zinc-700" title={item.label}>{item.label}</span>
					<span
						class="shrink-0 tabular-nums {v === null
							? 'text-zinc-400'
							: positive
								? 'text-emerald-600'
								: zero
									? 'text-zinc-500'
									: 'text-rose-600'}"
					>
						{item.secondary ?? (positive ? `+${v}` : `${v ?? '—'}`)}
					</span>
				</div>
				<div class="relative h-1.5 w-full overflow-hidden rounded-full bg-zinc-100">
					<div class="absolute top-0 bottom-0 left-1/2 w-px bg-zinc-300"></div>
					{#if !zero}
						<div
							class="absolute top-0 bottom-0 transition-[width,left] duration-300 {positive
								? 'rounded-r-full bg-emerald-500/80'
								: 'rounded-l-full bg-rose-500/80'}"
							style:left="{positive ? 50 : 50 - pct}%"
							style:width="{pct}%"
						></div>
					{/if}
				</div>
			</li>
		{/each}
	</ul>
{/if}
