<script lang="ts">
	import ChatTreeNode from '$lib/components/chat/ChatTreeNode.svelte';
	import { enrichTree } from '$lib/components/chat/tree';
	import BarChartH from '$lib/components/charts/BarChartH.svelte';
	import DivergingBars from '$lib/components/charts/DivergingBars.svelte';
	import ActionTile from '$lib/components/home/ActionTile.svelte';
	import Tile from '$lib/components/home/Tile.svelte';
	import SpamPingsList from '$lib/components/spam/SpamPingsList.svelte';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import { MessageSquare, Network, RefreshCw, ShieldAlert } from '@lucide/svelte';
	import type { components } from '$lib/api/types';

	type HomeStats = components['schemas']['HomeStats'];
	type Tree = components['schemas']['ChatNode'][];

	const stats = useLivePoll<HomeStats>('/api/stats/home');
	const tree = useLivePoll<Tree>('/api/chats/graph', 120_000);

	const enrichedTree = $derived(tree.data ? enrichTree(tree.data) : []);

	const spamCount24h = $derived(stats.data?.spam_pings.count_24h ?? 0);
	const spamCount7d = $derived(stats.data?.spam_pings.count_7d ?? 0);
	const trackedChats = $derived(stats.data?.members_delta.length ?? 0);
	const messages7d = $derived(
		(stats.data?.chat_heatmap ?? []).reduce((acc, c) => acc + c.total_messages, 0)
	);
</script>

<div class="space-y-6 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Dashboard</h2>
			<p class="mt-0.5 text-xs text-zinc-500">Live moderation view of the Konnekt chats.</p>
		</div>
		<div class="flex items-center gap-3 text-xs text-zinc-500">
			{#if stats.error}
				<span class="text-red-600">Error: {stats.error}</span>
			{:else if stats.lastUpdatedAt}
				<span>Updated {stats.lastUpdatedAt.toLocaleTimeString()}</span>
			{/if}
			<button
				type="button"
				class="flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs font-medium hover:bg-zinc-100"
				onclick={() => stats.refresh()}
			>
				<RefreshCw class="h-3 w-3" />
				<span>Refresh</span>
			</button>
		</div>
	</header>

	<!-- Action bar: what needs attention NOW -->
	<section class="space-y-2">
		<div class="text-[10px] font-semibold tracking-wider text-zinc-400 uppercase">
			Needs your attention
		</div>
		<div class="grid grid-cols-1 gap-3 md:grid-cols-3">
			<ActionTile
				title="Spam pings (24h)"
				value={spamCount24h}
				caption="Ad detector hits across all chats"
				icon={ShieldAlert}
				tone={spamCount24h > 0 ? 'warning' : 'default'}
				href="/admin/chats"
			/>
			<ActionTile
				title="Spam pings (7d)"
				value={spamCount7d}
				caption="Rolling weekly total"
				icon={ShieldAlert}
				href="/admin/chats"
			/>
			<ActionTile
				title="Messages (7d)"
				value={messages7d.toLocaleString()}
				caption={`${trackedChats} chats with member snapshots`}
				icon={MessageSquare}
				href="/admin/catalog"
			/>
		</div>
	</section>

	<!-- Chats / community -->
	<section class="space-y-2">
		<div class="text-[10px] font-semibold tracking-wider text-zinc-400 uppercase">Community</div>
		<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
			<Tile title="Chats heatmap (7d total)">
				<BarChartH
					items={(stats.data?.chat_heatmap ?? []).map((c) => ({
						label: c.title ?? `#${c.chat_id}`,
						value: c.total_messages,
						href: `/chats/${c.chat_id}`
					}))}
					empty={stats.loading ? 'loading…' : 'No activity recorded'}
				/>
			</Tile>

			<Tile title="Members Δ (24h)">
				<DivergingBars
					items={(stats.data?.members_delta ?? []).map((m) => {
						const d = m.delta_24h;
						const secondary =
							d === null || d === undefined
								? `${m.current?.toLocaleString() ?? '—'} · no baseline`
								: `${m.current?.toLocaleString() ?? '—'} · ${d > 0 ? '+' : ''}${d}`;
						return {
							label: m.title ?? `#${m.chat_id}`,
							value: d ?? null,
							secondary,
							href: `/chats/${m.chat_id}`
						};
					})}
					empty={stats.loading ? 'loading…' : 'No snapshots yet'}
				/>
			</Tile>
		</div>
	</section>

	<!-- Side rail: spam + tree -->
	<section class="space-y-2">
		<div class="text-[10px] font-semibold tracking-wider text-zinc-400 uppercase">
			Recent activity
		</div>
		<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
			<Tile title="Recent spam pings">
				<SpamPingsList
					items={(stats.data?.spam_pings.recent ?? []).slice(0, 4)}
					empty={stats.loading ? 'loading…' : 'No pings detected.'}
					showChat
				/>
			</Tile>

			<Tile title="Chat graph">
				{#snippet action()}
					<Network class="h-3.5 w-3.5 text-zinc-400" />
				{/snippet}
				{#if tree.loading}
					<p class="text-xs text-zinc-500">loading…</p>
				{:else if enrichedTree.length === 0}
					<p class="text-xs text-zinc-500">No chats yet.</p>
				{:else}
					<ul class="space-y-1">
						{#each enrichedTree.slice(0, 3) as root (root.id)}
							<ChatTreeNode node={root} defaultExpandedDepth={1} />
						{/each}
					</ul>
					<a
						href="/admin/catalog/hierarchy"
						class="mt-2 inline-block text-xs text-zinc-500 hover:underline"
					>
						View full tree →
					</a>
				{/if}
			</Tile>
		</div>
	</section>
</div>
