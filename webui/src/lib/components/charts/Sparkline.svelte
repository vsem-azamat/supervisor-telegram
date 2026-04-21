<script lang="ts">
	type Props = {
		values: number[];
		width?: number;
		height?: number;
		strokeClass?: string;
		fillClass?: string;
	};
	let {
		values,
		width = 240,
		height = 48,
		strokeClass = 'text-emerald-600',
		fillClass = 'text-emerald-600/10'
	}: Props = $props();

	const path = $derived.by(() => {
		if (values.length === 0) return { line: '', area: '' };
		const max = Math.max(...values);
		const min = Math.min(...values);
		const span = Math.max(1, max - min);
		const denom = Math.max(1, values.length - 1);
		const pts = values.map((v, i) => {
			const x = (i / denom) * width;
			const y = height - ((v - min) / span) * height;
			return [x, y] as const;
		});
		const line = pts
			.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
			.join(' ');
		const area = `${line} L${width.toFixed(1)},${height} L0,${height} Z`;
		return { line, area };
	});
</script>

{#if values.length > 0}
	<svg {width} {height} viewBox="0 0 {width} {height}" preserveAspectRatio="none">
		<path d={path.area} class={fillClass} fill="currentColor" stroke="none" />
		<path d={path.line} class={strokeClass} fill="none" stroke="currentColor" stroke-width="1.5" />
	</svg>
{/if}
