<script lang="ts">
	import { Badge } from '$lib/components/ui/badge/index.js';
	import Tile from './Tile.svelte';

	type Props = { title: string; phase: number; hint?: string };
	let { title, phase, hint }: Props = $props();
</script>

<Tile {title}>
	{#snippet action()}
		<Badge variant="secondary" class="text-[10px]">P{phase}</Badge>
	{/snippet}
	<p class="text-xs text-zinc-500">{hint ?? 'Coming in Phase ' + phase + '.'}</p>
</Tile>
