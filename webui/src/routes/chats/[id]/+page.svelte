<script lang="ts">
	import { page } from '$app/state';
	import * as Card from '$lib/components/ui/card/index.js';
	import HeatmapGrid from '$lib/components/chat/HeatmapGrid.svelte';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import type { components } from '$lib/api/types';

	type ChatDetail = components['schemas']['ChatDetail'];

	const chatId = page.params.id;
	const detail = useLivePoll<ChatDetail>(`/api/chats/${chatId}`, 60_000);

	function sparklinePath(points: { member_count: number }[]): string {
		if (points.length === 0) return '';
		const w = 240;
		const h = 48;
		const max = Math.max(...points.map((p) => p.member_count));
		const min = Math.min(...points.map((p) => p.member_count));
		const span = Math.max(1, max - min);
		return points
			.map((p, i) => {
				const x = (i / Math.max(1, points.length - 1)) * w;
				const y = h - ((p.member_count - min) / span) * h;
				return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(' ');
	}
</script>

<div class="mx-auto max-w-5xl space-y-4 px-6 py-6">
	<header>
		<h2 class="text-lg font-semibold tracking-tight">
			{detail.data?.title ?? `Chat #${chatId}`}
		</h2>
		{#if detail.lastUpdatedAt}
			<span class="text-xs text-zinc-500">Updated {detail.lastUpdatedAt.toLocaleTimeString()}</span>
		{/if}
	</header>

	{#if detail.loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if detail.error}
		<p class="text-sm text-red-600">Error: {detail.error}</p>
	{:else if detail.data}
		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Overview</Card.Title></Card.Header>
			<Card.Content class="grid grid-cols-2 gap-2 text-sm">
				<div>Members: <strong>{detail.data.member_count ?? '—'}</strong></div>
				<div>Forum: {detail.data.is_forum ? 'yes' : 'no'}</div>
				<div>Captcha: {detail.data.is_captcha_enabled ? 'on' : 'off'}</div>
				<div>Welcome: {detail.data.is_welcome_enabled ? 'on' : 'off'}</div>
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Activity heatmap (7 days, UTC)</Card.Title></Card.Header>
			<Card.Content>
				<HeatmapGrid cells={detail.data.heatmap} />
				{#if detail.data.heatmap.length === 0}
					<p class="mt-2 text-xs text-zinc-500">No messages recorded for this chat yet.</p>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Members over time</Card.Title></Card.Header>
			<Card.Content>
				{#if detail.data.member_snapshots.length === 0}
					<p class="text-xs text-zinc-500">No snapshots yet. First snapshot will appear within an hour of bot startup.</p>
				{:else}
					<svg width="240" height="48" class="text-emerald-600">
						<path d={sparklinePath(detail.data.member_snapshots)} fill="none" stroke="currentColor" stroke-width="1.5" />
					</svg>
					<p class="text-xs text-zinc-500">
						{detail.data.member_snapshots.length} snapshots
					</p>
				{/if}
			</Card.Content>
		</Card.Root>
	{/if}
</div>
