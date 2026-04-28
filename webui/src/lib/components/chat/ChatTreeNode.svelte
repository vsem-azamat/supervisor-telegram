<script lang="ts">
	import { goto } from '$app/navigation';
	import { ChevronDown, ChevronRight } from '@lucide/svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { untrack } from 'svelte';
	import Self from './ChatTreeNode.svelte';
	import { hashId, initialsFor, type EnrichedNode } from './tree';

	type Props = {
		node: EnrichedNode;
		expandedIds?: SvelteSet<number>;
		query?: string;
		defaultExpandedDepth?: number;
	};
	let { node, expandedIds, query = '', defaultExpandedDepth = 2 }: Props = $props();

	// Local fallback when the parent doesn't manage expansion (legacy uses on
	// the dashboard preview tile). Initialised from depth so shallow trees
	// expand by default but deep ones stay collapsed.
	let localExpanded = $state(untrack(() => node.depth < defaultExpandedDepth));

	const expanded = $derived(expandedIds ? expandedIds.has(node.id) : localExpanded);
	const hasChildren = $derived(node.children.length > 0);

	function toggle() {
		if (expandedIds) {
			if (expandedIds.has(node.id)) expandedIds.delete(node.id);
			else expandedIds.add(node.id);
		} else {
			localExpanded = !localExpanded;
		}
	}

	const palette = [
		'bg-amber-100 text-amber-700',
		'bg-emerald-100 text-emerald-700',
		'bg-sky-100 text-sky-700',
		'bg-violet-100 text-violet-700',
		'bg-rose-100 text-rose-700',
		'bg-fuchsia-100 text-fuchsia-700',
		'bg-lime-100 text-lime-700',
		'bg-orange-100 text-orange-700'
	];
	const avatarClass = $derived(palette[hashId(node.id) % palette.length]);
	const initials = $derived(initialsFor(node.title, node.id));
	const label = $derived(node.title ?? `#${node.id}`);

	type Segment = { text: string; matched: boolean };
	function highlight(text: string, q: string): Segment[] {
		if (!q) return [{ text, matched: false }];
		const lower = text.toLowerCase();
		const needle = q.toLowerCase();
		const segments: Segment[] = [];
		let i = 0;
		while (i < text.length) {
			const hit = lower.indexOf(needle, i);
			if (hit === -1) {
				segments.push({ text: text.slice(i), matched: false });
				break;
			}
			if (hit > i) segments.push({ text: text.slice(i, hit), matched: false });
			segments.push({ text: text.slice(hit, hit + needle.length), matched: true });
			i = hit + needle.length;
		}
		return segments;
	}

	const labelSegments = $derived(highlight(label, query));
	const notesSegments = $derived(node.relation_notes ? highlight(node.relation_notes, query) : []);
</script>

<li class="space-y-0.5">
	<div
		class="group flex items-center gap-2 rounded-md py-1 pr-1 pl-0.5 text-sm transition-colors hover:bg-zinc-50"
	>
		{#if hasChildren}
			<button
				type="button"
				class="flex h-5 w-5 shrink-0 items-center justify-center rounded text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700"
				aria-label={expanded ? 'Collapse' : 'Expand'}
				onclick={toggle}
			>
				{#if expanded}
					<ChevronDown class="h-3.5 w-3.5" />
				{:else}
					<ChevronRight class="h-3.5 w-3.5" />
				{/if}
			</button>
		{:else}
			<span class="h-5 w-5 shrink-0"></span>
		{/if}

		<span
			class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold tracking-tight {avatarClass}"
			aria-hidden="true"
		>
			{initials}
		</span>

		<button
			type="button"
			class="min-w-0 flex-1 truncate text-left font-medium text-zinc-800 hover:text-zinc-950 hover:underline"
			onclick={() => goto(`/chats/${node.id}`)}
			title={label}
		>
			{#each labelSegments as seg}
				{#if seg.matched}
					<mark class="rounded bg-amber-200/70 px-0.5 text-zinc-900">{seg.text}</mark>
				{:else}
					{seg.text}
				{/if}
			{/each}
		</button>

		{#if node.relation_notes}
			<span class="hidden truncate text-xs text-zinc-400 md:inline">
				·
				{#each notesSegments as seg}
					{#if seg.matched}
						<mark class="rounded bg-amber-200/70 px-0.5 text-zinc-700">{seg.text}</mark>
					{:else}
						{seg.text}
					{/if}
				{/each}
			</span>
		{/if}

		{#if hasChildren}
			<span
				class="ml-auto rounded-full bg-zinc-100 px-1.5 py-0.5 font-mono text-[10px] text-zinc-500 group-hover:bg-zinc-200"
				title="{node.subtreeSize} chats including this root"
			>
				{node.subtreeSize}
			</span>
		{/if}
	</div>

	{#if expanded && hasChildren}
		<ul class="ml-3 space-y-0.5 border-l border-zinc-200 pl-3">
			{#each node.children as child (child.id)}
				<Self node={child} {expandedIds} {query} {defaultExpandedDepth} />
			{/each}
		</ul>
	{/if}
</li>
