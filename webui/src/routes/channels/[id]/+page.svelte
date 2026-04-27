<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { apiFetch } from '$lib/api/client';
	import { toast } from 'svelte-sonner';
	import type { components } from '$lib/api/types';

	type ChannelDetail = components['schemas']['ChannelDetail'];
	type ChannelSourceRead = components['schemas']['ChannelSourceRead'];
	type ChannelMutationResponse = components['schemas']['ChannelMutationResponse'];

	let channel = $state<ChannelDetail | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);

	let editing = $state(false);
	let saving = $state(false);
	let edit = $state({
		name: '',
		description: '',
		language: '',
		enabled: true,
		max_posts_per_day: 3,
		footer_template: '',
		posting_schedule: '',
		publish_schedule: ''
	});

	let newSourceUrl = $state('');
	let addingSource = $state(false);

	const channelId = $derived(page.params.id);

	function snapshotEdit(c: ChannelDetail): void {
		edit = {
			name: c.name,
			description: c.description ?? '',
			language: c.language,
			enabled: c.enabled,
			max_posts_per_day: c.max_posts_per_day,
			footer_template: c.footer_template ?? '',
			posting_schedule: (c.posting_schedule ?? []).join(', '),
			publish_schedule: (c.publish_schedule ?? []).join(', ')
		};
	}

	function parseSchedule(s: string): string[] | null {
		const parts = s
			.split(',')
			.map((p) => p.trim())
			.filter(Boolean);
		return parts.length ? parts : null;
	}

	async function load(): Promise<void> {
		loading = true;
		const res = await apiFetch<ChannelDetail>(`/api/channels/${channelId}`);
		if (res.error) {
			error = res.error.message;
			channel = null;
		} else {
			channel = res.data;
			snapshotEdit(res.data);
			error = null;
		}
		loading = false;
	}

	$effect(() => {
		void load();
	});

	async function saveEdit(): Promise<void> {
		if (!channel) return;
		saving = true;
		const res = await apiFetch<ChannelDetail>(`/api/channels/${channelId}`, {
			method: 'PATCH',
			body: JSON.stringify({
				name: edit.name,
				description: edit.description,
				language: edit.language,
				enabled: edit.enabled,
				max_posts_per_day: edit.max_posts_per_day,
				footer_template: edit.footer_template || null,
				posting_schedule: parseSchedule(edit.posting_schedule),
				publish_schedule: parseSchedule(edit.publish_schedule)
			})
		});
		saving = false;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success('Channel updated');
			channel = res.data;
			snapshotEdit(res.data);
			editing = false;
		}
	}

	async function deleteChannel(): Promise<void> {
		if (!channel) return;
		if (!confirm(`Delete channel "${channel.name}"? This is permanent.`)) return;
		const res = await apiFetch<ChannelMutationResponse>(`/api/channels/${channelId}`, {
			method: 'DELETE'
		});
		if (res.error) toast.error(res.error.message);
		else {
			toast.success(res.data.message);
			await goto('/channels');
		}
	}

	async function addSource(): Promise<void> {
		const url = newSourceUrl.trim();
		if (!url) return;
		addingSource = true;
		const res = await apiFetch<ChannelSourceRead>(`/api/channels/${channelId}/sources`, {
			method: 'POST',
			body: JSON.stringify({ url })
		});
		addingSource = false;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success('Source added');
			newSourceUrl = '';
			await load();
		}
	}

	async function toggleSource(s: ChannelSourceRead): Promise<void> {
		const res = await apiFetch<ChannelSourceRead>(
			`/api/channels/${channelId}/sources/${s.id}`,
			{ method: 'PATCH', body: JSON.stringify({ enabled: !s.enabled }) }
		);
		if (res.error) toast.error(res.error.message);
		else await load();
	}

	async function removeSource(s: ChannelSourceRead): Promise<void> {
		if (!confirm(`Remove source "${s.title ?? s.url}"?`)) return;
		const res = await apiFetch<ChannelMutationResponse>(
			`/api/channels/${channelId}/sources/${s.id}`,
			{ method: 'DELETE' }
		);
		if (res.error) toast.error(res.error.message);
		else {
			toast.success(res.data.message);
			await load();
		}
	}
</script>

<div class="mx-auto max-w-4xl space-y-4 px-6 py-6">
	{#if loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if error}
		<p class="text-sm text-red-600">Error: {error}</p>
	{:else if channel}
		<header class="flex items-start justify-between gap-4">
			<div>
				<div class="text-xs text-zinc-500">
					<a href="/channels" class="hover:underline">Channels</a> ›
					<span class="font-mono">#{channel.id}</span>
				</div>
				<h2 class="mt-1 text-xl font-semibold tracking-tight">{channel.name}</h2>
				<p class="mt-1 text-sm text-zinc-600">{channel.description || '—'}</p>
			</div>
			<div class="flex shrink-0 items-center gap-2">
				<Button
					variant="outline"
					size="sm"
					onclick={() => (editing = !editing)}
					disabled={saving}
				>
					{editing ? 'Cancel edit' : 'Edit'}
				</Button>
				<Button variant="outline" size="sm" onclick={deleteChannel} disabled={saving || editing}>
					Delete
				</Button>
			</div>
		</header>

		<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
			<Card.Root>
				<Card.Header><Card.Title class="text-sm">Config</Card.Title></Card.Header>
				<Card.Content class="space-y-3 text-sm">
					{#if editing}
						<label class="block space-y-1">
							<span class="text-xs text-zinc-600">Name</span>
							<Input bind:value={edit.name} />
						</label>
						<label class="block space-y-1">
							<span class="text-xs text-zinc-600">Description</span>
							<Input bind:value={edit.description} />
						</label>
						<label class="block space-y-1">
							<span class="text-xs text-zinc-600">Language</span>
							<Input bind:value={edit.language} />
						</label>
						<label class="block space-y-1">
							<span class="text-xs text-zinc-600">Max posts / day</span>
							<Input type="number" bind:value={edit.max_posts_per_day} min="0" />
						</label>
						<label class="flex items-center gap-2 text-xs">
							<input type="checkbox" bind:checked={edit.enabled} />
							<span>Enabled</span>
						</label>
						<label class="block space-y-1">
							<span class="text-xs text-zinc-600">Footer template</span>
							<Input bind:value={edit.footer_template} />
						</label>
						<label class="block space-y-1">
							<span class="text-xs text-zinc-600">Posting schedule (comma-separated HH:MM)</span>
							<Input bind:value={edit.posting_schedule} placeholder="09:00, 13:00, 18:00" />
						</label>
						<label class="block space-y-1">
							<span class="text-xs text-zinc-600">Publish schedule (comma-separated HH:MM)</span>
							<Input bind:value={edit.publish_schedule} />
						</label>
						<div class="flex items-center justify-end gap-2 pt-2">
							<Button variant="ghost" size="sm" onclick={() => (editing = false)} disabled={saving}>
								Cancel
							</Button>
							<Button size="sm" onclick={saveEdit} disabled={saving}>
								{saving ? 'Saving…' : 'Save'}
							</Button>
						</div>
					{:else}
						<div>Telegram ID: <span class="font-mono">{channel.telegram_id}</span></div>
						<div>Language: <span class="uppercase">{channel.language}</span></div>
						<div>Enabled: {channel.enabled ? 'yes' : 'no'}</div>
						<div>Max posts/day: {channel.max_posts_per_day}</div>
						<div>Review chat: <span class="font-mono">{channel.review_chat_id ?? '—'}</span></div>
						<div>Posting schedule: {channel.posting_schedule?.join(', ') ?? '—'}</div>
						<div>Publish schedule: {channel.publish_schedule?.join(', ') ?? '—'}</div>
						<div>Footer: <span class="text-xs text-zinc-500">{channel.footer_template ?? '—'}</span></div>
						<div>Critic: {channel.critic_enabled ?? 'inherit'}</div>
					{/if}
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header><Card.Title class="text-sm">Sources ({channel.sources.length})</Card.Title></Card.Header>
				<Card.Content class="space-y-3">
					<form
						class="flex items-center gap-2"
						onsubmit={(e) => {
							e.preventDefault();
							void addSource();
						}}
					>
						<Input
							bind:value={newSourceUrl}
							placeholder="https://example.com/feed.xml"
							class="flex-1 text-xs"
							disabled={addingSource}
						/>
						<Button type="submit" size="sm" disabled={addingSource || !newSourceUrl.trim()}>
							{addingSource ? '…' : 'Add'}
						</Button>
					</form>
					{#if channel.sources.length === 0}
						<p class="text-sm text-zinc-500">No sources configured.</p>
					{:else}
						<ul class="flex flex-col gap-2 text-sm">
							{#each channel.sources as s (s.id)}
								<li class="flex items-center justify-between gap-2 border-b border-zinc-100 pb-1 last:border-0">
									<span class="truncate" title={s.url}>{s.title ?? s.url}</span>
									<span class="flex shrink-0 items-center gap-1">
										{#if s.error_count > 0}<Badge variant="destructive" class="text-[10px]"
												>err×{s.error_count}</Badge
											>{/if}
										<button
											type="button"
											class="rounded-md px-2 py-0.5 text-[10px] {s.enabled
												? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200'
												: 'bg-zinc-100 text-zinc-500 hover:bg-zinc-200'}"
											onclick={() => toggleSource(s)}
										>
											{s.enabled ? 'on' : 'off'}
										</button>
										<button
											type="button"
											class="rounded-md px-1 text-zinc-400 hover:text-red-600"
											aria-label="Remove source"
											onclick={() => removeSource(s)}
										>
											✕
										</button>
									</span>
								</li>
							{/each}
						</ul>
					{/if}
				</Card.Content>
			</Card.Root>
		</div>

		<Card.Root>
			<Card.Header
				><Card.Title class="text-sm">Recent posts ({channel.recent_posts.length})</Card.Title></Card.Header
			>
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
									<Table.Cell>
										<a href={`/posts/${p.id}`} class="hover:underline">{p.title}</a>
									</Table.Cell>
									<Table.Cell class="text-xs text-zinc-500"
										>{new Date(p.created_at).toLocaleString()}</Table.Cell
									>
								</Table.Row>
							{/each}
						</Table.Body>
					</Table.Root>
				{/if}
			</Card.Content>
		</Card.Root>
	{/if}
</div>
