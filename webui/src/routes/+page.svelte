<script lang="ts">
	import ChatTreeNode from '$lib/components/chat/ChatTreeNode.svelte';
	import { enrichTree } from '$lib/components/chat/tree';
	import BarChartH from '$lib/components/charts/BarChartH.svelte';
	import DivergingBars from '$lib/components/charts/DivergingBars.svelte';
	import Donut from '$lib/components/charts/Donut.svelte';
	import ActionTile from '$lib/components/home/ActionTile.svelte';
	import ListTile from '$lib/components/home/ListTile.svelte';
	import SuggestionsRow from '$lib/components/home/SuggestionsRow.svelte';
	import Tile from '$lib/components/home/Tile.svelte';
	import SpamPingsList from '$lib/components/spam/SpamPingsList.svelte';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import { Inbox, RefreshCw, Send, ShieldAlert, Wallet } from '@lucide/svelte';
	import type { components } from '$lib/api/types';

	type HomeStats = components['schemas']['HomeStats'];
	type Tree = components['schemas']['ChatNode'][];
	type Suggestions = components['schemas']['SuggestionsResponse'];

	const stats = useLivePoll<HomeStats>('/api/stats/home');
	const tree = useLivePoll<Tree>('/api/chats/graph', 120_000);
	const suggestions = useLivePoll<Suggestions>('/api/suggestions', 60_000);

	const suggestionItems = $derived(suggestions.data?.items ?? []);
	const enrichedTree = $derived(tree.data ? enrichTree(tree.data) : []);

	const totalDrafts = $derived(
		stats.data?.drafts.reduce((acc, d) => acc + d.count, 0) ?? 0
	);
	const sessionCostUsd = $derived(stats.data?.session_cost.total_cost_usd ?? 0);
	const scheduledCount = $derived(stats.data?.scheduled_next_24h.length ?? 0);
	const spamCount24h = $derived(stats.data?.spam_pings.count_24h ?? 0);

	function fmtMoney(usd: number): string {
		return usd < 0.01 ? '<$0.01' : `$${usd.toFixed(2)}`;
	}

	function fmtWhen(iso: string): string {
		const d = new Date(iso);
		const hh = d.getHours().toString().padStart(2, '0');
		const mm = d.getMinutes().toString().padStart(2, '0');
		return `${hh}:${mm}`;
	}
</script>

<div class="space-y-6 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Dashboard</h2>
			<p class="mt-0.5 text-xs text-zinc-500">Live operational view of the Konnekt platform.</p>
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
		<div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
			<ActionTile
				title="Drafts in review queue"
				value={totalDrafts}
				caption={totalDrafts === 0 ? 'No drafts pending' : 'Open the posts queue to review'}
				icon={Inbox}
				tone={totalDrafts > 0 ? 'attention' : 'default'}
				href="/posts?status=sent_for_review"
				cta={totalDrafts > 0 ? 'Review' : 'View'}
			/>
			<ActionTile
				title="Scheduled in 24h"
				value={scheduledCount}
				caption={scheduledCount === 0 ? 'Nothing scheduled' : 'Upcoming publications'}
				icon={Send}
				href="/posts?status=scheduled"
				cta="View"
			/>
			<ActionTile
				title="Spam pings (24h)"
				value={spamCount24h}
				caption="Ad detector hits across all chats"
				icon={ShieldAlert}
				tone={spamCount24h > 0 ? 'warning' : 'default'}
				href="/chats"
			/>
			<ActionTile
				title="LLM cost (session)"
				value={fmtMoney(sessionCostUsd)}
				caption="Since last bot restart"
				icon={Wallet}
				href="/costs"
			/>
		</div>
	</section>

	<!-- Setup gaps — surfaces only when at least one rule fires. -->
	{#if suggestionItems.length > 0}
		<section class="space-y-2">
			<div class="text-[10px] font-semibold tracking-wider text-zinc-400 uppercase">
				Setup gaps
			</div>
			<SuggestionsRow items={suggestionItems} loading={suggestions.loading} />
		</section>
	{/if}

	<!-- Content pipeline -->
	<section class="space-y-2">
		<div class="text-[10px] font-semibold tracking-wider text-zinc-400 uppercase">
			Content pipeline
		</div>
		<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
			<Tile title="Drafts by channel">
				<Donut
					slices={(stats.data?.drafts ?? []).map((d) => ({
						label: d.channel_name,
						value: d.count
					}))}
					centerValue={totalDrafts}
					centerLabel="drafts"
					empty={stats.loading ? 'loading…' : 'No drafts queued'}
				/>
			</Tile>

			<Tile title="Post views (recent)">
				<BarChartH
					items={(stats.data?.post_views ?? []).map((p) => ({
						label: p.title,
						value: p.views,
						secondary: p.views === 0 ? 'no data' : p.views.toLocaleString(),
						href: `/posts/${p.post_id}`
					}))}
					empty={stats.loading ? 'loading…' : 'No published posts yet'}
				/>
			</Tile>
		</div>
	</section>

	<!-- Chats / community -->
	<section class="space-y-2">
		<div class="text-[10px] font-semibold tracking-wider text-zinc-400 uppercase">
			Community
		</div>
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

	<!-- Side rail: timeline + spam + tree -->
	<section class="space-y-2">
		<div class="text-[10px] font-semibold tracking-wider text-zinc-400 uppercase">
			Recent activity
		</div>
		<div class="grid grid-cols-1 gap-4 md:grid-cols-3">
			<ListTile
				title="Scheduled next 24h"
				items={(stats.data?.scheduled_next_24h ?? []).map((p) => ({
					primary: p.title,
					secondary: fmtWhen(p.scheduled_at)
				}))}
				empty={stats.loading ? 'loading…' : 'Nothing scheduled'}
			/>

			<Tile title="Recent spam pings">
				<SpamPingsList
					items={(stats.data?.spam_pings.recent ?? []).slice(0, 4)}
					empty={stats.loading ? 'loading…' : 'No pings detected.'}
					showChat
				/>
			</Tile>

			<Tile title="Chat graph">
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
						href="/chats/graph"
						class="mt-2 inline-block text-xs text-zinc-500 hover:underline"
					>
						View full tree →
					</a>
				{/if}
			</Tile>
		</div>
	</section>
</div>
