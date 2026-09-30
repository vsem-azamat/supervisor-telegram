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
	import { afterNavigate } from '$app/navigation';
	import { onMount } from 'svelte';
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

	// How many of this console's own pages are behind the current one.
	let depth = 0;
	afterNavigate((navigation) => {
		if (navigation.type === 'enter') return;
		depth = navigation.type === 'popstate' ? Math.max(0, depth - 1) : depth + 1;
	});

	onMount(async () => {
		// This console is entered from the Mini App's /console, a different
		// build: without this Telegram's back button would be gone, and
		// Android's would close the app. Back walks this console's own pages
		// first, then leaves for /console with a full load.
		const back = (
			window as unknown as {
				Telegram?: { WebApp?: { BackButton?: { show(): void; onClick(cb: () => void): void } } };
			}
		).Telegram?.WebApp?.BackButton;
		back?.onClick(() => {
			if (depth > 0) history.back();
			else window.location.assign('/console');
		});
		back?.show();

		await auth.refresh();
		if (!auth.me) await auth.signInWithTelegram();
		settled = true;
	});

	// Set by the button, so the panel below says what happened instead of
	// telling somebody who just signed out that they are not on the list.
	let signedOut = $state(false);

	async function doLogout(): Promise<void> {
		// Stays here: `/` is the Mini App now, a build this router cannot reach.
		await auth.logout();
		signedOut = true;
	}
</script>

<Toaster richColors />

{#if !settled}
	<div class="flex min-h-screen items-center justify-center text-sm text-zinc-400">Загрузка…</div>
{:else if !auth.me}
	<div class="flex min-h-screen items-center justify-center px-4">
		<div
			class="w-full max-w-sm space-y-3 rounded-xl border border-zinc-200 bg-white p-6 text-center"
		>
			<h1 class="text-lg font-semibold tracking-tight text-zinc-900">
				Консоль открывается из Telegram
			</h1>
			<p class="text-sm text-zinc-500">
				Вход — это само открытие приложения: личность подтверждает Telegram, паролей и ссылок нет.
				Напишите боту <span class="font-medium text-zinc-700">/start</span> и нажмите «Открыть консоль».
			</p>
			{#if signedOut}
				<p class="text-xs text-zinc-400">Вы вышли. Чтобы войти снова, откройте консоль заново.</p>
			{:else}
				<p class="text-xs text-zinc-400">
					Если вы открыли это из Telegram и всё равно видите сообщение — аккаунт не в списке главных
					администраторов.
				</p>
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
