<script lang="ts">
	import ChatTreeNode from '$lib/components/chat/ChatTreeNode.svelte';
	import * as Card from '$lib/components/ui/card/index.js';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import type { components } from '$lib/api/types';

	type Tree = components['schemas']['ChatNode'][];
	const tree = useLivePoll<Tree>('/api/chats/graph', 60_000);

	const totalChats = $derived.by(() => {
		const count = (nodes: Tree): number =>
			nodes.reduce((acc, n) => acc + 1 + count(n.children), 0);
		return tree.data ? count(tree.data) : 0;
	});
</script>

<div class="mx-auto max-w-3xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<h2 class="text-lg font-semibold tracking-tight">Chat graph</h2>
		<div class="flex items-center gap-3 text-xs text-zinc-500">
			{#if !tree.loading && tree.data}
				<span>{totalChats} chats</span>
			{/if}
			{#if tree.error}
				<span class="text-red-600">Error: {tree.error}</span>
			{:else if tree.lastUpdatedAt}
				<span>Updated {tree.lastUpdatedAt.toLocaleTimeString()}</span>
			{/if}
			<button
				type="button"
				class="rounded-md border border-zinc-200 px-2 py-1 text-xs font-medium hover:bg-zinc-100"
				onclick={() => tree.refresh()}
			>
				Refresh
			</button>
		</div>
	</header>

	<Card.Root>
		<Card.Content class="py-4">
			{#if tree.loading}
				<p class="text-sm text-zinc-500">Loading…</p>
			{:else if tree.error}
				<p class="text-sm text-red-600">Error: {tree.error}</p>
			{:else if !tree.data || tree.data.length === 0}
				<p class="text-sm text-zinc-500">
					No chats found. Set <code class="rounded bg-zinc-100 px-1 py-0.5 text-xs">parent_chat_id</code> on any
					chat row to build the tree.
				</p>
			{:else}
				<ul class="space-y-1">
					{#each tree.data as root (root.id)}
						<ChatTreeNode node={root} />
					{/each}
				</ul>
			{/if}
		</Card.Content>
	</Card.Root>
</div>
