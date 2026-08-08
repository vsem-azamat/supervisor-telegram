<script lang="ts">
	// Everything nested here needs a super-administrator session. The check is a
	// layout rather than a per-page guard so that adding a screen cannot forget
	// it: a new file under `(admin)/` is protected by where it sits.
	//
	// This is a second lock, not the lock. The API refuses without a valid cookie
	// whatever the browser believes — see `require_super_admin` in
	// `app/webapi/deps.py`. What the guard buys is not safety but honesty: an
	// anonymous visitor gets an explanation instead of a console full of failed
	// requests.
	//
	// There is no sign-in page to send them to any more. Opening the Mini App is
	// the sign-in: Telegram signs `initData` before this code runs, so the first
	// thing an unauthenticated console does is offer that signature. Outside
	// Telegram there is nothing to offer, and the panel below explains that case
	// rather than retrying it.
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import Header from '$lib/components/app-shell/Header.svelte';
	import Sidebar from '$lib/components/app-shell/Sidebar.svelte';
	// Toasts are a console thing — only the chat detail page raises them. Kept
	// here rather than at the root so a student on the catalog does not download
	// a toast library to be told nothing.
	import { Toaster } from '$lib/components/ui/sonner/index.js';
	import { auth } from '$lib/stores/auth.svelte';

	let { children } = $props();

	// Separate from `auth.initialized`, which only says the session was asked
	// about. This says the sign-in attempt that follows is over too, so the
	// panel cannot flash in the moment between the two.
	let settled = $state(false);

	onMount(async () => {
		await auth.refresh();
		if (!auth.me) await auth.signInWithTelegram();
		settled = true;
	});

	async function doLogout(): Promise<void> {
		await auth.logout();
		await goto('/');
	}

	// One panel per reason, because the reasons need different things done
	// about them. The old screen said "your account is not on the list" for all
	// four, which is the sentence a person forwards to the administrator who
	// added them — while the actual fault was on this side of the wire and
	// nobody was looking for it.
	const PANELS = {
		'not-in-telegram': {
			title: 'Консоль открывается из Telegram',
			body: 'Вход — это само открытие приложения: личность подтверждает Telegram, паролей и ссылок нет. Напишите боту /start и нажмите «Открыть консоль».',
			aside: null
		},
		refused: {
			title: 'Telegram не подтвердил вход',
			body: 'Подпись, с которой открылось приложение, не прошла проверку на сервере. Дело не в правах — попробуйте закрыть приложение и открыть заново из бота.',
			aside: 'Если повторяется — это ошибка на нашей стороне, напишите @work_azamat.'
		},
		'not-an-admin': {
			title: 'Доступ только для главных администраторов',
			body: 'Telegram подтвердил, кто вы. Этого аккаунта нет в списке главных администраторов, поэтому консоль не открывается.',
			aside: 'Если считаете, что должен быть — напишите @work_azamat.'
		},
		unavailable: {
			title: 'Сервер не отвечает',
			body: 'Не удалось связаться с сервером. Попробуйте ещё раз через минуту.',
			aside: null
		}
	} as const;

	const panel = $derived(PANELS[auth.failure ?? 'not-in-telegram']);
</script>

<Toaster richColors />

{#if !settled}
	<div class="flex min-h-screen items-center justify-center text-sm text-zinc-400">Загрузка…</div>
{:else if !auth.me}
	<div class="flex min-h-screen items-center justify-center px-4">
		<div
			class="w-full max-w-sm space-y-3 rounded-xl border border-zinc-200 bg-white p-6 text-center"
		>
			<h1 class="text-lg font-semibold tracking-tight text-zinc-900">{panel.title}</h1>
			<p class="text-sm text-zinc-500">{panel.body}</p>
			{#if panel.aside}
				<p class="text-xs text-zinc-400">{panel.aside}</p>
			{/if}
		</div>
	</div>
{:else}
	<div class="flex h-screen w-screen bg-white text-zinc-900">
		<Sidebar />
		<div class="flex min-w-0 flex-1 flex-col">
			<Header onLogout={doLogout} />
			<main class="flex-1 overflow-auto">
				{@render children()}
			</main>
		</div>
	</div>
{/if}
