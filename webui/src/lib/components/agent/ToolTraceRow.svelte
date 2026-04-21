<script lang="ts">
	type Props = {
		label: string;
		toolName: string;
		status: 'pending' | 'done';
		preview?: string;
	};
	let { label, toolName, status, preview }: Props = $props();

	let expanded = $state(false);
	const hasOverflow = $derived((preview?.length ?? 0) > 80);
</script>

<div class="rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-xs">
	<div class="flex items-baseline gap-2">
		<span class="shrink-0">🔧</span>
		<span class="font-medium text-zinc-700">{label}</span>
		<span class="text-zinc-400">{toolName}</span>
		<span class="ml-auto shrink-0 {status === 'done' ? 'text-emerald-600' : 'text-amber-600'}">
			{status === 'done' ? '✓' : '⏳'}
		</span>
		{#if hasOverflow && status === 'done'}
			<button
				type="button"
				class="shrink-0 text-zinc-400 hover:text-zinc-700"
				aria-label={expanded ? 'Hide details' : 'Show details'}
				onclick={() => (expanded = !expanded)}
			>
				{expanded ? '▾' : '▸'}
			</button>
		{/if}
	</div>
	{#if preview && status === 'done'}
		<div class="mt-1 pl-5 text-zinc-500 {expanded ? '' : 'line-clamp-1'}">
			{preview}
		</div>
	{/if}
</div>
