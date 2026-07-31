<script lang="ts">
	import { onMount } from 'svelte';
	import { apiFetch } from '$lib/api/client';

	type TelegramWebApp = {
		initData: string;
		ready: () => void;
		expand?: () => void;
		close?: () => void;
	};

	let phase = $state<'loading' | 'ready' | 'working' | 'passed' | 'failed'>('loading');
	let message = $state('');
	let webApp: TelegramWebApp | null = null;
	let queryId = '';

	onMount(() => {
		// Injected by Telegram, not bundled — outside a Telegram client there is
		// no initData to sign with and nothing here can work.
		webApp = (window as unknown as { Telegram?: { WebApp?: TelegramWebApp } }).Telegram?.WebApp ?? null;
		queryId = new URLSearchParams(window.location.search).get('q') ?? '';

		if (!webApp?.initData || !queryId) {
			phase = 'failed';
			message = 'Откройте эту страницу по ссылке из заявки на вступление.';
			return;
		}

		webApp.ready();
		webApp.expand?.();
		phase = 'ready';
	});

	async function confirm() {
		if (!webApp) return;
		phase = 'working';

		const { error } = await apiFetch<{ status: string }>('/api/public/join-check', {
			method: 'POST',
			body: JSON.stringify({ init_data: webApp.initData, query_id: queryId })
		});

		if (error) {
			phase = 'failed';
			// The server refuses without saying which check failed; saying more
			// here would only be a guess.
			message = 'Проверка не пройдена. Попробуйте подать заявку заново.';
			return;
		}

		phase = 'passed';
		message = 'Готово — заявка одобрена.';
		setTimeout(() => webApp?.close?.(), 1500);
	}
</script>

<svelte:head>
	<title>Проверка при вступлении</title>
</svelte:head>

<main>
	<h1>Подтвердите, что вы не бот</h1>

	{#if phase === 'loading'}
		<p class="muted">Загрузка…</p>
	{:else if phase === 'ready' || phase === 'working'}
		<p class="muted">Нажмите кнопку, чтобы вступить в чат.</p>
		<button onclick={confirm} disabled={phase === 'working'}>
			{phase === 'working' ? 'Проверяем…' : 'Я не бот'}
		</button>
	{:else}
		<p class:ok={phase === 'passed'} class:bad={phase === 'failed'}>{message}</p>
	{/if}
</main>

<style>
	main {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		align-items: center;
		justify-content: center;
		min-height: 100dvh;
		padding: 1.5rem;
		text-align: center;
	}

	h1 {
		font-size: 1.25rem;
		font-weight: 600;
		margin: 0;
	}

	.muted {
		color: var(--color-muted-foreground, #6b7280);
		margin: 0;
	}

	button {
		font: inherit;
		padding: 0.75rem 1.75rem;
		border: none;
		border-radius: 0.5rem;
		background: var(--tg-theme-button-color, #2481cc);
		color: var(--tg-theme-button-text-color, #fff);
		cursor: pointer;
	}

	button:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.ok {
		color: #16a34a;
	}

	.bad {
		color: #dc2626;
	}
</style>
