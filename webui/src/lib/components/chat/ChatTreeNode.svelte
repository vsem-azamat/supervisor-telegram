<script lang="ts">
	import { goto } from '$app/navigation';
	import type { components } from '$lib/api/types';
	import { untrack } from 'svelte';
	import Self from './ChatTreeNode.svelte';

	type Node = components['schemas']['ChatNode'];
	type Props = { node: Node; depth?: number };
	let { node, depth = 0 }: Props = $props();

	let expanded = $state(untrack(() => depth < 2));
	const hasChildren = $derived(node.children.length > 0);
</script>

<li class="space-y-1">
	<div class="flex items-center gap-2 text-sm">
		{#if hasChildren}
			<button
				type="button"
				class="w-3 text-xs text-zinc-500 hover:text-zinc-900"
				aria-label={expanded ? 'Collapse' : 'Expand'}
				onclick={() => (expanded = !expanded)}
			>
				{expanded ? '▾' : '▸'}
			</button>
		{:else}
			<span class="w-3"></span>
		{/if}
		<button
			type="button"
			class="truncate text-zinc-800 hover:underline"
			onclick={() => goto(`/chats/${node.id}`)}
			title={node.title ?? `#${node.id}`}
		>
			{node.title ?? `#${node.id}`}
		</button>
		{#if node.relation_notes}
			<span class="truncate text-xs text-zinc-400">· {node.relation_notes}</span>
		{/if}
		{#if hasChildren}
			<span class="ml-auto text-xs text-zinc-400">{node.children.length}</span>
		{/if}
	</div>
	{#if expanded && hasChildren}
		<ul class="ml-4 space-y-1 border-l border-zinc-200 pl-2">
			{#each node.children as child (child.id)}
				<Self node={child} depth={depth + 1} />
			{/each}
		</ul>
	{/if}
</li>
