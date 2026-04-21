<script lang="ts">
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { apiFetch } from '$lib/api/client';
	import type { components } from '$lib/api/types';

	type Post = components['schemas']['PostRead'];

	let status = $state<string>('');
	let channelId = $state<string>('');
	let posts = $state<Post[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);

	async function load() {
		loading = true;
		error = null;
		const params = new URLSearchParams({ limit: '100' });
		if (status) params.set('status', status);
		if (channelId) params.set('channel_id', channelId);
		const res = await apiFetch<Post[]>(`/api/posts?${params}`);
		if (res.error) {
			error = res.error.message;
			posts = [];
		} else {
			posts = res.data;
		}
		loading = false;
	}

	$effect(() => {
		void load();
	});

	const STATUSES = ['draft', 'sent_for_review', 'approved', 'scheduled', 'published', 'rejected', 'failed', 'deleted'];
</script>

<div class="space-y-4 px-6 py-6">
	<header class="flex items-center justify-between">
		<h2 class="text-lg font-semibold tracking-tight">Posts</h2>
		<div class="flex items-center gap-2">
			<select
				bind:value={status}
				class="rounded-md border border-zinc-200 bg-white px-2 py-1 text-sm"
				onchange={() => load()}
			>
				<option value="">all statuses</option>
				{#each STATUSES as s (s)}<option value={s}>{s}</option>{/each}
			</select>
			<Input
				placeholder="channel_id"
				bind:value={channelId}
				class="w-40"
				onkeydown={(e: KeyboardEvent) => {
					if (e.key === 'Enter') load();
				}}
			/>
		</div>
	</header>

	{#if loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if error}
		<p class="text-sm text-red-600">Error: {error}</p>
	{:else if posts.length === 0}
		<p class="text-sm text-zinc-500">No posts match these filters.</p>
	{:else}
		<Table.Root>
			<Table.Header>
				<Table.Row>
					<Table.Head class="w-16">ID</Table.Head>
					<Table.Head class="w-32">Status</Table.Head>
					<Table.Head>Title</Table.Head>
					<Table.Head class="w-32">Channel</Table.Head>
					<Table.Head class="w-40">Created</Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body>
				{#each posts as p (p.id)}
					<Table.Row>
						<Table.Cell class="text-zinc-500">{p.id}</Table.Cell>
						<Table.Cell><Badge variant="secondary">{p.status}</Badge></Table.Cell>
						<Table.Cell class="truncate">
							<a class="text-zinc-900 hover:underline" href={`/posts/${p.id}`}>{p.title}</a>
						</Table.Cell>
						<Table.Cell class="font-mono text-xs text-zinc-600">{p.channel_id}</Table.Cell>
						<Table.Cell class="text-xs text-zinc-500">
							{new Date(p.created_at).toLocaleString()}
						</Table.Cell>
					</Table.Row>
				{/each}
			</Table.Body>
		</Table.Root>
	{/if}
</div>
