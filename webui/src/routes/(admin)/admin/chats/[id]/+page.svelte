<script lang="ts">
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import ChatAvatar from '$lib/components/chat/ChatAvatar.svelte';
	import HeatmapGrid from '$lib/components/chat/HeatmapGrid.svelte';
	import Sparkline from '$lib/components/charts/Sparkline.svelte';
	import SpamPingsList from '$lib/components/spam/SpamPingsList.svelte';
	import * as Card from '$lib/components/ui/card/index.js';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import { apiFetch } from '$lib/api/client';
	import { num, plural, relativeTime } from '$lib/format';
	import { ExternalLink, RefreshCw } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import type { components } from '$lib/api/types';

	type ChatDetail = components['schemas']['ChatDetail'];
	type ChatRead = components['schemas']['ChatRead'];
	type ChatStatus = ChatRead['resource_status'];
	type UserBlockResponse = components['schemas']['UserBlockResponse'];

	const chatId = page.params.id;
	const detail = useLivePoll<ChatDetail>(`/api/chats/${chatId}`, 60_000);

	let busyUserId = $state<number | null>(null);
	let editing = $state(false);
	let saving = $state(false);
	let savingStatus = $state(false);
	let refreshing = $state(false);

	async function refreshFromTelegram(): Promise<void> {
		refreshing = true;
		const res = await apiFetch<ChatRead>(`/api/chats/${chatId}/refresh`, { method: 'POST' });
		refreshing = false;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success(`Обновлено — название: ${res.data.title ?? '—'}`);
			await detail.refresh();
		}
	}

	let edit = $state({
		title: '',
		welcome_message: '',
		is_welcome_enabled: false,
		is_captcha_enabled: false,
		is_service_cleanup_enabled: true,
		time_delete: 60
	});

	function snapshotEdit(d: ChatDetail): void {
		edit = {
			title: d.title ?? '',
			welcome_message: d.welcome_message ?? '',
			is_welcome_enabled: d.is_welcome_enabled,
			is_captcha_enabled: d.is_captcha_enabled,
			is_service_cleanup_enabled: d.is_service_cleanup_enabled,
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
				is_service_cleanup_enabled: edit.is_service_cleanup_enabled,
				time_delete: edit.time_delete
			})
		});
		saving = false;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success('Настройки сохранены');
			editing = false;
			await detail.refresh();
		}
	}

	function statusLabel(status: ChatStatus): string {
		if (status === 'approved') return 'Одобрен';
		if (status === 'disabled') return 'Отключён';
		return 'На проверке';
	}

	async function setResourceStatus(status: ChatStatus): Promise<void> {
		if (!detail.data || detail.data.resource_status === status) return;
		savingStatus = true;
		const res = await apiFetch<ChatRead>(`/api/chats/${chatId}`, {
			method: 'PATCH',
			body: JSON.stringify({ resource_status: status })
		});
		savingStatus = false;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success(`Статус: ${statusLabel(status).toLowerCase()}`);
			await detail.refresh();
		}
	}

	// Publishing is kept apart from the moderation form on purpose: everything in
	// that form is read back by the admin who set it, and this one field is read
	// by everybody who opens the front page. Its own card, its own save.
	let editingLink = $state(false);
	let savingLink = $state(false);
	let linkDraft = $state('');

	// Same guard as the moderation form — the page polls every minute and would
	// otherwise wipe a half-typed link out from under the person typing it.
	$effect(() => {
		if (detail.data && !editingLink) linkDraft = detail.data.public_link ?? '';
	});

	async function savePublicLink(): Promise<void> {
		savingLink = true;
		const res = await apiFetch<ChatRead>(`/api/chats/${chatId}`, {
			method: 'PATCH',
			body: JSON.stringify({ public_link: linkDraft.trim() || null })
		});
		savingLink = false;
		if (res.error) {
			toast.error(res.error.message);
			return;
		}
		toast.success(res.data.public_link ? 'Чат опубликован' : 'Чат снят с публичного сайта');
		editingLink = false;
		await detail.refresh();
	}

	function senderLabel(s: components['schemas']['ChatSender']): string {
		if (s.username) return `@${s.username}`;
		const name = [s.first_name, s.last_name].filter(Boolean).join(' ').trim();
		return name || `#${s.user_id}`;
	}

	async function blockUser(userId: number, revoke: boolean = false): Promise<void> {
		const question = revoke
			? `Заблокировать #${userId} во всех чатах и удалить все его сообщения?`
			: `Заблокировать #${userId} во всех чатах?`;
		if (!confirm(question)) return;
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
	<header class="flex items-center justify-between gap-3">
		<div class="flex min-w-0 items-center gap-3">
			{#if detail.data}
				<ChatAvatar
					chatId={detail.data.id}
					title={detail.data.title}
					hasPhoto={detail.data.has_photo}
					size="lg"
				/>
			{/if}
			<div class="min-w-0">
				<h2 class="truncate text-lg font-semibold tracking-tight">
					{detail.data?.title ?? `Чат #${chatId}`}
				</h2>
				<div class="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-zinc-500">
					{#if detail.lastUpdatedAt}
						<span>Страница обновлена {detail.lastUpdatedAt.toLocaleTimeString('ru-RU')}</span>
					{/if}
					{#if detail.data}
						<span>· Из Telegram {relativeTime(detail.data.last_synced_at, 'ни разу')}</span>
						<span>· {statusLabel(detail.data.resource_status)}</span>
					{/if}
				</div>
			</div>
		</div>
		<Button
			type="button"
			variant="outline"
			size="sm"
			disabled={refreshing}
			onclick={refreshFromTelegram}
			class="shrink-0 gap-1.5"
		>
			<RefreshCw class="h-3.5 w-3.5 {refreshing ? 'animate-spin' : ''}" />
			{refreshing ? 'Обновляем…' : 'Обновить из Telegram'}
		</Button>
	</header>

	{#if detail.loading}
		<p class="text-sm text-zinc-500">Загружаем…</p>
	{:else if detail.error}
		<p class="text-sm text-red-600">Ошибка: {detail.error}</p>
	{:else if detail.data}
		<Card.Root>
			<Card.Header class="flex flex-row items-center justify-between">
				<Card.Title class="text-sm">Чат и модерация</Card.Title>
				<Button
					variant="outline"
					size="sm"
					onclick={() => (editing = !editing)}
					disabled={saving}
				>
					{editing ? 'Отмена' : 'Изменить'}
				</Button>
			</Card.Header>
			<Card.Content class="space-y-3 text-sm">
				{#if editing}
					<label class="block space-y-1">
						<span class="text-xs text-zinc-600">Название</span>
						<Input bind:value={edit.title} />
					</label>
					<div class="grid grid-cols-2 gap-2">
						<label class="flex items-center gap-2 text-xs">
							<input type="checkbox" bind:checked={edit.is_welcome_enabled} />
							<span>Приветствовать новичков</span>
						</label>
						<label class="flex items-center gap-2 text-xs">
							<input type="checkbox" bind:checked={edit.is_captcha_enabled} />
							<span>Капча при входе</span>
						</label>
						<label class="flex items-center gap-2 text-xs">
							<input type="checkbox" bind:checked={edit.is_service_cleanup_enabled} />
							<span>Прятать «вошёл» и «вышел»</span>
						</label>
					</div>
					<label class="block space-y-1">
						<span class="text-xs text-zinc-600">Текст приветствия</span>
						<Input bind:value={edit.welcome_message} placeholder="Привет! Добро пожаловать." />
					</label>
					<label class="block space-y-1">
						<span class="text-xs text-zinc-600">Удалять сообщения бота через, секунд</span>
						<Input type="number" bind:value={edit.time_delete} min="1" />
					</label>
					<div class="flex items-center justify-end gap-2 pt-1">
						<Button variant="ghost" size="sm" onclick={() => (editing = false)} disabled={saving}>
							Отмена
						</Button>
						<Button size="sm" onclick={saveEdit} disabled={saving}>
							{saving ? 'Сохраняем…' : 'Сохранить'}
						</Button>
					</div>
				{:else}
					<div class="grid grid-cols-2 gap-2">
						<div>Участников: <strong>{num(detail.data.member_count)}</strong></div>
						<div>Темы: {detail.data.is_forum ? 'включены' : 'выключены'}</div>
						<div>Статус: {statusLabel(detail.data.resource_status)}</div>
						<div>Капча: {detail.data.is_captcha_enabled ? 'вкл' : 'выкл'}</div>
						<div>Приветствие: {detail.data.is_welcome_enabled ? 'вкл' : 'выкл'}</div>
						<div>
							«Вошёл / вышел»: {detail.data.is_service_cleanup_enabled ? 'скрыты' : 'видны'}
						</div>
						<div>Сообщения бота живут: {detail.data.time_delete} с</div>
					</div>
					<div class="flex flex-wrap items-center gap-2 border-t border-zinc-100 pt-3">
						<Button
							size="sm"
							disabled={savingStatus || detail.data.resource_status === 'approved'}
							onclick={() => setResourceStatus('approved')}
						>
							Одобрить
						</Button>
						<Button
							variant="outline"
							size="sm"
							disabled={savingStatus || detail.data.resource_status === 'disabled'}
							onclick={() => setResourceStatus('disabled')}
						>
							Отключить
						</Button>
					</div>
					{#if detail.data.welcome_message}
						<div class="rounded-md border border-zinc-100 bg-zinc-50 p-2 text-xs text-zinc-600">
							<span class="text-zinc-400">Приветствие:</span>
							{detail.data.welcome_message}
						</div>
					{/if}
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header class="flex flex-row items-center justify-between">
				<Card.Title class="text-sm">Публичный каталог</Card.Title>
				{#if !editingLink}
					<Button variant="outline" size="sm" onclick={() => (editingLink = true)}>
						{detail.data.public_link ? 'Изменить ссылку' : 'Добавить ссылку'}
					</Button>
				{/if}
			</Card.Header>
			<Card.Content class="space-y-3 text-sm">
				{#if editingLink}
					<label class="block space-y-1">
						<span class="text-xs text-zinc-600">Ссылка на чат</span>
						<Input bind:value={linkDraft} placeholder="https://t.me/cvut_fit" />
					</label>
					<p class="text-xs text-zinc-500">
						Ссылка Telegram: юзернейм или приглашение, если юзернейма нет. Пустое поле снимает
						чат с публичного сайта.
					</p>
					<div class="flex items-center justify-end gap-2">
						<Button
							variant="ghost"
							size="sm"
							disabled={savingLink}
							onclick={() => {
								editingLink = false;
								linkDraft = detail.data?.public_link ?? '';
							}}
						>
							Отмена
						</Button>
						<Button size="sm" onclick={savePublicLink} disabled={savingLink}>
							{savingLink ? 'Сохраняем…' : 'Сохранить'}
						</Button>
					</div>
				{:else if detail.data.public_link}
					<div class="flex items-center gap-2">
						<a
							href={detail.data.public_link}
							target="_blank"
							rel="noopener noreferrer"
							class="inline-flex items-center gap-1.5 font-mono text-xs text-zinc-800 hover:underline"
						>
							{detail.data.public_link}
							<ExternalLink class="h-3 w-3 text-zinc-400" />
						</a>
					</div>
					{#if detail.data.resource_status === 'approved'}
						<p class="text-xs text-zinc-500">Чат виден на главной странице всем.</p>
					{:else}
						<!-- The link alone does not publish: the catalogue asks for an
						     approved resource too. Said here rather than left to be
						     worked out by opening the public page and not finding it. -->
						<p class="text-xs text-amber-700">
							На сайте его нет — чат
							{statusLabel(detail.data.resource_status).toLowerCase()}. Одобрите выше, и он
							появится.
						</p>
					{/if}
				{:else}
					<p class="text-xs text-zinc-500">
						Чата нет на публичном сайте. Добавьте ссылку — и студенты найдут его сами.
					</p>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Активность по часам (7 дней, UTC)</Card.Title></Card.Header>
			<Card.Content>
				<HeatmapGrid cells={detail.data.heatmap} />
				{#if detail.data.heatmap.length === 0}
					<p class="mt-2 text-xs text-zinc-500">Сообщений в этом чате пока не записано.</p>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Участники со временем</Card.Title></Card.Header>
			<Card.Content>
				{#if detail.data.member_snapshots.length === 0}
					<p class="text-xs text-zinc-500">
						Снимков пока нет. Первый появится в течение часа после запуска бота.
					</p>
				{:else}
					<Sparkline values={detail.data.member_snapshots.map((p) => p.member_count)} />
					<p class="text-xs text-zinc-500">
						{detail.data.member_snapshots.length}
						{plural(detail.data.member_snapshots.length, 'снимок', 'снимка', 'снимков')}
					</p>
				{/if}
			</Card.Content>
		</Card.Root>

		{#if detail.data.parent_chat_id !== null || detail.data.children.length > 0}
			<Card.Root>
				<Card.Header><Card.Title class="text-sm">Связи</Card.Title></Card.Header>
				<Card.Content class="space-y-2 text-sm">
					{#if detail.data.parent_chat_id !== null}
						<div class="flex items-baseline gap-2">
							<span class="text-zinc-500">Родитель:</span>
							<a href="/admin/chats/{detail.data.parent_chat_id}" class="text-zinc-800 hover:underline">
								#{detail.data.parent_chat_id}
							</a>
							{#if detail.data.relation_notes}
								<span class="text-xs text-zinc-400">· {detail.data.relation_notes}</span>
							{/if}
						</div>
					{/if}
					{#if detail.data.children.length > 0}
						<div class="space-y-1">
							<span class="text-zinc-500">
								Вложенные ({detail.data.children.length}):
							</span>
							<ul class="ml-4 list-disc space-y-0.5">
								{#each detail.data.children as c (c.id)}
									<li>
										<a href="/admin/chats/{c.id}" class="text-zinc-800 hover:underline">
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
					Реклама
					{#if detail.data.spam_pings.length > 0}
						<span class="ml-1 text-xs font-normal text-zinc-500">
							({detail.data.spam_pings.length} за последнее время)
						</span>
					{/if}
				</Card.Title>
			</Card.Header>
			<Card.Content>
				<SpamPingsList items={detail.data.spam_pings} empty="Детектор рекламы здесь не срабатывал." />
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title class="text-sm">
					Кто писал за 7 дней
					{#if detail.data.recent_senders.length > 0}
						<span class="ml-1 text-xs font-normal text-zinc-500">
							({detail.data.recent_senders.length})
						</span>
					{/if}
				</Card.Title>
			</Card.Header>
			<Card.Content>
				{#if detail.data.recent_senders.length === 0}
					<p class="text-xs text-zinc-500">За последние 7 дней сообщений не записано.</p>
				{:else}
					<ul class="divide-y divide-zinc-100 text-sm">
						{#each detail.data.recent_senders as s (s.user_id)}
							<li class="flex items-center justify-between gap-2 py-1.5">
								<div class="flex min-w-0 items-baseline gap-2">
									<span class="truncate font-medium text-zinc-800">{senderLabel(s)}</span>
									<span class="shrink-0 font-mono text-xs text-zinc-400">#{s.user_id}</span>
									<span class="shrink-0 text-xs text-zinc-500">
										{s.message_count}
										{plural(s.message_count, 'сообщение', 'сообщения', 'сообщений')}
									</span>
									{#if s.blocked}
										<Badge variant="destructive" class="shrink-0 text-[10px]">заблокирован</Badge>
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
											{busyUserId === s.user_id ? '…' : 'Разблокировать'}
										</Button>
									{:else}
										<Button
											variant="outline"
											size="sm"
											onclick={() => blockUser(s.user_id, false)}
											disabled={busyUserId === s.user_id}
										>
											{busyUserId === s.user_id ? '…' : 'Заблокировать'}
										</Button>
										<Button
											variant="ghost"
											size="sm"
											class="text-red-600 hover:bg-red-50 hover:text-red-700"
											onclick={() => blockUser(s.user_id, true)}
											disabled={busyUserId === s.user_id}
											title="Заблокировать и стереть все сообщения этого человека из всех известных чатов"
										>
											+ стереть
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
