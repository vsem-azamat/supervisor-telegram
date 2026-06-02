<script lang="ts">
	import { goto } from '$app/navigation';
	import { apiFetch } from '$lib/api/client';
	import ChatAvatar from '$lib/components/chat/ChatAvatar.svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import { CheckCircle2, CircleDashed, RefreshCw, Search, Shield, XCircle } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import type { components } from '$lib/api/types';

	type Chat = components['schemas']['ChatRead'];
	type ChatStatus = Chat['resource_status'];
	type Filter = 'all' | ChatStatus;

	const chats = useLivePoll<Chat[]>('/api/chats', 60_000);

	let query = $state('');
	let filter = $state<Filter>('all');
	let busyChatId = $state<number | null>(null);

	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		return (chats.data ?? []).filter((chat) => {
			if (filter !== 'all' && chat.resource_status !== filter) return false;
			if (!q) return true;
			return [chat.title ?? '', chat.relation_notes ?? '', String(chat.id), chat.resource_status]
				.join(' ')
				.toLowerCase()
				.includes(q);
		});
	});

	const counts = $derived.by(() => {
		const rows = chats.data ?? [];
		return {
			all: rows.length,
			discovered: rows.filter((chat) => chat.resource_status === 'discovered').length,
			approved: rows.filter((chat) => chat.resource_status === 'approved').length,
			disabled: rows.filter((chat) => chat.resource_status === 'disabled').length
		};
	});

	function statusLabel(status: ChatStatus): string {
		if (status === 'approved') return 'Approved';
		if (status === 'disabled') return 'Disabled';
		return 'Pending';
	}

	function statusTone(status: ChatStatus): 'default' | 'secondary' | 'destructive' {
		if (status === 'approved') return 'default';
		if (status === 'disabled') return 'secondary';
		return 'secondary';
	}

	async function setStatus(chat: Chat, status: ChatStatus, event?: MouseEvent): Promise<void> {
		event?.stopPropagation();
		if (chat.resource_status === status) return;

		busyChatId = chat.id;
		const res = await apiFetch<Chat>(`/api/chats/${chat.id}`, {
			method: 'PATCH',
			body: JSON.stringify({ resource_status: status })
		});
		busyChatId = null;

		if (res.error) {
			toast.error(res.error.message);
			return;
		}

		toast.success(`${res.data.title ?? `#${res.data.id}`} is ${statusLabel(status).toLowerCase()}`);
		await chats.refresh();
	}
</script>

<div class="mx-auto max-w-6xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between gap-3">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Chats</h2>
			<p class="mt-0.5 text-xs text-zinc-500">Approve discovered Telegram resources before the bot operates there.</p>
		</div>
		<div class="flex items-center gap-3 text-xs text-zinc-500">
			{#if chats.error}
				<span class="text-red-600">Error: {chats.error}</span>
			{:else if chats.lastUpdatedAt}
				<span class="hidden md:inline">Updated {chats.lastUpdatedAt.toLocaleTimeString()}</span>
			{/if}
			<Button variant="outline" size="sm" onclick={() => chats.refresh()}>
				<RefreshCw class="h-3.5 w-3.5" />
				Refresh
			</Button>
		</div>
	</header>

	<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
		<div class="rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Total</div>
			<div class="text-lg font-semibold tracking-tight text-zinc-900">{counts.all}</div>
		</div>
		<div class="rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Pending</div>
			<div class="text-lg font-semibold tracking-tight text-zinc-900">{counts.discovered}</div>
		</div>
		<div class="rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Approved</div>
			<div class="text-lg font-semibold tracking-tight text-zinc-900">{counts.approved}</div>
		</div>
		<div class="rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Disabled</div>
			<div class="text-lg font-semibold tracking-tight text-zinc-900">{counts.disabled}</div>
		</div>
	</div>

	<div class="flex flex-col gap-3 border-b border-zinc-200 pb-3 md:flex-row md:items-center md:justify-between">
		<div class="flex flex-wrap items-center gap-1">
			{#each ['all', 'discovered', 'approved', 'disabled'] as value}
				<button
					type="button"
					class="rounded-md px-3 py-1.5 text-sm font-medium {filter === value
						? 'bg-zinc-900 text-white'
						: 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900'}"
					onclick={() => (filter = value as Filter)}
				>
					{value === 'all' ? 'All' : statusLabel(value as ChatStatus)}
				</button>
			{/each}
		</div>
		<div class="relative w-full md:w-72">
			<Search class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-400" />
			<Input bind:value={query} placeholder="Search chats..." class="h-8 pl-8" />
		</div>
	</div>

	<div class="overflow-hidden rounded-md border border-zinc-200 bg-white">
		{#if chats.loading && !chats.data}
			<p class="p-4 text-sm text-zinc-500">Loading...</p>
		{:else if chats.error && !chats.data}
			<p class="p-4 text-sm text-red-600">Error: {chats.error}</p>
		{:else if filtered.length === 0}
			<p class="p-4 text-sm text-zinc-500">No chats found.</p>
		{:else}
			<Table.Root>
				<Table.Header>
					<Table.Row class="bg-zinc-50/80">
						<Table.Head>Name</Table.Head>
						<Table.Head class="w-28">Status</Table.Head>
						<Table.Head class="w-28">Members</Table.Head>
						<Table.Head class="w-32">Features</Table.Head>
						<Table.Head class="w-48 text-right">Actions</Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body>
					{#each filtered as chat (chat.id)}
						<Table.Row class="cursor-pointer hover:bg-zinc-50" onclick={() => goto(`/chats/${chat.id}`)}>
							<Table.Cell>
								<div class="flex min-w-0 items-center gap-2">
									<ChatAvatar chatId={chat.id} title={chat.title} hasPhoto={chat.has_photo} size="sm" />
									<div class="min-w-0">
										<div class="truncate font-medium text-zinc-900">{chat.title ?? `#${chat.id}`}</div>
										<div class="truncate font-mono text-xs text-zinc-500">{chat.id}</div>
									</div>
								</div>
							</Table.Cell>
							<Table.Cell>
								<Badge variant={statusTone(chat.resource_status)}>
									{#if chat.resource_status === 'approved'}
										<CheckCircle2 class="h-3 w-3" />
									{:else if chat.resource_status === 'disabled'}
										<XCircle class="h-3 w-3" />
									{:else}
										<CircleDashed class="h-3 w-3" />
									{/if}
									{statusLabel(chat.resource_status)}
								</Badge>
							</Table.Cell>
							<Table.Cell class="text-sm text-zinc-700">
								{chat.member_count === null || chat.member_count === undefined ? '-' : chat.member_count.toLocaleString()}
							</Table.Cell>
							<Table.Cell class="text-xs text-zinc-600">
								{[
									chat.is_captcha_enabled ? 'captcha' : null,
									chat.is_welcome_enabled ? 'welcome' : null
								]
									.filter(Boolean)
									.join(', ') || 'basic'}
							</Table.Cell>
							<Table.Cell>
								<div class="flex justify-end gap-1">
									{#if chat.resource_status !== 'approved'}
										<Button
											size="sm"
											disabled={busyChatId === chat.id}
											onclick={(event) => setStatus(chat, 'approved', event)}
										>
											<Shield class="h-3.5 w-3.5" />
											Approve
										</Button>
									{/if}
									{#if chat.resource_status !== 'disabled'}
										<Button
											variant="outline"
											size="sm"
											disabled={busyChatId === chat.id}
											onclick={(event) => setStatus(chat, 'disabled', event)}
										>
											Disable
										</Button>
									{/if}
								</div>
							</Table.Cell>
						</Table.Row>
					{/each}
				</Table.Body>
			</Table.Root>
		{/if}
	</div>
</div>
