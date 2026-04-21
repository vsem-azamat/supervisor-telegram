<script lang="ts">
	import { page } from '$app/state';
	import HeatmapGrid from '$lib/components/chat/HeatmapGrid.svelte';
	import Sparkline from '$lib/components/charts/Sparkline.svelte';
	import * as Card from '$lib/components/ui/card/index.js';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import type { components } from '$lib/api/types';

	type ChatDetail = components['schemas']['ChatDetail'];

	const chatId = page.params.id;
	const detail = useLivePoll<ChatDetail>(`/api/chats/${chatId}`, 60_000);
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
					<Sparkline values={detail.data.member_snapshots.map((p) => p.member_count)} />
					<p class="text-xs text-zinc-500">
						{detail.data.member_snapshots.length} snapshots
					</p>
				{/if}
			</Card.Content>
		</Card.Root>

		{#if detail.data.parent_chat_id !== null || detail.data.children.length > 0}
			<Card.Root>
				<Card.Header><Card.Title class="text-sm">Relationships</Card.Title></Card.Header>
				<Card.Content class="space-y-2 text-sm">
					{#if detail.data.parent_chat_id !== null}
						<div class="flex items-baseline gap-2">
							<span class="text-zinc-500">Parent:</span>
							<a href="/chats/{detail.data.parent_chat_id}" class="text-zinc-800 hover:underline">
								#{detail.data.parent_chat_id}
							</a>
							{#if detail.data.relation_notes}
								<span class="text-xs text-zinc-400">· {detail.data.relation_notes}</span>
							{/if}
						</div>
					{/if}
					{#if detail.data.children.length > 0}
						<div class="space-y-1">
							<span class="text-zinc-500">Children ({detail.data.children.length}):</span>
							<ul class="ml-4 list-disc space-y-0.5">
								{#each detail.data.children as c (c.id)}
									<li>
										<a href="/chats/{c.id}" class="text-zinc-800 hover:underline">
											{c.title ?? `#${c.id}`}
										</a>
										{#if c.relation_notes}
											<span class="text-xs text-zinc-400">· {c.relation_notes}</span>
										{/if}
									</li>
								{/each}
							</ul>
						</div>
					{/if}
				</Card.Content>
			</Card.Root>
		{/if}
	{/if}
</div>
