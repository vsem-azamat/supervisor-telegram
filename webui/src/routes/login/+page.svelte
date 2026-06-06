<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { apiFetch } from '$lib/api/client';
	import type { components } from '$lib/api/types';
	import TelegramLoginButton from '$lib/components/TelegramLoginButton.svelte';
	import { auth } from '$lib/stores/auth.svelte';
	import { onMount } from 'svelte';

	type AuthConfig = components['schemas']['AuthConfigResponse'];
	type AuthMode = AuthConfig['auth_mode'];

	let error = $state<string | null>(null);
	let magicBusy = $state(false);
	let authMode = $state<AuthMode | null>(null);
	let botUsername = $state<string | null>(null);
	let botStartUrl = $state<string | null>(null);
	let configLoading = $state(true);

	onMount(() => {
		void initializeLogin();
	});

	async function initializeLogin(): Promise<void> {
		error = null;
		const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
		const token = hashParams.get('token') ?? page.url.searchParams.get('token');
		try {
			const res = await apiFetch<AuthConfig>('/api/auth/config');
			if (res.error) {
				error = res.error.message ?? 'Could not load sign-in options';
				return;
			}
			authMode = res.data.auth_mode;
			botUsername = res.data.bot_username ?? null;
			botStartUrl = res.data.bot_start_url ?? null;
			if (authMode === 'magic_link' && token) {
				await handleMagicLink(token);
			}
		} finally {
			configLoading = false;
		}
	}

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
			{#if configLoading}
				Loading sign-in options.
			{:else if magicBusy}
				Signing in…
			{:else if authMode === 'magic_link'}
				Open the magic link from Telegram to continue.
			{:else}
				Sign in with your Telegram account to continue.
			{/if}
		</p>
		{#if authMode === 'telegram' && !magicBusy}
			{#if botUsername}
				<TelegramLoginButton botUsername={botUsername} onAuth={handleAuth} />
			{:else}
				<p class="text-xs text-destructive">Telegram sign-in bot is not configured.</p>
			{/if}
		{/if}
		{#if authMode === 'magic_link' && !magicBusy && botStartUrl}
			<a
				class="inline-flex h-9 items-center justify-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-xs transition-colors hover:bg-primary/90 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
				href={botStartUrl}
				rel="noreferrer"
				target="_blank"
			>
				Open Telegram bot
			</a>
		{/if}
		{#if error}
			<p class="text-xs text-destructive">{error}</p>
		{/if}
	</div>
</div>
