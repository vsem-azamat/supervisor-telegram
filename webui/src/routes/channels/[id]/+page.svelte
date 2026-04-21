<script lang="ts">
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { apiFetch } from '$lib/api/client';
	import type { components } from '$lib/api/types';

	type ChannelDetail = components['schemas']['ChannelDetail'];

	let channel = $state<ChannelDetail | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);

	const channelId = $derived(page.params.id);

	$effect(() => {
		void (async () => {
			loading = true;
			const res = await apiFetch<ChannelDetail>(`/api/channels/${channelId}`);
			if (res.error) {
				error = res.error.message;
				channel = null;
			} else {
				channel = res.data;
				error = null;
			}
			loading = false;
		})();
	});
</script>

<div class="mx-auto max-w-4xl space-y-4 px-6 py-6">
	{#if loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if error}
		<p class="text-sm text-red-600">Error: {error}</p>
	{:else if channel}
		<header>
			<div class="text-xs text-zinc-500">
				<a href="/channels" class="hover:underline">Channels</a> › <span class="font-mono">#{channel.id}</span>
			</div>
			<h2 class="mt-1 text-xl font-semibold tracking-tight">{channel.name}</h2>
			<p class="mt-1 text-sm text-zinc-600">{channel.description || '—'}</p>
		</header>

		<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
			<Card.Root>
				<Card.Header><Card.Title class="text-sm">Config</Card.Title></Card.Header>
				<Card.Content class="space-y-2 text-sm">
					<div>Telegram ID: <span class="font-mono">{channel.telegram_id}</span></div>
					<div>Language: <span class="uppercase">{channel.language}</span></div>
					<div>Enabled: {channel.enabled ? 'yes' : 'no'}</div>
					<div>Max posts/day: {channel.max_posts_per_day}</div>
					<div>Review chat: <span class="font-mono">{channel.review_chat_id ?? '—'}</span></div>
					<div>Posting schedule: {channel.posting_schedule?.join(', ') ?? '—'}</div>
					<div>Publish schedule: {channel.publish_schedule?.join(', ') ?? '—'}</div>
					<div>Critic: {channel.critic_enabled ?? 'inherit'}</div>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header><Card.Title class="text-sm">Sources ({channel.sources.length})</Card.Title></Card.Header>
				<Card.Content>
					{#if channel.sources.length === 0}
						<p class="text-sm text-zinc-500">No sources configured.</p>
					{:else}
						<ul class="flex flex-col gap-2 text-sm">
							{#each channel.sources as s (s.id)}
								<li class="flex items-center justify-between gap-2">
									<span class="truncate" title={s.url}>{s.title ?? s.url}</span>
									<span class="shrink-0">
										{#if s.enabled}<Badge class="text-[10px]">on</Badge>{:else}<Badge variant="secondary" class="text-[10px]">off</Badge>{/if}
										{#if s.error_count > 0}<Badge variant="destructive" class="text-[10px]">err×{s.error_count}</Badge>{/if}
									</span>
								</li>
							{/each}
						</ul>
					{/if}
				</Card.Content>
			</Card.Root>
		</div>

		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Recent posts ({channel.recent_posts.length})</Card.Title></Card.Header>
			<Card.Content>
				{#if channel.recent_posts.length === 0}
					<p class="text-sm text-zinc-500">No posts yet.</p>
				{:else}
					<Table.Root>
						<Table.Header>
							<Table.Row>
								<Table.Head class="w-28">Status</Table.Head>
								<Table.Head>Title</Table.Head>
								<Table.Head class="w-40">Created</Table.Head>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{#each channel.recent_posts as p (p.id)}
								<Table.Row>
									<Table.Cell><Badge variant="secondary">{p.status}</Badge></Table.Cell>
									<Table.Cell><a href={`/posts/${p.id}`} class="hover:underline">{p.title}</a></Table.Cell>
									<Table.Cell class="text-xs text-zinc-500">{new Date(p.created_at).toLocaleString()}</Table.Cell>
								</Table.Row>
							{/each}
						</Table.Body>
					</Table.Root>
				{/if}
			</Card.Content>
		</Card.Root>
	{/if}
</div>
