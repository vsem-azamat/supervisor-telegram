<script lang="ts">
	import { marked } from 'marked';

	type Props = {
		role: 'user' | 'assistant';
		text: string;
		streaming?: boolean;
	};
	let { role, text, streaming = false }: Props = $props();

	marked.setOptions({ gfm: true, breaks: true });

	const rendered = $derived(role === 'assistant' ? (marked.parse(text) as string) : '');
</script>

<div class="flex {role === 'user' ? 'justify-end' : 'justify-start'}">
	<div
		class="max-w-[85%] rounded-lg px-3 py-2 text-sm {role === 'user'
			? 'bg-zinc-900 whitespace-pre-wrap text-zinc-50'
			: 'agent-md bg-zinc-100 text-zinc-900'}"
	>
		{#if role === 'assistant'}
			<!-- Admin-only single-tenant: trust LLM output, skip DOMPurify -->
			<!-- eslint-disable-next-line svelte/no-at-html-tags -->
			{@html rendered}
			{#if streaming}<span class="ml-0.5 inline-block animate-pulse">▍</span>{/if}
		{:else}
			{text}{#if streaming}<span class="ml-0.5 inline-block animate-pulse">▍</span>{/if}
		{/if}
	</div>
</div>

<style>
	/* Tighten Markdown spacing inside the assistant bubble — defaults from
	   the browser ship with too much vertical padding for chat usage. */
	:global(.agent-md p) {
		margin: 0 0 0.5em 0;
	}
	:global(.agent-md p:last-child) {
		margin-bottom: 0;
	}
	:global(.agent-md ul, .agent-md ol) {
		margin: 0 0 0.5em 0;
		padding-left: 1.25em;
	}
	:global(.agent-md li) {
		margin-bottom: 0.15em;
	}
	:global(.agent-md code) {
		background-color: rgb(228 228 231 / 0.7);
		padding: 0.1em 0.35em;
		border-radius: 0.25rem;
		font-size: 0.875em;
	}
	:global(.agent-md pre) {
		background-color: rgb(228 228 231 / 0.7);
		padding: 0.5em 0.75em;
		border-radius: 0.375rem;
		overflow-x: auto;
		margin: 0.25em 0 0.5em 0;
	}
	:global(.agent-md pre code) {
		background: none;
		padding: 0;
	}
	:global(.agent-md a) {
		color: rgb(37 99 235);
		text-decoration: underline;
	}
	:global(.agent-md strong) {
		font-weight: 600;
	}
</style>
