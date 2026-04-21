<script lang="ts">
	type Slice = { label: string; value: number };
	type Props = {
		slices: Slice[];
		size?: number;
		strokeWidth?: number;
		empty?: string;
		centerValue?: string | number;
		centerLabel?: string;
	};
	let {
		slices,
		size = 140,
		strokeWidth = 18,
		empty = 'No data',
		centerValue,
		centerLabel
	}: Props = $props();

	const palette = [
		'#27272a',
		'#52525b',
		'#71717a',
		'#a1a1aa',
		'#d4d4d8',
		'#10b981',
		'#0ea5e9',
		'#f59e0b'
	];

	const nonZero = $derived(slices.filter((s) => s.value > 0));
	const total = $derived(nonZero.reduce((a, s) => a + s.value, 0));
	const r = $derived((size - strokeWidth) / 2);
	const cx = $derived(size / 2);
	const cy = $derived(size / 2);
	const circumference = $derived(2 * Math.PI * r);

	const arcs = $derived.by(() => {
		let cumulative = 0;
		return nonZero.map((s, i) => {
			const fraction = s.value / total;
			const dash = fraction * circumference;
			const offset = -cumulative * circumference;
			cumulative += fraction;
			return {
				key: `${s.label}-${i}`,
				label: s.label,
				value: s.value,
				color: palette[i % palette.length],
				dasharray: `${dash} ${circumference - dash}`,
				dashoffset: offset
			};
		});
	});
</script>

{#if nonZero.length === 0}
	<p class="text-xs text-zinc-500">{empty}</p>
{:else}
	<div class="flex items-center gap-4">
		<svg width={size} height={size} viewBox="0 0 {size} {size}" class="shrink-0">
			<circle {cx} {cy} r={r} fill="none" stroke="#f4f4f5" stroke-width={strokeWidth} />
			{#each arcs as arc (arc.key)}
				<circle
					{cx}
					{cy}
					r={r}
					fill="none"
					stroke={arc.color}
					stroke-width={strokeWidth}
					stroke-dasharray={arc.dasharray}
					stroke-dashoffset={arc.dashoffset}
					transform="rotate(-90 {cx} {cy})"
				>
					<title>{arc.label}: {arc.value.toLocaleString()}</title>
				</circle>
			{/each}
			{#if centerValue !== undefined}
				<text
					x={cx}
					y={cy}
					text-anchor="middle"
					dominant-baseline="central"
					class="fill-zinc-900 text-xl font-semibold"
				>
					{centerValue}
				</text>
				{#if centerLabel}
					<text
						x={cx}
						y={cy + 14}
						text-anchor="middle"
						dominant-baseline="central"
						class="fill-zinc-500 text-[10px] uppercase tracking-wider"
					>
						{centerLabel}
					</text>
				{/if}
			{/if}
		</svg>
		<ul class="min-w-0 flex-1 space-y-1.5 text-xs">
			{#each arcs as arc (arc.key)}
				<li class="flex items-center justify-between gap-2">
					<span class="flex min-w-0 items-center gap-2">
						<span
							class="size-2.5 shrink-0 rounded-sm"
							style:background-color={arc.color}
						></span>
						<span class="truncate text-zinc-700" title={arc.label}>{arc.label}</span>
					</span>
					<span class="shrink-0 tabular-nums text-zinc-500">{arc.value}</span>
				</li>
			{/each}
		</ul>
	</div>
{/if}
