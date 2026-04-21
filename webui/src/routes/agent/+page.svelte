<script lang="ts">
	import MessageBubble from '$lib/components/agent/MessageBubble.svelte';
	import ToolTraceRow from '$lib/components/agent/ToolTraceRow.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { apiFetch } from '$lib/api/client';
	import { streamAgentTurn, type AgentStreamEvent } from '$lib/api/agent-stream';
	import type { components } from '$lib/api/types';
	import { onMount, tick } from 'svelte';

	type AgentMessage = components['schemas']['AgentMessage'];
	type AgentHistory = components['schemas']['AgentHistory'];

	type ChatItem =
		| { kind: 'user' | 'assistant'; text: string; streaming?: boolean }
		| {
				kind: 'tool';
				label: string;
				toolName: string;
				state: 'pending' | 'done';
				preview?: string;
				toolCallId: string;
		  };

	let items = $state<ChatItem[]>([]);
	let input = $state('');
	let busy = $state(false);
	let error = $state<string | null>(null);
	let scroller: HTMLDivElement | null = null;
	let abortCtrl: AbortController | null = null;

	function adoptHistory(history: AgentMessage[]): void {
		items = history.map((m): ChatItem => {
			if (m.role === 'tool') {
				return {
					kind: 'tool',
					label: m.tool_label ?? m.tool_name ?? 'tool',
					toolName: m.tool_name ?? '',
					state: 'done',
					preview: m.result_preview ?? '',
					toolCallId: ''
				};
			}
			return { kind: m.role as 'user' | 'assistant', text: m.text ?? '' };
		});
	}

	onMount(async () => {
		const res = await apiFetch<AgentHistory>('/api/agent/history');
		if (res.data) adoptHistory(res.data.messages);
	});

	async function scrollToBottom(): Promise<void> {
		await tick();
		scroller?.scrollTo({ top: scroller.scrollHeight, behavior: 'smooth' });
	}

	function handleEvent(ev: AgentStreamEvent, assistantIdx: number): number {
		if (ev.type === 'tool_call') {
			items.push({
				kind: 'tool',
				label: ev.label,
				toolName: ev.tool_name,
				state: 'pending',
				toolCallId: ev.tool_call_id
			});
			return -1; // re-create assistant bubble after tool sequence
		}
		if (ev.type === 'tool_result') {
			for (let i = items.length - 1; i >= 0; i--) {
				const it = items[i];
				if (it.kind === 'tool' && it.toolCallId === ev.tool_call_id) {
					it.state = 'done';
					it.preview = ev.result_preview;
					break;
				}
			}
			return -1;
		}
		if (ev.type === 'token') {
			if (assistantIdx === -1) {
				items.push({ kind: 'assistant', text: ev.text, streaming: true });
				return items.length - 1;
			}
			const it = items[assistantIdx];
			if (it.kind === 'assistant') it.text = ev.text;
			return assistantIdx;
		}
		if (ev.type === 'done') {
			if (assistantIdx === -1 || items[assistantIdx]?.kind !== 'assistant') {
				items.push({ kind: 'assistant', text: ev.final_text });
			} else {
				const it = items[assistantIdx];
				if (it.kind === 'assistant') {
					it.text = ev.final_text;
					it.streaming = false;
				}
			}
			return assistantIdx;
		}
		if (ev.type === 'error') {
			error = ev.message;
		}
		return assistantIdx;
	}

	async function send(): Promise<void> {
		const text = input.trim();
		if (!text || busy) return;
		input = '';
		error = null;
		items.push({ kind: 'user', text });
		busy = true;
		await scrollToBottom();

		abortCtrl = new AbortController();
		let assistantIdx = -1;
		try {
			for await (const ev of streamAgentTurn(text, abortCtrl.signal)) {
				assistantIdx = handleEvent(ev, assistantIdx);
				await scrollToBottom();
			}
		} catch (err) {
			if ((err as Error).name !== 'AbortError') {
				error = (err as Error).message;
			}
		} finally {
			busy = false;
			abortCtrl = null;
			// Strip any leftover streaming flag
			for (const it of items) {
				if (it.kind === 'assistant') it.streaming = false;
			}
		}
	}

	function cancel(): void {
		abortCtrl?.abort();
	}

	async function clearConversation(): Promise<void> {
		await apiFetch('/api/agent/clear', { method: 'POST' });
		items = [];
		error = null;
	}

	function handleKey(e: KeyboardEvent): void {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			void send();
		}
	}
</script>

<div class="mx-auto flex h-[calc(100vh-4rem)] max-w-3xl flex-col px-6 py-4">
	<header class="mb-3 flex items-baseline justify-between">
		<h2 class="text-lg font-semibold tracking-tight">Agent chat</h2>
		<div class="flex items-center gap-2 text-xs text-zinc-500">
			<span>{items.length} messages</span>
			<button
				type="button"
				class="rounded-md border border-zinc-200 px-2 py-1 text-xs font-medium hover:bg-zinc-100"
				onclick={clearConversation}
				disabled={busy}
			>
				New conversation
			</button>
		</div>
	</header>

	<div
		bind:this={scroller}
		class="flex-1 space-y-2 overflow-y-auto rounded-md border border-zinc-200 bg-white p-3"
	>
		{#if items.length === 0}
			<p class="text-center text-sm text-zinc-400">
				Start chatting with the assistant. It can manage channels, moderate chats, look up costs, and more.
			</p>
		{/if}
		{#each items as item, i (i)}
			{#if item.kind === 'tool'}
				<ToolTraceRow
					label={item.label}
					toolName={item.toolName}
					state={item.state}
					preview={item.preview}
				/>
			{:else}
				<MessageBubble role={item.kind} text={item.text} streaming={item.streaming} />
			{/if}
		{/each}
	</div>

	{#if error}
		<p class="mt-2 text-xs text-red-600">Error: {error}</p>
	{/if}

	<div class="mt-3 flex items-end gap-2">
		<textarea
			class="flex-1 resize-none rounded-md border border-zinc-200 px-3 py-2 text-sm focus:border-zinc-400 focus:outline-none disabled:opacity-60"
			rows="2"
			placeholder="Message the assistant…  (Enter to send, Shift+Enter for newline)"
			bind:value={input}
			onkeydown={handleKey}
			disabled={busy}
		></textarea>
		{#if busy}
			<Button variant="outline" onclick={cancel}>Cancel</Button>
		{:else}
			<Button onclick={send} disabled={!input.trim()}>Send</Button>
		{/if}
	</div>
</div>
