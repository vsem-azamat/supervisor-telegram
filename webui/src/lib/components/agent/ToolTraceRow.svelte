<script lang="ts">
	type Props = {
		label: string;
		toolName: string;
		state: 'pending' | 'done';
		preview?: string;
	};
	let { label, toolName, state, preview }: Props = $props();
</script>

<div class="flex items-baseline gap-2 rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-xs">
	<span class="shrink-0">🔧</span>
	<span class="font-medium text-zinc-700">{label}</span>
	<span class="text-zinc-400">{toolName}</span>
	<span class="ml-auto shrink-0 {state === 'done' ? 'text-emerald-600' : 'text-amber-600'}">
		{state === 'done' ? '✓' : '⏳'}
	</span>
	{#if preview && state === 'done'}
		<div class="basis-full pl-5 text-zinc-500">{preview}</div>
	{/if}
</div>
