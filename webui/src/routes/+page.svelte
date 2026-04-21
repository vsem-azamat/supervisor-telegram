<script lang="ts">
	import ListTile from '$lib/components/home/ListTile.svelte';
	import SkeletonTile from '$lib/components/home/SkeletonTile.svelte';
	import StatTile from '$lib/components/home/StatTile.svelte';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import type { components } from '$lib/api/types';

	type HomeStats = components['schemas']['HomeStats'];

	const stats = useLivePoll<HomeStats>('/api/stats/home');

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

	<div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
		<StatTile
			title="Drafts queue"
			value={totalDrafts}
			caption={stats.loading ? 'loading…' : `${stats.data?.drafts.length ?? 0} channels`}
		/>
		<ListTile
			title="Scheduled next 24h"
			items={(stats.data?.scheduled_next_24h ?? []).map((p) => ({
				primary: p.title,
				secondary: fmtWhen(p.scheduled_at)
			}))}
			empty={stats.loading ? 'loading…' : 'Nothing scheduled'}
		/>
		<StatTile
			title="LLM cost (session)"
			value={fmtMoney(sessionCostUsd)}
			caption="Since last bot restart"
		/>
		<ListTile
			title="Post views (recent)"
			items={(stats.data?.post_views ?? []).map((p) => ({
				primary: p.title,
				secondary: p.views === 0 ? 'no data' : p.views.toLocaleString()
			}))}
			empty={stats.loading ? 'loading…' : 'No published posts yet'}
		/>
		<ListTile
			title="Chats heatmap (7d total)"
			items={(stats.data?.chat_heatmap ?? []).map((c) => ({
				primary: c.title ?? `#${c.chat_id}`,
				secondary: c.total_messages.toLocaleString()
			}))}
			empty={stats.loading ? 'loading…' : 'No activity recorded'}
		/>
		<ListTile
			title="Members Δ (24h)"
			items={(stats.data?.members_delta ?? []).map((m) => {
				const d = m.delta_24h;
				const sign = d === null || d === undefined ? '' : d > 0 ? '+' : '';
				const secondary =
					d === null || d === undefined
						? `${m.current ?? '—'} (no baseline)`
						: `${m.current?.toLocaleString() ?? '—'} (${sign}${d})`;
				return { primary: m.title ?? `#${m.chat_id}`, secondary };
			})}
			empty={stats.loading ? 'loading…' : 'No snapshots yet'}
		/>
		<SkeletonTile title="Spam pings" phase={3} hint="Needs spam detector." />
		<SkeletonTile title="Chat graph" phase={3} hint="Needs relationship model." />
	</div>
</div>
