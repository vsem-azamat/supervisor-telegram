<script lang="ts">
	// The administrator's view of every chat. It used to be one page that served
	// two audiences, branching on `auth.me` in nine places to decide which
	// columns, which endpoint and which sentence to show. Half of those branches
	// were the difference between a moderation console and a public directory,
	// which is more than a conditional should be carrying.
	//
	// The public half now lives at `/`, reads `/api/public/catalog`, and cannot
	// accidentally inherit an admin column.
	import { goto } from '$app/navigation';
	import { apiFetch } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button/index.js';
	import ChatAvatar from '$lib/components/chat/ChatAvatar.svelte';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import {
		CheckCircle2,
		Hash,
		MessageSquare,
		Network,
		Search,
		ShieldCheck,
		ShieldQuestion,
		XCircle
	} from '@lucide/svelte';
	import type { components } from '$lib/api/types';

	type Chat = components['schemas']['ChatRead'];
	type Resource = {
		key: string;
		id: number;
		title: string;
		subtitle: string;
		status: string;
		statusKind: 'enabled' | 'disabled' | 'guarded' | 'pending';
		metric: string;
		identity: string;
		path: string;
		hasPhoto: boolean;
	};

	let query = $state('');
	let resources = $state<Resource[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let lastUpdatedAt = $state<Date | null>(null);

	function toResources(chats: Chat[]): Resource[] {
		return chats
			.map((chat) => ({
				key: `chat:${chat.id}`,
				id: chat.id,
				title: chat.title ?? `#${chat.id}`,
				subtitle: chat.relation_notes ?? '',
				status:
					chat.resource_status === 'approved'
						? [chat.is_captcha_enabled ? 'captcha' : null, chat.is_welcome_enabled ? 'welcome' : null]
								.filter(Boolean)
								.join(', ') || 'approved'
						: chat.resource_status === 'disabled'
							? 'disabled'
							: 'pending approval',
				statusKind:
					chat.resource_status === 'disabled'
						? ('disabled' as const)
						: chat.resource_status === 'discovered'
							? ('pending' as const)
							: chat.is_captcha_enabled || chat.is_welcome_enabled
								? ('guarded' as const)
								: ('enabled' as const),
				metric:
					chat.member_count === null || chat.member_count === undefined
						? '-'
						: chat.member_count.toLocaleString(),
				identity: String(chat.id),
				path: `/admin/chats/${chat.id}`,
				hasPhoto: chat.has_photo ?? false
			}))
			.sort((a, b) => {
				const title = a.title.localeCompare(b.title);
				if (title !== 0) return title;
				return a.key.localeCompare(b.key);
			});
	}

	async function refreshResources(): Promise<void> {
		loading = true;
		error = null;
		try {
			const res = await apiFetch<Chat[]>('/api/chats');
			if (res.error) {
				error = res.error.message;
				resources = [];
				return;
			}
			resources = toResources(res.data);
			lastUpdatedAt = new Date();
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		void refreshResources();
		const id = setInterval(refreshResources, 60_000);
		return () => clearInterval(id);
	});

	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		return resources.filter((resource) => {
			if (!q) return true;
			return [resource.title, resource.subtitle, resource.status, resource.identity]
				.join(' ')
				.toLowerCase()
				.includes(q);
		});
	});

	const summary = $derived.by(() => ({
		total: resources.length,
		members: resources
			.reduce((acc, resource) => acc + Number(resource.metric.replaceAll(',', '') || 0), 0)
			.toLocaleString()
	}));
</script>

<div class="mx-auto max-w-6xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Catalog</h2>
			<p class="mt-0.5 text-xs text-zinc-500">Telegram chats managed by the platform.</p>
		</div>
		<div class="flex items-center gap-2">
			{#if lastUpdatedAt}
				<span class="hidden text-xs text-zinc-500 md:inline">
					Updated {lastUpdatedAt.toLocaleTimeString()}
				</span>
			{/if}
			<Button variant="outline" size="sm" href="/admin/catalog/hierarchy">
				<Network class="h-3.5 w-3.5" />
				Hierarchy
			</Button>
		</div>
	</header>

	<div class="grid grid-cols-2 gap-3">
		<div class="flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2.5">
			<MessageSquare class="h-4 w-4 text-zinc-500" />
			<div class="min-w-0">
				<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Chats</div>
				<div class="text-lg font-semibold tracking-tight text-zinc-900">{summary.total}</div>
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

	<div class="flex flex-col gap-3 border-b border-zinc-200 pb-3 md:flex-row md:items-center md:justify-end">
		<div class="relative w-full md:w-72">
			<Search
				class="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-zinc-400"
			/>
			<Input bind:value={query} placeholder="Search chats..." class="h-8 pl-8" />
		</div>
	</div>

	<div class="overflow-hidden rounded-md border border-zinc-200 bg-white">
		{#if loading}
			<p class="p-4 text-sm text-zinc-500">Loading...</p>
		{:else if error}
			<p class="p-4 text-sm text-red-600">Error: {error}</p>
		{:else if filtered.length === 0}
			<p class="p-4 text-sm text-zinc-500">No chats found.</p>
		{:else}
			<Table.Root>
				<Table.Header>
					<Table.Row class="bg-zinc-50/80">
						<Table.Head>Name</Table.Head>
						<Table.Head class="w-20 text-center">Status</Table.Head>
						<Table.Head class="w-28">Members</Table.Head>
						<Table.Head class="w-44">Telegram ID</Table.Head>
					</Table.Row>
				</Table.Header>
				<Table.Body>
					{#each filtered as resource (resource.key)}
						<Table.Row class="cursor-pointer hover:bg-zinc-50" onclick={() => goto(resource.path)}>
							<Table.Cell>
								<div class="flex min-w-0 items-center gap-2">
									<ChatAvatar
										chatId={resource.id}
										title={resource.title}
										hasPhoto={resource.hasPhoto}
										size="sm"
									/>
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
									class="inline-flex h-7 w-7 items-center justify-center rounded-md border border-zinc-200 bg-white {resource.statusKind ===
										'enabled' || resource.statusKind === 'guarded'
										? 'text-emerald-600'
										: resource.statusKind === 'pending'
											? 'text-amber-600'
											: 'text-zinc-400'}"
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
