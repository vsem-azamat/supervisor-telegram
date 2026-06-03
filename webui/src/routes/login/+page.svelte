<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { apiFetch } from '$lib/api/client';
	import TelegramLoginButton from '$lib/components/TelegramLoginButton.svelte';
	import { auth } from '$lib/stores/auth.svelte';
	import { onMount } from 'svelte';

	const BOT_USERNAME = 'konnekt_moder_bot';
	let error = $state<string | null>(null);
	let magicBusy = $state(false);

	onMount(() => {
		const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
		const token = hashParams.get('token') ?? page.url.searchParams.get('token');
		if (token) void handleMagicLink(token);
	});

	async function handleAuth(user: Record<string, string | number>): Promise<void> {
		error = null;
		const res = await apiFetch('/api/auth/login', {
			method: 'POST',
			body: JSON.stringify(user)
		});
		if (res.error) {
			error = res.error.message ?? 'Login failed';
			return;
		}
		await auth.refresh();
		await goto('/');
	}

	async function handleMagicLink(token: string): Promise<void> {
		error = null;
		magicBusy = true;
		try {
			const res = await apiFetch('/api/auth/magic-link', {
				method: 'POST',
				body: JSON.stringify({ token })
			});
			if (res.error) {
				error = res.error.message ?? 'Login failed';
				return;
			}
			await auth.refresh();
			await goto('/');
		} finally {
			magicBusy = false;
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center bg-background px-4 text-foreground">
	<div class="w-full max-w-sm space-y-5 rounded-lg border bg-card p-6 shadow-sm">
		<div class="flex items-center gap-2.5">
			<div
				class="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-sm font-semibold text-primary-foreground"
			>
				K
			</div>
			<h1 class="text-lg font-semibold">Konnekt Admin</h1>
		</div>
		<p class="text-sm text-muted-foreground">
			{magicBusy ? 'Signing in…' : 'Sign in with your Telegram account to continue.'}
		</p>
		{#if !magicBusy}
			<TelegramLoginButton botUsername={BOT_USERNAME} onAuth={handleAuth} />
		{/if}
		{#if error}
			<p class="text-xs text-destructive">{error}</p>
		{/if}
	</div>
</div>
