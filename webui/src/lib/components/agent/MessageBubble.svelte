<script lang="ts">
	type Props = {
		role: 'user' | 'assistant';
		text: string;
		streaming?: boolean;
	};
	let { role, text, streaming = false }: Props = $props();
</script>

<div class="flex {role === 'user' ? 'justify-end' : 'justify-start'}">
	<div
		class="max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap {role === 'user'
			? 'bg-zinc-900 text-zinc-50'
			: 'bg-zinc-100 text-zinc-900'}"
	>
		{text}{#if streaming}<span class="ml-0.5 inline-block animate-pulse">▍</span>{/if}
	</div>
</div>
