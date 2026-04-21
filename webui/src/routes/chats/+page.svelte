<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { goto } from '$app/navigation';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import type { components } from '$lib/api/types';

	type Chat = components['schemas']['ChatRead'];
	const chats = useLivePoll<Chat[]>('/api/chats', 60_000);

	function fmtMembers(n: number | null | undefined): string {
		return n === null || n === undefined ? '—' : n.toLocaleString();
	}

	function fmtDate(iso: string): string {
		return new Date(iso).toLocaleDateString();
	}
</script>

<div class="mx-auto max-w-5xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<h2 class="text-lg font-semibold tracking-tight">Chats</h2>
		{#if chats.lastUpdatedAt}
			<span class="text-xs text-zinc-500">Updated {chats.lastUpdatedAt.toLocaleTimeString()}</span>
		{/if}
	</header>

	<Card.Root>
		<Card.Content class="pt-6">
			{#if chats.loading}
				<p class="text-sm text-zinc-500">Loading…</p>
			{:else if chats.error}
				<p class="text-sm text-red-600">Error: {chats.error}</p>
			{:else if !chats.data || chats.data.length === 0}
				<p class="text-sm text-zinc-500">No chats registered yet.</p>
			{:else}
				<Table.Root>
					<Table.Header>
						<Table.Row>
							<Table.Head>Title</Table.Head>
							<Table.Head class="w-24">Members</Table.Head>
							<Table.Head class="w-24">Captcha</Table.Head>
							<Table.Head class="w-24">Welcome</Table.Head>
							<Table.Head class="w-28">Created</Table.Head>
						</Table.Row>
					</Table.Header>
					<Table.Body>
						{#each chats.data as chat (chat.id)}
							<Table.Row
								class="cursor-pointer hover:bg-zinc-50"
								onclick={() => goto(`/chats/${chat.id}`)}
							>
								<Table.Cell class="font-medium">{chat.title ?? `#${chat.id}`}</Table.Cell>
								<Table.Cell>{fmtMembers(chat.member_count)}</Table.Cell>
								<Table.Cell>{chat.is_captcha_enabled ? 'on' : 'off'}</Table.Cell>
								<Table.Cell>{chat.is_welcome_enabled ? 'on' : 'off'}</Table.Cell>
								<Table.Cell class="text-xs text-zinc-500">{fmtDate(chat.created_at)}</Table.Cell>
							</Table.Row>
						{/each}
					</Table.Body>
				</Table.Root>
			{/if}
		</Card.Content>
	</Card.Root>
</div>
