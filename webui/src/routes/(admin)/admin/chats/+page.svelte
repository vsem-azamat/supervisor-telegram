<script lang="ts">
	// Every chat the bot knows, in one table.
	//
	// There used to be two of these — /admin/catalog and /admin/chats — listing
	// the same rows from the same endpoint, differing in which four columns they
	// chose. Two screens for one question is two places to look and one of them
	// is always the stale one, so the catalogue now redirects here.
	import { goto } from '$app/navigation';
	import { apiFetch } from '$lib/api/client';
	import ChatAvatar from '$lib/components/chat/ChatAvatar.svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import { num } from '$lib/format';
	import {
		CheckCircle2,
		CircleDashed,
		Globe,
		Network,
		RefreshCw,
		Search,
		Shield,
		XCircle
	} from '@lucide/svelte';
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
			disabled: rows.filter((chat) => chat.resource_status === 'disabled').length,
			// Counted the way the public endpoint counts: approved *and* carrying a
			// link. A chat with a link but no approval is not on the site, and this
			// number would be a small lie if it said otherwise.
			listed: rows.filter((chat) => chat.resource_status === 'approved' && chat.public_link).length,
			// A sum over the chats that have a recorded snapshot. A chat Telegram
			// declined to answer about carries null and contributes nothing, so
			// this is a floor rather than a claim about the whole network.
			members: rows.reduce((acc, chat) => acc + (chat.member_count ?? 0), 0)
		};
	});

	function statusLabel(status: ChatStatus): string {
		if (status === 'approved') return 'Одобрен';
		if (status === 'disabled') return 'Отключён';
		return 'На проверке';
	}

	function statusTone(status: ChatStatus): 'default' | 'secondary' | 'destructive' {
		if (status === 'approved') return 'default';
		return 'secondary';
	}

	const FILTERS: { value: Filter; label: string }[] = [
		{ value: 'all', label: 'Все' },
		{ value: 'discovered', label: 'На проверке' },
		{ value: 'approved', label: 'Одобренные' },
		{ value: 'disabled', label: 'Отключённые' }
	];

	function filterCount(value: Filter): number {
		if (value === 'all') return counts.all;
		if (value === 'discovered') return counts.discovered;
		if (value === 'approved') return counts.approved;
		return counts.disabled;
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

		toast.success(`${res.data.title ?? `#${res.data.id}`} — ${statusLabel(status).toLowerCase()}`);
		await chats.refresh();
	}
</script>

<div class="mx-auto max-w-6xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between gap-3">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Чаты</h2>
			<p class="mt-0.5 text-xs text-zinc-500">
				Бот работает только в одобренных чатах. Остальные он видит, но молчит.
			</p>
		</div>
		<div class="flex items-center gap-3 text-xs text-zinc-500">
			{#if chats.error}
				<span class="text-red-600">Ошибка: {chats.error}</span>
			{:else if chats.lastUpdatedAt}
				<span class="hidden md:inline">Обновлено {chats.lastUpdatedAt.toLocaleTimeString('ru-RU')}</span>
			{/if}
			<Button variant="outline" size="sm" href="/admin/hierarchy">
				<Network class="h-3.5 w-3.5" />
				Иерархия
			</Button>
			<Button variant="outline" size="sm" onclick={() => chats.refresh()}>
				<RefreshCw class="h-3.5 w-3.5" />
				Обновить
			</Button>
		</div>
	</header>

	<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
		<div class="rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Чатов</div>
			<div class="font-mono text-xl font-semibold tracking-tight text-zinc-900 tabular-nums">
				{counts.all}
			</div>
		</div>
		<div class="rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Участников</div>
			<div class="font-mono text-xl font-semibold tracking-tight text-zinc-900 tabular-nums">
				{num(counts.members)}
			</div>
		</div>
		<div
			class="rounded-md border bg-white px-3 py-2.5 {counts.discovered > 0
				? 'border-amber-300'
				: 'border-zinc-200'}"
		>
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">На проверке</div>
			<div
				class="font-mono text-xl font-semibold tracking-tight tabular-nums {counts.discovered > 0
					? 'text-amber-700'
					: 'text-zinc-900'}"
			>
				{counts.discovered}
			</div>
		</div>
		<div class="rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">На сайте</div>
			<div class="font-mono text-xl font-semibold tracking-tight text-zinc-900 tabular-nums">
				{counts.listed}
			</div>
		</div>
	</div>

	<div class="flex flex-col gap-3 border-b border-zinc-200 pb-3 md:flex-row md:items-center md:justify-between">
		<div class="flex flex-wrap items-center gap-1">
			{#each FILTERS as option (option.value)}
				<button
					type="button"
					class="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium {filter ===
					option.value
						? 'bg-zinc-900 text-white'
						: 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900'}"
					onclick={() => (filter = option.value)}
				>
					{option.label}
					<span
						class="font-mono text-xs tabular-nums {filter === option.value
							? 'text-white/60'
							: 'text-zinc-400'}"
					>
						{filterCount(option.value)}
					</span>
				</button>
			{/each}
		</div>
		<div class="relative w-full md:w-72">
			<Search class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-400" />
			<Input bind:value={query} placeholder="Поиск по названию или id…" class="h-8 pl-8" />
		</div>
	</div>

	<div class="overflow-hidden rounded-md border border-zinc-200 bg-white">
		{#if chats.loading && !chats.data}
			<p class="p-4 text-sm text-zinc-500">Загружаем…</p>
		{:else if chats.error && !chats.data}
			<p class="p-4 text-sm text-red-600">Ошибка: {chats.error}</p>
		{:else if filtered.length === 0}
			<p class="p-4 text-sm text-zinc-500">
				{query ? `По запросу «${query}» ничего не нашлось.` : 'Здесь пока пусто.'}
			</p>
		{:else}
			<Table.Root>
				<Table.Header>
					<Table.Row class="bg-zinc-50/80">
						<Table.Head>Чат</Table.Head>
						<Table.Head class="w-32">Статус</Table.Head>
						<Table.Head class="w-24 text-right">Участников</Table.Head>
						<Table.Head class="w-32">Защита</Table.Head>
						<Table.Head class="w-48 text-right">Действия</Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body>
					{#each filtered as chat (chat.id)}
						<Table.Row class="cursor-pointer hover:bg-zinc-50" onclick={() => goto(`/admin/chats/${chat.id}`)}>
							<Table.Cell>
								<div class="flex min-w-0 items-center gap-2">
									<ChatAvatar chatId={chat.id} title={chat.title} hasPhoto={chat.has_photo} size="sm" />
									<div class="min-w-0">
										<div class="flex items-center gap-1.5">
											<span class="truncate font-medium text-zinc-900">{chat.title ?? `#${chat.id}`}</span>
											{#if chat.public_link && chat.resource_status === 'approved'}
												<Globe class="h-3 w-3 shrink-0 text-zinc-400" aria-label="На публичном сайте" />
											{/if}
										</div>
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
							<Table.Cell class="text-right font-mono text-sm text-zinc-700 tabular-nums">
								{num(chat.member_count)}
							</Table.Cell>
							<Table.Cell class="text-xs text-zinc-600">
								{[
									chat.is_captcha_enabled ? 'капча' : null,
									chat.is_welcome_enabled ? 'приветствие' : null
								]
									.filter(Boolean)
									.join(', ') || '—'}
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
											Одобрить
										</Button>
									{/if}
									{#if chat.resource_status !== 'disabled'}
										<Button
											variant="outline"
											size="sm"
											disabled={busyChatId === chat.id}
											onclick={(event) => setStatus(chat, 'disabled', event)}
										>
											Отключить
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
