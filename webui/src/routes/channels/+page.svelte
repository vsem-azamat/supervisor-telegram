<script lang="ts">
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { apiFetch } from '$lib/api/client';
	import type { components } from '$lib/api/types';

	type Channel = components['schemas']['ChannelRead'];

	let channels = $state<Channel[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	$effect(() => {
		void (async () => {
			const res = await apiFetch<Channel[]>('/api/channels');
			if (res.error) {
				error = res.error.message;
			} else {
				channels = res.data;
			}
			loading = false;
		})();
	});
</script>

<div class="space-y-4 px-6 py-6">
	<h2 class="text-lg font-semibold tracking-tight">Channels</h2>
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
							<a href={`/channels/${c.id}`} class="font-medium text-zinc-900 hover:underline">{c.name}</a>
							{#if c.username}
								<span class="ml-1 text-xs text-zinc-500">@{c.username}</span>
							{/if}
						</Table.Cell>
						<Table.Cell class="text-xs uppercase text-zinc-600">{c.language}</Table.Cell>
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
