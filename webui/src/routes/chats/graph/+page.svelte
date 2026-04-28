<script lang="ts">
	import ChatTreeNode from '$lib/components/chat/ChatTreeNode.svelte';
	import {
		collectIds,
		computeStats,
		enrichTree,
		filterTree,
		type EnrichedNode
	} from '$lib/components/chat/tree';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import { ChevronsDownUp, ChevronsUpDown, RefreshCw, Search } from '@lucide/svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import type { components } from '$lib/api/types';

	type Tree = components['schemas']['ChatNode'][];
	const tree = useLivePoll<Tree>('/api/chats/graph', 60_000);

	let query = $state('');

	const enrichedRoots = $derived(tree.data ? enrichTree(tree.data) : []);
	const filteredRoots = $derived(filterTree(enrichedRoots, query));
	const stats = $derived(computeStats(enrichedRoots));

	const expandedIds = new SvelteSet<number>();
	let seeded = false;

	function seed(roots: EnrichedNode[]) {
		const visit = (n: EnrichedNode): void => {
			if (n.depth < 2) expandedIds.add(n.id);
			n.children.forEach(visit);
		};
		roots.forEach(visit);
	}

	function expandAll() {
		const all = collectIds(enrichedRoots);
		for (const id of all) expandedIds.add(id);
	}

	function collapseAll() {
		expandedIds.clear();
	}

	// While there's an active filter, expand every visible node so matches
	// aren't hidden behind a collapsed ancestor — restore on clear.
	let preFilterExpansion: number[] = [];
	let filterApplied = false;
	$effect(() => {
		if (!seeded && enrichedRoots.length > 0) {
			seed(enrichedRoots);
			seeded = true;
		}
		const q = query.trim();
		if (q && !filterApplied) {
			preFilterExpansion = Array.from(expandedIds);
			const all = collectIds(enrichedRoots);
			for (const id of all) expandedIds.add(id);
			filterApplied = true;
		}
		if (!q && filterApplied) {
			expandedIds.clear();
			for (const id of preFilterExpansion) expandedIds.add(id);
			filterApplied = false;
		}
	});

	function fmtDepth(d: number): string {
		// stats.maxDepth is 0 for a single-node tree; humans expect levels = depth+1.
		return enrichedRoots.length === 0 ? '—' : String(d + 1);
	}
</script>

<div class="mx-auto max-w-4xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Chat graph</h2>
			<p class="mt-0.5 text-xs text-zinc-500">
				Hierarchical view of every managed chat. Click a node to drill into the chat detail
				page.
			</p>
		</div>
		<div class="flex items-center gap-3 text-xs text-zinc-500">
			{#if tree.error}
				<span class="text-red-600">Error: {tree.error}</span>
			{:else if tree.lastUpdatedAt}
				<span>Updated {tree.lastUpdatedAt.toLocaleTimeString()}</span>
			{/if}
			<button
				type="button"
				class="flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs font-medium hover:bg-zinc-100"
				onclick={() => tree.refresh()}
			>
				<RefreshCw class="h-3 w-3" />
				<span>Refresh</span>
			</button>
		</div>
	</header>

	<!-- Stats strip: total chats / roots / max depth / biggest network -->
	<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
		<div class="rounded-lg border border-zinc-200 bg-white px-4 py-3">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Chats</div>
			<div class="mt-0.5 text-xl font-semibold tracking-tight text-zinc-900">{stats.total}</div>
		</div>
		<div class="rounded-lg border border-zinc-200 bg-white px-4 py-3">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Networks</div>
			<div class="mt-0.5 text-xl font-semibold tracking-tight text-zinc-900">{stats.rootCount}</div>
		</div>
		<div class="rounded-lg border border-zinc-200 bg-white px-4 py-3">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Max depth</div>
			<div class="mt-0.5 text-xl font-semibold tracking-tight text-zinc-900">
				{fmtDepth(stats.maxDepth)}
			</div>
		</div>
		<div class="rounded-lg border border-zinc-200 bg-white px-4 py-3">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">
				Biggest network
			</div>
			<div class="mt-0.5 text-xl font-semibold tracking-tight text-zinc-900">
				{stats.biggestNetwork || '—'}
			</div>
		</div>
	</div>

	<!-- Toolbar: search + expand/collapse -->
	<div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
		<div class="relative max-w-sm flex-1">
			<Search class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-400" />
			<Input
				bind:value={query}
				placeholder="Filter by title, notes or id…"
				class="pl-8"
			/>
		</div>
		<div class="flex items-center gap-2">
			<button
				type="button"
				class="flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs font-medium hover:bg-zinc-100 disabled:opacity-50"
				disabled={enrichedRoots.length === 0}
				onclick={expandAll}
			>
				<ChevronsUpDown class="h-3 w-3" />
				<span>Expand all</span>
			</button>
			<button
				type="button"
				class="flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs font-medium hover:bg-zinc-100 disabled:opacity-50"
				disabled={enrichedRoots.length === 0}
				onclick={collapseAll}
			>
				<ChevronsDownUp class="h-3 w-3" />
				<span>Collapse all</span>
			</button>
		</div>
	</div>

	<Card.Root>
		<Card.Content class="py-4">
			{#if tree.loading && !tree.data}
				<p class="text-sm text-zinc-500">Loading…</p>
			{:else if tree.error && !tree.data}
				<p class="text-sm text-red-600">Error: {tree.error}</p>
			{:else if enrichedRoots.length === 0}
				<p class="text-sm text-zinc-500">
					No chats found. Set <code class="rounded bg-zinc-100 px-1 py-0.5 text-xs">parent_chat_id</code>
					on any chat row to build the tree.
				</p>
			{:else if filteredRoots.length === 0}
				<p class="text-sm text-zinc-500">
					No matches for <span class="font-medium text-zinc-700">"{query}"</span>.
				</p>
			{:else}
				<ul class="space-y-0.5">
					{#each filteredRoots as root (root.id)}
						<ChatTreeNode node={root} {expandedIds} {query} />
					{/each}
				</ul>
			{/if}
		</Card.Content>
	</Card.Root>
</div>
