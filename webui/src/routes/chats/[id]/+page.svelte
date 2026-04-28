<script lang="ts">
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import HeatmapGrid from '$lib/components/chat/HeatmapGrid.svelte';
	import Sparkline from '$lib/components/charts/Sparkline.svelte';
	import SpamPingsList from '$lib/components/spam/SpamPingsList.svelte';
	import * as Card from '$lib/components/ui/card/index.js';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import { apiFetch } from '$lib/api/client';
	import { toast } from 'svelte-sonner';
	import type { components } from '$lib/api/types';

	type ChatDetail = components['schemas']['ChatDetail'];
	type ChatRead = components['schemas']['ChatRead'];
	type UserBlockResponse = components['schemas']['UserBlockResponse'];

	const chatId = page.params.id;
	const detail = useLivePoll<ChatDetail>(`/api/chats/${chatId}`, 60_000);

	let busyUserId = $state<number | null>(null);
	let editing = $state(false);
	let saving = $state(false);
	let edit = $state({
		title: '',
		welcome_message: '',
		is_welcome_enabled: false,
		is_captcha_enabled: false,
		time_delete: 60
	});

	function snapshotEdit(d: ChatDetail): void {
		edit = {
			title: d.title ?? '',
			welcome_message: d.welcome_message ?? '',
			is_welcome_enabled: d.is_welcome_enabled,
			is_captcha_enabled: d.is_captcha_enabled,
			time_delete: d.time_delete
		};
	}

	$effect(() => {
		if (detail.data && !editing) snapshotEdit(detail.data);
	});

	async function saveEdit(): Promise<void> {
		saving = true;
		const res = await apiFetch<ChatRead>(`/api/chats/${chatId}`, {
			method: 'PATCH',
			body: JSON.stringify({
				title: edit.title || null,
				welcome_message: edit.welcome_message || null,
				is_welcome_enabled: edit.is_welcome_enabled,
				is_captcha_enabled: edit.is_captcha_enabled,
				time_delete: edit.time_delete
			})
		});
		saving = false;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success('Moderation settings saved');
			editing = false;
			await detail.refresh();
		}
	}

	function senderLabel(s: components['schemas']['ChatSender']): string {
		if (s.username) return `@${s.username}`;
		const name = [s.first_name, s.last_name].filter(Boolean).join(' ').trim();
		return name || `#${s.user_id}`;
	}

	async function blockUser(userId: number, revoke: boolean = false): Promise<void> {
		if (!confirm(`Block user #${userId} across all managed chats?${revoke ? ' Messages will be revoked.' : ''}`)) {
			return;
		}
		busyUserId = userId;
		const res = await apiFetch<UserBlockResponse>(`/api/users/${userId}/block`, {
			method: 'POST',
			body: JSON.stringify({ revoke_messages: revoke })
		});
		busyUserId = null;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success(res.data.message);
			await detail.refresh();
		}
	}

	async function unblockUser(userId: number): Promise<void> {
		busyUserId = userId;
		const res = await apiFetch<UserBlockResponse>(`/api/users/${userId}/block`, { method: 'DELETE' });
		busyUserId = null;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success(res.data.message);
			await detail.refresh();
		}
	}
</script>

<div class="mx-auto max-w-5xl space-y-4 px-6 py-6">
	<header>
		<h2 class="text-lg font-semibold tracking-tight">
			{detail.data?.title ?? `Chat #${chatId}`}
		</h2>
		{#if detail.lastUpdatedAt}
			<span class="text-xs text-zinc-500">Updated {detail.lastUpdatedAt.toLocaleTimeString()}</span>
		{/if}
	</header>

	{#if detail.loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if detail.error}
		<p class="text-sm text-red-600">Error: {detail.error}</p>
	{:else if detail.data}
		<Card.Root>
			<Card.Header class="flex flex-row items-center justify-between">
				<Card.Title class="text-sm">Overview & moderation</Card.Title>
				<Button
					variant="outline"
					size="sm"
					onclick={() => (editing = !editing)}
					disabled={saving}
				>
					{editing ? 'Cancel' : 'Edit'}
				</Button>
			</Card.Header>
			<Card.Content class="space-y-3 text-sm">
				{#if editing}
					<label class="block space-y-1">
						<span class="text-xs text-zinc-600">Title</span>
						<Input bind:value={edit.title} />
					</label>
					<div class="grid grid-cols-2 gap-2">
						<label class="flex items-center gap-2 text-xs">
							<input type="checkbox" bind:checked={edit.is_welcome_enabled} />
							<span>Welcome message enabled</span>
						</label>
						<label class="flex items-center gap-2 text-xs">
							<input type="checkbox" bind:checked={edit.is_captcha_enabled} />
							<span>Captcha enabled</span>
						</label>
					</div>
					<label class="block space-y-1">
						<span class="text-xs text-zinc-600">Welcome message text</span>
						<Input bind:value={edit.welcome_message} placeholder="Welcome to the chat!" />
					</label>
					<label class="block space-y-1">
						<span class="text-xs text-zinc-600">Auto-delete bot messages after (seconds)</span>
						<Input type="number" bind:value={edit.time_delete} min="1" />
					</label>
					<div class="flex items-center justify-end gap-2 pt-1">
						<Button variant="ghost" size="sm" onclick={() => (editing = false)} disabled={saving}>
							Cancel
						</Button>
						<Button size="sm" onclick={saveEdit} disabled={saving}>
							{saving ? 'Saving…' : 'Save'}
						</Button>
					</div>
				{:else}
					<div class="grid grid-cols-2 gap-2">
						<div>Members: <strong>{detail.data.member_count ?? '—'}</strong></div>
						<div>Forum: {detail.data.is_forum ? 'yes' : 'no'}</div>
						<div>Captcha: {detail.data.is_captcha_enabled ? 'on' : 'off'}</div>
						<div>Welcome: {detail.data.is_welcome_enabled ? 'on' : 'off'}</div>
						<div>Auto-delete: {detail.data.time_delete}s</div>
					</div>
					{#if detail.data.welcome_message}
						<div class="rounded-md border border-zinc-100 bg-zinc-50 p-2 text-xs text-zinc-600">
							<span class="text-zinc-400">Welcome:</span> {detail.data.welcome_message}
						</div>
					{/if}
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Activity heatmap (7 days, UTC)</Card.Title></Card.Header>
			<Card.Content>
				<HeatmapGrid cells={detail.data.heatmap} />
				{#if detail.data.heatmap.length === 0}
					<p class="mt-2 text-xs text-zinc-500">No messages recorded for this chat yet.</p>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Members over time</Card.Title></Card.Header>
			<Card.Content>
				{#if detail.data.member_snapshots.length === 0}
					<p class="text-xs text-zinc-500">No snapshots yet. First snapshot will appear within an hour of bot startup.</p>
				{:else}
					<Sparkline values={detail.data.member_snapshots.map((p) => p.member_count)} />
					<p class="text-xs text-zinc-500">
						{detail.data.member_snapshots.length} snapshots
					</p>
				{/if}
			</Card.Content>
		</Card.Root>

		{#if detail.data.parent_chat_id !== null || detail.data.children.length > 0}
			<Card.Root>
				<Card.Header><Card.Title class="text-sm">Relationships</Card.Title></Card.Header>
				<Card.Content class="space-y-2 text-sm">
					{#if detail.data.parent_chat_id !== null}
						<div class="flex items-baseline gap-2">
							<span class="text-zinc-500">Parent:</span>
							<a href="/chats/{detail.data.parent_chat_id}" class="text-zinc-800 hover:underline">
								#{detail.data.parent_chat_id}
							</a>
							{#if detail.data.relation_notes}
								<span class="text-xs text-zinc-400">· {detail.data.relation_notes}</span>
							{/if}
						</div>
					{/if}
					{#if detail.data.children.length > 0}
						<div class="space-y-1">
							<span class="text-zinc-500">Children ({detail.data.children.length}):</span>
							<ul class="ml-4 list-disc space-y-0.5">
								{#each detail.data.children as c (c.id)}
									<li>
										<a href="/chats/{c.id}" class="text-zinc-800 hover:underline">
											{c.title ?? `#${c.id}`}
										</a>
										{#if c.relation_notes}
											<span class="text-xs text-zinc-400">· {c.relation_notes}</span>
										{/if}
									</li>
								{/each}
							</ul>
						</div>
					{/if}
				</Card.Content>
			</Card.Root>
		{/if}

		<Card.Root>
			<Card.Header>
				<Card.Title class="text-sm">
					Spam pings
					{#if detail.data.spam_pings.length > 0}
						<span class="ml-1 text-xs font-normal text-zinc-500">
							({detail.data.spam_pings.length} recent)
						</span>
					{/if}
				</Card.Title>
			</Card.Header>
			<Card.Content>
				<SpamPingsList items={detail.data.spam_pings} empty="No ad-detector hits in this chat." />
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title class="text-sm">
					Recent senders (7 days)
					{#if detail.data.recent_senders.length > 0}
						<span class="ml-1 text-xs font-normal text-zinc-500">
							({detail.data.recent_senders.length})
						</span>
					{/if}
				</Card.Title>
			</Card.Header>
			<Card.Content>
				{#if detail.data.recent_senders.length === 0}
					<p class="text-xs text-zinc-500">No messages recorded in the last 7 days.</p>
				{:else}
					<ul class="divide-y divide-zinc-100 text-sm">
						{#each detail.data.recent_senders as s (s.user_id)}
							<li class="flex items-center justify-between gap-2 py-1.5">
								<div class="flex min-w-0 items-baseline gap-2">
									<span class="truncate font-medium text-zinc-800">{senderLabel(s)}</span>
									<span class="shrink-0 font-mono text-xs text-zinc-400">#{s.user_id}</span>
									<span class="shrink-0 text-xs text-zinc-500">{s.message_count} msg</span>
									{#if s.blocked}
										<Badge variant="destructive" class="shrink-0 text-[10px]">blocked</Badge>
									{/if}
								</div>
								<div class="flex shrink-0 items-center gap-1">
									{#if s.blocked}
										<Button
											variant="ghost"
											size="sm"
											onclick={() => unblockUser(s.user_id)}
											disabled={busyUserId === s.user_id}
										>
											{busyUserId === s.user_id ? '…' : 'Unblock'}
										</Button>
									{:else}
										<Button
											variant="outline"
											size="sm"
											onclick={() => blockUser(s.user_id, false)}
											disabled={busyUserId === s.user_id}
										>
											{busyUserId === s.user_id ? '…' : 'Block'}
										</Button>
										<Button
											variant="ghost"
											size="sm"
											class="text-red-600 hover:bg-red-50 hover:text-red-700"
											onclick={() => blockUser(s.user_id, true)}
											disabled={busyUserId === s.user_id}
											title="Block + delete this user's messages from all known chats"
										>
											+ Revoke
										</Button>
									{/if}
								</div>
							</li>
						{/each}
					</ul>
				{/if}
			</Card.Content>
		</Card.Root>
	{/if}
</div>
