<script lang="ts">
	type Item = { label: string; value: number; secondary?: string; href?: string };
	type Props = {
		items: Item[];
		empty?: string;
		format?: (n: number) => string;
		max?: number;
	};
	let { items, empty = 'No data', format = (n) => n.toLocaleString(), max }: Props = $props();

	const computedMax = $derived(max ?? Math.max(1, ...items.map((i) => i.value)));
</script>

{#if items.length === 0}
	<p class="text-xs text-zinc-500">{empty}</p>
{:else}
	<ul class="space-y-2">
		{#each items as item, i (i)}
			{@const pct = (Math.max(0, item.value) / computedMax) * 100}
			<li>
				{#if item.href}
					<a
						href={item.href}
						class="block space-y-1 rounded-md px-1 py-0.5 -mx-1 hover:bg-zinc-50"
					>
						<div class="flex items-baseline justify-between gap-2 text-xs">
							<span class="truncate text-zinc-700" title={item.label}>{item.label}</span>
							<span class="shrink-0 tabular-nums text-zinc-500">
								{item.secondary ?? format(item.value)}
							</span>
						</div>
						<div class="h-1.5 w-full overflow-hidden rounded-full bg-zinc-100">
							<div
								class="h-full rounded-full bg-zinc-900/80 transition-[width] duration-300"
								style:width="{pct}%"
							></div>
						</div>
					</a>
				{:else}
					<div class="space-y-1">
						<div class="flex items-baseline justify-between gap-2 text-xs">
							<span class="truncate text-zinc-700" title={item.label}>{item.label}</span>
							<span class="shrink-0 tabular-nums text-zinc-500">
								{item.secondary ?? format(item.value)}
							</span>
						</div>
						<div class="h-1.5 w-full overflow-hidden rounded-full bg-zinc-100">
							<div
								class="h-full rounded-full bg-zinc-900/80 transition-[width] duration-300"
								style:width="{pct}%"
							></div>
						</div>
					</div>
				{/if}
			</li>
		{/each}
	</ul>
{/if}
