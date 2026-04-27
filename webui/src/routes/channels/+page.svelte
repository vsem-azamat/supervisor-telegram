<script lang="ts">
	import { goto } from '$app/navigation';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { apiFetch } from '$lib/api/client';
	import { toast } from 'svelte-sonner';
	import type { components } from '$lib/api/types';

	type Channel = components['schemas']['ChannelRead'];
	type ChannelDetail = components['schemas']['ChannelDetail'];

	let channels = $state<Channel[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	let formOpen = $state(false);
	let saving = $state(false);
	let form = $state({ telegram_id: '', name: '', language: 'ru', description: '' });

	async function load(): Promise<void> {
		loading = true;
		const res = await apiFetch<Channel[]>('/api/channels');
		if (res.error) error = res.error.message;
		else {
			channels = res.data;
			error = null;
		}
		loading = false;
	}

	$effect(() => {
		void load();
	});

	async function createChannel(): Promise<void> {
		const tid = parseInt(form.telegram_id, 10);
		if (!Number.isFinite(tid) || !form.name.trim()) {
			toast.error('telegram_id (numeric) and name are required');
			return;
		}
		saving = true;
		const res = await apiFetch<ChannelDetail>('/api/channels', {
			method: 'POST',
			body: JSON.stringify({
				telegram_id: tid,
				name: form.name.trim(),
				language: form.language.trim() || 'ru',
				description: form.description
			})
		});
		saving = false;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success(`Channel #${res.data.id} created`);
			formOpen = false;
			form = { telegram_id: '', name: '', language: 'ru', description: '' };
			await goto(`/channels/${res.data.id}`);
		}
	}
</script>

<div class="space-y-4 px-6 py-6">
	<header class="flex items-center justify-between">
		<h2 class="text-lg font-semibold tracking-tight">Channels</h2>
		<Button size="sm" onclick={() => (formOpen = !formOpen)}>
			{formOpen ? 'Cancel' : 'New channel'}
		</Button>
	</header>

	{#if formOpen}
		<div class="grid grid-cols-1 gap-3 rounded-md border border-zinc-200 bg-zinc-50 p-4 md:grid-cols-2">
			<label class="space-y-1 text-xs">
				<span class="text-zinc-600">Telegram ID</span>
				<Input bind:value={form.telegram_id} placeholder="-1001234567890" />
			</label>
			<label class="space-y-1 text-xs">
				<span class="text-zinc-600">Name</span>
				<Input bind:value={form.name} placeholder="My channel" />
			</label>
			<label class="space-y-1 text-xs">
				<span class="text-zinc-600">Language</span>
				<Input bind:value={form.language} placeholder="ru" />
			</label>
			<label class="space-y-1 text-xs md:col-span-2">
				<span class="text-zinc-600">Description (optional)</span>
				<Input bind:value={form.description} />
			</label>
			<div class="flex items-center justify-end gap-2 md:col-span-2">
				<Button variant="ghost" size="sm" onclick={() => (formOpen = false)} disabled={saving}>
					Cancel
				</Button>
				<Button size="sm" onclick={createChannel} disabled={saving}>
					{saving ? 'Creating…' : 'Create'}
				</Button>
			</div>
		</div>
	{/if}

	{#if loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if error}
		<p class="text-sm text-red-600">Error: {error}</p>
	{:else}
		<Table.Root>
			<Table.Header>
				<Table.Row>
					<Table.Head>Name</Table.Head>
					<Table.Head class="w-32">Language</Table.Head>
					<Table.Head class="w-32">Enabled</Table.Head>
					<Table.Head class="w-32">Posts/day</Table.Head>
					<Table.Head class="w-40">Telegram ID</Table.Head>
				</Table.Row>
			</Table.Header>
			<Table.Body>
				{#each channels as c (c.id)}
					<Table.Row>
						<Table.Cell>
							<a
								href={`/channels/${c.id}`}
								class="font-medium text-zinc-900 hover:underline">{c.name}</a
							>
							{#if c.username}
								<span class="ml-1 text-xs text-zinc-500">@{c.username}</span>
							{/if}
						</Table.Cell>
						<Table.Cell class="text-xs text-zinc-600 uppercase">{c.language}</Table.Cell>
						<Table.Cell>
							{#if c.enabled}<Badge>on</Badge>{:else}<Badge variant="secondary">off</Badge>{/if}
						</Table.Cell>
						<Table.Cell class="text-sm text-zinc-700">{c.max_posts_per_day}</Table.Cell>
						<Table.Cell class="font-mono text-xs text-zinc-600">{c.telegram_id}</Table.Cell>
					</Table.Row>
				{/each}
			</Table.Body>
		</Table.Root>
	{/if}
</div>
