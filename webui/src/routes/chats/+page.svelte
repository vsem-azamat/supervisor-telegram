<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { goto } from '$app/navigation';
	import ChatAvatar from '$lib/components/chat/ChatAvatar.svelte';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import { MessagesSquare, Network, Shield, UserPlus, Users } from '@lucide/svelte';
	import type { components } from '$lib/api/types';

	type Chat = components['schemas']['ChatRead'];
	const chats = useLivePoll<Chat[]>('/api/chats', 60_000);

	const summary = $derived.by(() => {
		const data = chats.data ?? [];
		const total = data.length;
		const captchaOn = data.filter((c) => c.is_captcha_enabled).length;
		const welcomeOn = data.filter((c) => c.is_welcome_enabled).length;
		const members = data.reduce((acc, c) => acc + (c.member_count ?? 0), 0);
		return { total, captchaOn, welcomeOn, members };
	});

	function fmtMembers(n: number | null | undefined): string {
		return n === null || n === undefined ? '—' : n.toLocaleString();
	}

	function fmtDate(iso: string): string {
		return new Date(iso).toLocaleDateString();
	}
</script>

<div class="mx-auto max-w-5xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Chats</h2>
			<p class="mt-0.5 text-xs text-zinc-500">Managed groups under bot moderation.</p>
		</div>
		<div class="flex items-center gap-3 text-xs text-zinc-500">
			{#if chats.lastUpdatedAt}
				<span>Updated {chats.lastUpdatedAt.toLocaleTimeString()}</span>
			{/if}
			<a
				href="/chats/graph"
				class="flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs font-medium hover:bg-zinc-100"
			>
				<Network class="h-3 w-3" />
				<span>Graph view</span>
			</a>
		</div>
	</header>

	{#if !chats.loading && !chats.error}
		<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
			<div class="flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2.5">
				<MessagesSquare class="h-4 w-4 text-zinc-500" />
				<div class="min-w-0">
					<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Chats</div>
					<div class="text-lg font-semibold tracking-tight text-zinc-900">{summary.total}</div>
				</div>
			</div>
			<div class="flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2.5">
				<Users class="h-4 w-4 text-zinc-500" />
				<div class="min-w-0">
					<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Members</div>
					<div class="text-lg font-semibold tracking-tight text-zinc-900">
						{summary.members.toLocaleString()}
					</div>
				</div>
			</div>
			<div class="flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2.5">
				<Shield class="h-4 w-4 text-zinc-500" />
				<div class="min-w-0">
					<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Captcha on</div>
					<div class="text-lg font-semibold tracking-tight text-zinc-900">{summary.captchaOn}</div>
				</div>
			</div>
			<div class="flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-2.5">
				<UserPlus class="h-4 w-4 text-zinc-500" />
				<div class="min-w-0">
					<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Welcome on</div>
					<div class="text-lg font-semibold tracking-tight text-zinc-900">{summary.welcomeOn}</div>
				</div>
			</div>
		</div>
	{/if}

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
								<Table.Cell class="font-medium">
									<div class="flex items-center gap-2">
										<ChatAvatar
											chatId={chat.id}
											title={chat.title}
											hasPhoto={chat.has_photo}
											size="sm"
										/>
										<span class="truncate">{chat.title ?? `#${chat.id}`}</span>
									</div>
								</Table.Cell>
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
