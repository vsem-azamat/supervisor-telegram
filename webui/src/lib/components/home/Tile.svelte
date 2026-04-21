<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js';
	import type { Snippet } from 'svelte';

	type Props = { title: string; children: Snippet; action?: Snippet };
	let { title, children, action }: Props = $props();
</script>

<Card.Root class="h-full">
	<Card.Header class="flex flex-row items-center justify-between space-y-0 pb-2">
		<Card.Title class="text-sm font-medium text-zinc-700">{title}</Card.Title>
		{#if action}{@render action()}{/if}
	</Card.Header>
	<Card.Content>
		{@render children()}
	</Card.Content>
</Card.Root>
