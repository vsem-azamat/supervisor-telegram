<script lang="ts">
	import { goto } from '$app/navigation';
	import { Button } from '$lib/components/ui/button/index.js';
	import ChatAvatar from '$lib/components/chat/ChatAvatar.svelte';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import { CheckCircle2, Hash, MessageSquare, Network, Plus, Search, ShieldCheck, ShieldQuestion, Tv, XCircle } from '@lucide/svelte';
	import type { components } from '$lib/api/types';

	type Channel = components['schemas']['ChannelRead'];
	type Chat = components['schemas']['ChatRead'];
	type Filter = 'all' | 'chat' | 'channel';
	type Resource = {
		key: string;
		type: 'chat' | 'channel';
		id: number;
		title: string;
		subtitle: string;
		status: string;
		statusKind: 'enabled' | 'disabled' | 'guarded' | 'basic';
		metric: string;
		identity: string;
		path: string;
		hasPhoto?: boolean;
	};

	const chats = useLivePoll<Chat[]>('/api/chats', 60_000);
	const channels = useLivePoll<Channel[]>('/api/channels', 60_000);

	let filter = $state<Filter>('all');
	let query = $state('');

	const resources = $derived.by<Resource[]>(() => {
		const chatRows = (chats.data ?? []).map((chat) => ({
			key: `chat:${chat.id}`,
			type: 'chat' as const,
			id: chat.id,
			title: chat.title ?? `#${chat.id}`,
			subtitle: chat.relation_notes ?? '',
			status: [chat.is_captcha_enabled ? 'captcha' : null, chat.is_welcome_enabled ? 'welcome' : null]
				.filter(Boolean)
				.join(', ') || 'basic',
			statusKind: chat.is_captcha_enabled || chat.is_welcome_enabled ? ('guarded' as const) : ('basic' as const),
			metric:
				chat.member_count === null || chat.member_count === undefined
					? '-'
					: chat.member_count.toLocaleString(),
			identity: String(chat.id),
			path: `/chats/${chat.id}`,
			hasPhoto: chat.has_photo
		}));

		const channelRows = (channels.data ?? []).map((channel) => ({
			key: `channel:${channel.id}`,
			type: 'channel' as const,
			id: channel.id,
			title: channel.name,
			subtitle: channel.username ? `@${channel.username}` : channel.description,
			status: channel.enabled ? 'enabled' : 'disabled',
			statusKind: channel.enabled ? ('enabled' as const) : ('disabled' as const),
			metric: `${channel.max_posts_per_day}/day`,
			identity: String(channel.telegram_id),
			path: `/channels/${channel.id}`
		}));

		return [...channelRows, ...chatRows].sort((a, b) => {
			const title = a.title.localeCompare(b.title);
			if (title !== 0) return title;
			return a.key.localeCompare(b.key);
		});
	});

	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		return resources.filter((resource) => {
			if (filter !== 'all' && resource.type !== filter) return false;
			if (!q) return true;
			return [resource.title, resource.subtitle, resource.status, resource.identity]
				.join(' ')
				.toLowerCase()
				.includes(q);
		});
	});

	const summary = $derived.by(() => {
		const chatCount = chats.data?.length ?? 0;
		const channelCount = channels.data?.length ?? 0;
		const enabledChannels = channels.data?.filter((channel) => channel.enabled).length ?? 0;
		const members =
			chats.data?.reduce((acc, chat) => acc + (chat.member_count ?? 0), 0).toLocaleString() ?? '0';
		return { total: chatCount + channelCount, chatCount, channelCount, enabledChannels, members };
	});

	const loading = $derived((chats.loading && !chats.data) || (channels.loading && !channels.data));
	const error = $derived(chats.error || channels.error);
</script>

<div class="mx-auto max-w-6xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Catalog</h2>
			<p class="mt-0.5 text-xs text-zinc-500">Telegram resources managed by the platform.</p>
		</div>
		<div class="flex items-center gap-2">
			{#if chats.lastUpdatedAt || channels.lastUpdatedAt}
				<span class="hidden text-xs text-zinc-500 md:inline">
					Updated {(chats.lastUpdatedAt ?? channels.lastUpdatedAt)?.toLocaleTimeString()}
				</span>
			{/if}
			<Button variant="outline" size="sm" href="/catalog/hierarchy">
				<Network class="h-3.5 w-3.5" />
				Hierarchy
			</Button>
			<Button size="sm" href="/channels">
				<Plus class="h-3.5 w-3.5" />
				New channel
			</Button>
		</div>
	</header>

	<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
		<div class="flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<Hash class="h-4 w-4 text-zinc-500" />
			<div class="min-w-0">
				<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Total</div>
				<div class="text-lg font-semibold tracking-tight text-zinc-900">{summary.total}</div>
			</div>
		</div>
		<div class="flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<MessageSquare class="h-4 w-4 text-zinc-500" />
			<div class="min-w-0">
				<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Chats</div>
				<div class="text-lg font-semibold tracking-tight text-zinc-900">{summary.chatCount}</div>
			</div>
		</div>
		<div class="flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<Tv class="h-4 w-4 text-zinc-500" />
			<div class="min-w-0">
				<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Channels</div>
				<div class="text-lg font-semibold tracking-tight text-zinc-900">{summary.channelCount}</div>
			</div>
		</div>
		<div class="flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<Hash class="h-4 w-4 text-zinc-500" />
			<div class="min-w-0">
				<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Members</div>
				<div class="text-lg font-semibold tracking-tight text-zinc-900">{summary.members}</div>
			</div>
		</div>
	</div>

	<div class="flex flex-col gap-3 border-b border-zinc-200 pb-3 md:flex-row md:items-center md:justify-between">
		<div class="flex items-center gap-1">
			{#each ['all', 'chat', 'channel'] as value}
				<button
					type="button"
					class="rounded-md px-3 py-1.5 text-sm font-medium {filter === value
						? 'bg-zinc-900 text-white'
						: 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900'}"
					onclick={() => (filter = value as Filter)}
				>
					{value === 'all' ? 'All' : value === 'chat' ? 'Chats' : 'Channels'}
				</button>
			{/each}
		</div>
		<div class="relative w-full md:w-72">
			<Search class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-400" />
			<Input bind:value={query} placeholder="Search resources..." class="h-8 pl-8" />
		</div>
	</div>

	<div class="overflow-hidden rounded-md border border-zinc-200 bg-white">
		{#if loading}
			<p class="p-4 text-sm text-zinc-500">Loading...</p>
		{:else if error}
			<p class="p-4 text-sm text-red-600">Error: {error}</p>
		{:else if filtered.length === 0}
			<p class="p-4 text-sm text-zinc-500">No resources found.</p>
		{:else}
			<Table.Root>
				<Table.Header>
					<Table.Row class="bg-zinc-50/80">
						<Table.Head>Name</Table.Head>
						<Table.Head class="w-16 text-center">Type</Table.Head>
						<Table.Head class="w-20 text-center">Status</Table.Head>
						<Table.Head class="w-28">Metric</Table.Head>
						<Table.Head class="w-44">Telegram ID</Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body>
					{#each filtered as resource (resource.key)}
						<Table.Row class="cursor-pointer hover:bg-zinc-50" onclick={() => goto(resource.path)}>
							<Table.Cell>
								<div class="flex min-w-0 items-center gap-2">
									{#if resource.type === 'chat'}
										<ChatAvatar
											chatId={resource.id}
											title={resource.title}
											hasPhoto={resource.hasPhoto ?? false}
											size="sm"
										/>
									{:else}
										<span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-zinc-600">
											<Tv class="h-3.5 w-3.5" />
										</span>
									{/if}
									<div class="min-w-0">
										<div class="truncate font-medium text-zinc-900">{resource.title}</div>
										{#if resource.subtitle}
											<div class="truncate text-xs text-zinc-500">{resource.subtitle}</div>
										{/if}
									</div>
								</div>
							</Table.Cell>
							<Table.Cell class="text-center">
								<span
									class="inline-flex h-7 w-7 items-center justify-center rounded-md border border-zinc-200 bg-zinc-50 text-zinc-600"
									title={resource.type === 'chat' ? 'Chat' : 'Channel'}
									aria-label={resource.type === 'chat' ? 'Chat' : 'Channel'}
								>
									{#if resource.type === 'chat'}
										<MessageSquare class="h-3.5 w-3.5" />
									{:else}
										<Tv class="h-3.5 w-3.5" />
									{/if}
								</span>
							</Table.Cell>
							<Table.Cell class="text-center">
								<span
									class="inline-flex h-7 w-7 items-center justify-center rounded-md border border-zinc-200 bg-white {resource.statusKind === 'enabled' || resource.statusKind === 'guarded'
										? 'text-emerald-600'
										: resource.statusKind === 'disabled'
											? 'text-zinc-400'
											: 'text-zinc-500'}"
									title={resource.status}
									aria-label={resource.status}
								>
									{#if resource.statusKind === 'enabled'}
										<CheckCircle2 class="h-3.5 w-3.5" />
									{:else if resource.statusKind === 'disabled'}
										<XCircle class="h-3.5 w-3.5" />
									{:else if resource.statusKind === 'guarded'}
										<ShieldCheck class="h-3.5 w-3.5" />
									{:else}
										<ShieldQuestion class="h-3.5 w-3.5" />
									{/if}
								</span>
							</Table.Cell>
							<Table.Cell class="text-sm text-zinc-700">{resource.metric}</Table.Cell>
							<Table.Cell class="font-mono text-xs text-zinc-600">{resource.identity}</Table.Cell>
						</Table.Row>
					{/each}
				</Table.Body>
			</Table.Root>
		{/if}
	</div>
</div>
