<script lang="ts">
	import ChatTreeNode from '$lib/components/chat/ChatTreeNode.svelte';
	import {
		collectIds,
		computeStats,
		enrichTree,
		filterTree,
		type EnrichedNode
	} from '$lib/components/chat/tree';
	import { apiFetch } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import { ChevronsDownUp, ChevronsUpDown, Network, RefreshCw, Save, Search } from '@lucide/svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';
	import type { components } from '$lib/api/types';

	type Chat = components['schemas']['ChatRead'];
	type ChatUpdate = components['schemas']['ChatUpdate'];
	type Tree = components['schemas']['ChatNode'][];

	const chats = useLivePoll<Chat[]>('/api/chats', 60_000);
	const tree = useLivePoll<Tree>('/api/chats/graph', 60_000);

	let query = $state('');
	let selectedChatId = $state('');
	let parentChatId = $state('');
	let relationNotes = $state('');
	let saving = $state(false);

	const enrichedRoots = $derived(tree.data ? enrichTree(tree.data) : []);
	const filteredRoots = $derived(filterTree(enrichedRoots, query));
	const stats = $derived(computeStats(enrichedRoots));
	const selectedChat = $derived(
		chats.data?.find((chat) => String(chat.id) === selectedChatId) ?? null
	);
	const descendantIds = $derived(selectedChat ? collectDescendantIds(selectedChat.id, chats.data ?? []) : new Set<number>());
	const parentOptions = $derived(
		(chats.data ?? []).filter((chat) => chat.id !== selectedChat?.id && !descendantIds.has(chat.id))
	);

	const expandedIds = new SvelteSet<number>();
	let seeded = false;
	let preFilterExpansion: number[] = [];
	let filterApplied = false;

	function collectDescendantIds(chatId: number, rows: Chat[]): Set<number> {
		const childrenByParent = new Map<number, Chat[]>();
		for (const chat of rows) {
			if (chat.parent_chat_id === null || chat.parent_chat_id === undefined) continue;
			const children = childrenByParent.get(chat.parent_chat_id) ?? [];
			children.push(chat);
			childrenByParent.set(chat.parent_chat_id, children);
		}

		const out = new Set<number>();
		const visit = (id: number): void => {
			for (const child of childrenByParent.get(id) ?? []) {
				if (out.has(child.id)) continue;
				out.add(child.id);
				visit(child.id);
			}
		};
		visit(chatId);
		return out;
	}

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

	$effect(() => {
		if (!seeded && enrichedRoots.length > 0) {
			seed(enrichedRoots);
			seeded = true;
		}
		const q = query.trim();
		if (q && !filterApplied) {
			preFilterExpansion = Array.from(expandedIds);
			expandAll();
			filterApplied = true;
		}
		if (!q && filterApplied) {
			expandedIds.clear();
			for (const id of preFilterExpansion) expandedIds.add(id);
			filterApplied = false;
		}
	});

	$effect(() => {
		if (selectedChat) {
			parentChatId = selectedChat.parent_chat_id ? String(selectedChat.parent_chat_id) : '';
			relationNotes = selectedChat.relation_notes ?? '';
		}
	});

	async function saveHierarchy(): Promise<void> {
		if (!selectedChat) {
			toast.error('Select a chat first');
			return;
		}
		const parent = parentChatId ? Number(parentChatId) : null;
		if (parent !== null && (!Number.isFinite(parent) || parent === selectedChat.id || descendantIds.has(parent))) {
			toast.error('Choose a valid parent chat');
			return;
		}

		saving = true;
		const payload: ChatUpdate = {
			parent_chat_id: parent,
			relation_notes: relationNotes.trim() || null
		};
		const res = await apiFetch<Chat>(`/api/chats/${selectedChat.id}`, {
			method: 'PATCH',
			body: JSON.stringify(payload)
		});
		saving = false;
		if (res.error) {
			toast.error(res.error.message);
			return;
		}
		toast.success('Hierarchy updated');
		await Promise.all([chats.refresh(), tree.refresh()]);
	}
</script>

<div class="mx-auto max-w-6xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Hierarchy</h2>
			<p class="mt-0.5 text-xs text-zinc-500">Managed chat relationships.</p>
		</div>
		<div class="flex items-center gap-3 text-xs text-zinc-500">
			{#if tree.lastUpdatedAt}
				<span>Updated {tree.lastUpdatedAt.toLocaleTimeString()}</span>
			{/if}
			<Button variant="outline" size="xs" onclick={() => Promise.all([chats.refresh(), tree.refresh()])}>
				<RefreshCw class="h-3 w-3" />
				Refresh
			</Button>
		</div>
	</header>

	<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
		<div class="flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<Network class="h-4 w-4 text-zinc-500" />
			<div class="min-w-0">
				<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Chats</div>
				<div class="text-lg font-semibold tracking-tight text-zinc-900">{stats.total}</div>
			</div>
		</div>
		<div class="rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Networks</div>
			<div class="text-lg font-semibold tracking-tight text-zinc-900">{stats.rootCount}</div>
		</div>
		<div class="rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Levels</div>
			<div class="text-lg font-semibold tracking-tight text-zinc-900">{enrichedRoots.length === 0 ? '-' : stats.maxDepth + 1}</div>
		</div>
		<div class="rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Largest</div>
			<div class="text-lg font-semibold tracking-tight text-zinc-900">{stats.biggestNetwork || '-'}</div>
		</div>
	</div>

	<div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
		<div class="overflow-hidden rounded-md border border-zinc-200 bg-white">
			<div class="flex items-center justify-between gap-3 border-b border-zinc-200 bg-zinc-50/80 p-2">
				<div class="relative min-w-0 flex-1">
					<Search class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-400" />
					<Input bind:value={query} placeholder="Filter chats..." class="h-7 pl-8" />
				</div>
				<div class="flex items-center gap-1">
					<Button variant="ghost" size="icon-xs" disabled={enrichedRoots.length === 0} onclick={expandAll} title="Expand all">
						<ChevronsUpDown class="h-3 w-3" />
					</Button>
					<Button variant="ghost" size="icon-xs" disabled={enrichedRoots.length === 0} onclick={collapseAll} title="Collapse all">
						<ChevronsDownUp class="h-3 w-3" />
					</Button>
				</div>
			</div>
			<div class="p-3">
				{#if tree.loading && !tree.data}
					<p class="text-sm text-zinc-500">Loading...</p>
				{:else if tree.error && !tree.data}
					<p class="text-sm text-red-600">Error: {tree.error}</p>
				{:else if enrichedRoots.length === 0}
					<p class="text-sm text-zinc-500">No chats registered yet.</p>
				{:else if filteredRoots.length === 0}
					<p class="text-sm text-zinc-500">No matches for "{query}".</p>
				{:else}
					<ul class="space-y-0.5">
						{#each filteredRoots as root (root.id)}
							<ChatTreeNode node={root} {expandedIds} {query} />
						{/each}
					</ul>
				{/if}
			</div>
		</div>

		<div class="h-fit space-y-3 rounded-md border border-zinc-200 bg-white p-3">
			<div class="flex items-center gap-2 text-sm font-medium text-zinc-900">
				<Network class="h-4 w-4 text-zinc-500" />
				Parent link
			</div>
			<label class="space-y-1 text-xs">
				<span class="text-zinc-600">Chat</span>
				<select
					bind:value={selectedChatId}
					class="h-8 w-full rounded-md border border-zinc-200 bg-white px-2 text-sm"
				>
					<option value="">Select chat</option>
					{#each chats.data ?? [] as chat (chat.id)}
						<option value={String(chat.id)}>{chat.title ?? `#${chat.id}`}</option>
					{/each}
				</select>
			</label>
			<label class="space-y-1 text-xs">
				<span class="text-zinc-600">Parent</span>
				<select
					bind:value={parentChatId}
					disabled={!selectedChat}
					class="h-8 w-full rounded-md border border-zinc-200 bg-white px-2 text-sm disabled:opacity-50"
				>
					<option value="">No parent</option>
					{#each parentOptions as chat (chat.id)}
						<option value={String(chat.id)}>{chat.title ?? `#${chat.id}`}</option>
					{/each}
				</select>
			</label>
			<label class="space-y-1 text-xs">
				<span class="text-zinc-600">Notes</span>
				<Input bind:value={relationNotes} disabled={!selectedChat} placeholder="main, region, topic" />
			</label>
			<Button size="sm" class="w-full" disabled={!selectedChat || saving} onclick={saveHierarchy}>
				<Save class="h-3.5 w-3.5" />
				{saving ? 'Saving...' : 'Save'}
			</Button>
		</div>
	</div>
</div>
