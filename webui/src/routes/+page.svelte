<script lang="ts">
	import ChatTreeNode from '$lib/components/chat/ChatTreeNode.svelte';
	import BarChartH from '$lib/components/charts/BarChartH.svelte';
	import DivergingBars from '$lib/components/charts/DivergingBars.svelte';
	import Donut from '$lib/components/charts/Donut.svelte';
	import ListTile from '$lib/components/home/ListTile.svelte';
	import StatTile from '$lib/components/home/StatTile.svelte';
	import Tile from '$lib/components/home/Tile.svelte';
	import SpamPingsList from '$lib/components/spam/SpamPingsList.svelte';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import type { components } from '$lib/api/types';

	type HomeStats = components['schemas']['HomeStats'];
	type Tree = components['schemas']['ChatNode'][];

	const stats = useLivePoll<HomeStats>('/api/stats/home');
	const tree = useLivePoll<Tree>('/api/chats/graph', 120_000);

	const totalDrafts = $derived(
		stats.data?.drafts.reduce((acc, d) => acc + d.count, 0) ?? 0
	);
	const sessionCostUsd = $derived(stats.data?.session_cost.total_cost_usd ?? 0);

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
		<h2 class="text-lg font-semibold tracking-tight">Home dashboard</h2>
		<div class="flex items-center gap-3 text-xs text-zinc-500">
			{#if stats.error}
				<span class="text-red-600">Error: {stats.error}</span>
			{:else if stats.lastUpdatedAt}
				<span>Updated {stats.lastUpdatedAt.toLocaleTimeString()}</span>
			{/if}
			<button
				type="button"
				class="rounded-md border border-zinc-200 px-2 py-1 text-xs font-medium hover:bg-zinc-100"
				onclick={() => stats.refresh()}
			>
				Refresh
			</button>
		</div>
	</header>

	<div class="grid grid-cols-1 gap-4 md:grid-cols-4 xl:grid-cols-6">
		<div class="md:col-span-2 xl:col-span-3">
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
		</div>

		<div class="md:col-span-2 xl:col-span-3">
			<Tile title="Post views (recent)">
				<BarChartH
					items={(stats.data?.post_views ?? []).map((p) => ({
						label: p.title,
						value: p.views,
						secondary: p.views === 0 ? 'no data' : p.views.toLocaleString()
					}))}
					empty={stats.loading ? 'loading…' : 'No published posts yet'}
				/>
			</Tile>
		</div>

		<div class="md:col-span-2 xl:col-span-3">
			<Tile title="Chats heatmap (7d total)">
				<BarChartH
					items={(stats.data?.chat_heatmap ?? []).map((c) => ({
						label: c.title ?? `#${c.chat_id}`,
						value: c.total_messages
					}))}
					empty={stats.loading ? 'loading…' : 'No activity recorded'}
				/>
			</Tile>
		</div>

		<div class="md:col-span-2 xl:col-span-3">
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
							secondary
						};
					})}
					empty={stats.loading ? 'loading…' : 'No snapshots yet'}
				/>
			</Tile>
		</div>

		<div class="md:col-span-2 xl:col-span-2">
			<ListTile
				title="Scheduled next 24h"
				items={(stats.data?.scheduled_next_24h ?? []).map((p) => ({
					primary: p.title,
					secondary: fmtWhen(p.scheduled_at)
				}))}
				empty={stats.loading ? 'loading…' : 'Nothing scheduled'}
			/>
		</div>

		<div class="md:col-span-2 xl:col-span-2">
			<StatTile
				title="LLM cost (session)"
				value={fmtMoney(sessionCostUsd)}
				caption="Since last bot restart"
			/>
		</div>

		<div class="md:col-span-2 xl:col-span-2">
			<Tile title="Spam pings (24h)">
				<div class="flex items-baseline gap-3">
					<span class="text-2xl font-semibold tracking-tight text-zinc-900">
						{stats.data?.spam_pings.count_24h ?? 0}
					</span>
					<span class="text-xs text-zinc-500">
						· {stats.data?.spam_pings.count_7d ?? 0} in 7d
					</span>
				</div>
				<div class="mt-2">
					<SpamPingsList
						items={(stats.data?.spam_pings.recent ?? []).slice(0, 3)}
						empty={stats.loading ? 'loading…' : 'No pings detected.'}
						showChat
					/>
				</div>
			</Tile>
		</div>

		<div class="md:col-span-2 xl:col-span-2">
			<Tile title="Chat graph">
				{#if tree.loading}
					<p class="text-xs text-zinc-500">loading…</p>
				{:else if !tree.data || tree.data.length === 0}
					<p class="text-xs text-zinc-500">No chats yet.</p>
				{:else}
					<ul class="space-y-1">
						{#each tree.data.slice(0, 3) as root (root.id)}
							<ChatTreeNode node={root} depth={1} />
						{/each}
					</ul>
					<a href="/chats/graph" class="mt-2 inline-block text-xs text-zinc-500 hover:underline">
						View full tree →
					</a>
				{/if}
			</Tile>
		</div>
	</div>
</div>
