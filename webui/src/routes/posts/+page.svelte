<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { apiFetch } from '$lib/api/client';
	import type { components } from '$lib/api/types';

	type Post = components['schemas']['PostRead'];
	type Channel = components['schemas']['ChannelRead'];

	let status = $state<string>(page.url.searchParams.get('status') ?? '');
	let channelId = $state<string>(page.url.searchParams.get('channel_id') ?? '');
	let posts = $state<Post[]>([]);
	let channels = $state<Channel[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);

	async function loadChannels(): Promise<void> {
		const res = await apiFetch<Channel[]>('/api/channels');
		if (!res.error) channels = res.data;
	}

	async function load(): Promise<void> {
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

	function syncUrl(): void {
		const params = new URLSearchParams();
		if (status) params.set('status', status);
		if (channelId) params.set('channel_id', channelId);
		const qs = params.toString();
		const target = qs ? `/posts?${qs}` : '/posts';
		void goto(target, { replaceState: true, noScroll: true, keepFocus: true });
	}

	function updateStatus(value: string): void {
		status = value;
		syncUrl();
		void load();
	}

	function updateChannel(value: string): void {
		channelId = value;
		syncUrl();
		void load();
	}

	$effect(() => {
		void loadChannels();
		void load();
	});

	const STATUSES = [
		'draft',
		'sent_for_review',
		'approved',
		'scheduled',
		'published',
		'rejected',
		'failed',
		'deleted'
	];

	const counts = $derived.by(() => {
		const m: Record<string, number> = {};
		for (const p of posts) m[p.status] = (m[p.status] ?? 0) + 1;
		return m;
	});

	const STATUS_COLOR: Record<string, string> = {
		draft: 'bg-zinc-100 text-zinc-700',
		sent_for_review: 'bg-amber-100 text-amber-800',
		approved: 'bg-blue-100 text-blue-800',
		scheduled: 'bg-indigo-100 text-indigo-800',
		published: 'bg-emerald-100 text-emerald-800',
		rejected: 'bg-rose-100 text-rose-800',
		failed: 'bg-rose-100 text-rose-800',
		deleted: 'bg-zinc-100 text-zinc-500'
	};

	const QUICK_FILTERS = [
		{ label: 'All', value: '' },
		{ label: 'In review', value: 'sent_for_review' },
		{ label: 'Scheduled', value: 'scheduled' },
		{ label: 'Published', value: 'published' }
	];

	const channelById = $derived.by(() => {
		const m = new Map<number, Channel>();
		for (const c of channels) m.set(c.id, c);
		return m;
	});
</script>

<div class="space-y-4 px-6 py-6">
	<header class="flex flex-wrap items-center justify-between gap-3">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Posts</h2>
			<p class="mt-0.5 text-xs text-zinc-500">
				{posts.length} loaded · filter by status or channel to drill in.
			</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<select
				value={status}
				class="rounded-md border border-zinc-200 bg-white px-2 py-1 text-sm"
				onchange={(e) => updateStatus((e.currentTarget as HTMLSelectElement).value)}
			>
				<option value="">all statuses</option>
				{#each STATUSES as s (s)}<option value={s}>{s}</option>{/each}
			</select>
			<select
				value={channelId}
				class="rounded-md border border-zinc-200 bg-white px-2 py-1 text-sm"
				onchange={(e) => updateChannel((e.currentTarget as HTMLSelectElement).value)}
			>
				<option value="">all channels</option>
				{#each channels as c (c.id)}
					<option value={String(c.id)}>{c.name}</option>
				{/each}
			</select>
			<Input
				placeholder="custom channel id"
				bind:value={channelId}
				class="w-40"
				onkeydown={(e: KeyboardEvent) => {
					if (e.key === 'Enter') {
						syncUrl();
						void load();
					}
				}}
			/>
		</div>
	</header>

	<!-- Quick filter pills + counts -->
	<div class="flex flex-wrap items-center gap-1.5">
		{#each QUICK_FILTERS as f (f.value)}
			{@const active = status === f.value}
			<button
				type="button"
				onclick={() => updateStatus(f.value)}
				class="rounded-full px-3 py-1 text-xs font-medium transition-colors {active
					? 'bg-zinc-900 text-white'
					: 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200'}"
			>
				{f.label}
			</button>
		{/each}
		<span class="ml-2 text-xs text-zinc-400">
			|
			{#each STATUSES as s (s)}
				{#if counts[s]}
					<span class="ml-2 inline-flex items-center gap-1">
						<span class="h-1.5 w-1.5 rounded-full {STATUS_COLOR[s] ?? 'bg-zinc-300'}"></span>
						<span class="text-zinc-500">{s}: {counts[s]}</span>
					</span>
				{/if}
			{/each}
		</span>
	</div>

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
					<Table.Head class="w-36">Status</Table.Head>
					<Table.Head>Title</Table.Head>
					<Table.Head class="w-44">Channel</Table.Head>
					<Table.Head class="w-40">Created</Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body>
				{#each posts as p (p.id)}
					{@const ch = channelById.get(p.channel_id)}
					<Table.Row>
						<Table.Cell class="text-zinc-500">{p.id}</Table.Cell>
						<Table.Cell>
							<span class="rounded-md px-2 py-0.5 text-xs font-medium {STATUS_COLOR[p.status] ?? 'bg-zinc-100 text-zinc-700'}">
								{p.status}
							</span>
						</Table.Cell>
						<Table.Cell class="truncate">
							<a class="text-zinc-900 hover:underline" href={`/posts/${p.id}`}>{p.title}</a>
						</Table.Cell>
						<Table.Cell class="text-xs">
							{#if ch}
								<a href={`/channels/${ch.id}`} class="text-zinc-700 hover:underline">{ch.name}</a>
							{:else}
								<span class="font-mono text-zinc-500">{p.channel_id}</span>
							{/if}
						</Table.Cell>
						<Table.Cell class="text-xs text-zinc-500">
							{new Date(p.created_at).toLocaleString()}
						</Table.Cell>
					</Table.Row>
				{/each}
			</Table.Body>
		</Table.Root>
	{/if}
</div>
