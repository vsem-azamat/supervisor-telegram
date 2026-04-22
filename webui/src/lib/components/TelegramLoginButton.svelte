<script lang="ts">
	import { onMount } from 'svelte';

	type TgUser = Record<string, string | number>;
	type Props = {
		botUsername: string;
		onAuth: (payload: TgUser) => void;
	};
	let { botUsername, onAuth }: Props = $props();

	let container: HTMLDivElement;

	onMount(() => {
		// The widget calls window.onTelegramAuth(user) globally — bridge it.
		(window as unknown as { onTelegramAuth: (u: TgUser) => void }).onTelegramAuth = onAuth;

		const s = document.createElement('script');
		s.async = true;
		s.src = 'https://telegram.org/js/telegram-widget.js?22';
		s.setAttribute('data-telegram-login', botUsername);
		s.setAttribute('data-size', 'large');
		s.setAttribute('data-radius', '8');
		s.setAttribute('data-onauth', 'onTelegramAuth(user)');
		s.setAttribute('data-request-access', 'write');
		container.appendChild(s);
	});
</script>

<div bind:this={container}></div>
