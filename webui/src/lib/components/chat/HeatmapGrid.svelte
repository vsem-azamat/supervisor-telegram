<script lang="ts">
	import type { components } from '$lib/api/types';

	type HeatmapCell = components['schemas']['HeatmapCell'];
	type Props = { cells: HeatmapCell[] };
	let { cells }: Props = $props();

	const weekdayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

	const countByKey = $derived.by(() => {
		const map = new Map<string, number>();
		for (const c of cells) map.set(`${c.weekday}:${c.hour}`, c.count);
		return map;
	});

	const maxCount = $derived(Math.max(1, ...cells.map((c) => c.count)));

	function cellOpacity(weekday: number, hour: number): number {
		const n = countByKey.get(`${weekday}:${hour}`) ?? 0;
		if (n === 0) return 0;
		// gamma-ish scale so modest activity is visible
		return 0.15 + 0.85 * Math.sqrt(n / maxCount);
	}

	function cellCount(weekday: number, hour: number): number {
		return countByKey.get(`${weekday}:${hour}`) ?? 0;
	}
</script>

<div class="space-y-1">
	<div class="grid grid-cols-[3rem_repeat(24,1fr)] items-center gap-[2px] text-[10px] text-zinc-500">
		<div></div>
		{#each Array(24) as _, h}
			<div class="text-center">{h % 6 === 0 ? h : ''}</div>
		{/each}
	</div>

	{#each weekdayLabels as label, weekday}
		<div class="grid grid-cols-[3rem_repeat(24,1fr)] items-center gap-[2px]">
			<div class="text-[10px] text-zinc-500">{label}</div>
			{#each Array(24) as _, hour}
				<div
					class="aspect-square rounded-sm border border-zinc-200 bg-emerald-500"
					style:opacity={cellOpacity(weekday, hour)}
					title="{label} {hour}:00 — {cellCount(weekday, hour)}"
				></div>
			{/each}
		</div>
	{/each}
</div>
