<script lang="ts">
	import type { components } from '$lib/api/types';

	type Ping = components['schemas']['SpamPingRead'];
	type Props = { items: Ping[]; empty?: string; showChat?: boolean };
	let { items, empty = 'No pings recorded.', showChat = false }: Props = $props();

	function fmtRelative(iso: string): string {
		const now = Date.now();
		const then = new Date(iso).getTime();
		const diff = Math.max(0, now - then);
		const m = Math.floor(diff / 60_000);
		if (m < 1) return 'just now';
		if (m < 60) return `${m}m ago`;
		const h = Math.floor(m / 60);
		if (h < 24) return `${h}h ago`;
		const d = Math.floor(h / 24);
		return `${d}d ago`;
	}
</script>

{#if items.length === 0}
	<p class="text-xs text-zinc-500">{empty}</p>
{:else}
	<ul class="space-y-2">
		{#each items as ping (ping.id)}
			<li class="space-y-0.5 border-b border-zinc-100 pb-2 last:border-b-0 last:pb-0">
				<div class="flex items-baseline justify-between gap-2 text-xs">
					<span class="flex items-center gap-1.5">
						<span
							class="rounded px-1 py-0.5 text-[10px] font-medium uppercase tracking-wide {ping.kind ===
							'mention'
								? 'bg-amber-100 text-amber-700'
								: 'bg-rose-100 text-rose-700'}"
						>
							{ping.kind}
						</span>
						{#each ping.matches as match (match)}
							<code class="truncate rounded bg-zinc-100 px-1 py-0.5 text-[11px] text-zinc-700">{match}</code>
						{/each}
					</span>
					<span class="shrink-0 text-zinc-400">{fmtRelative(ping.detected_at)}</span>
				</div>
				{#if showChat && ping.chat_title}
					<a href="/chats/{ping.chat_id}" class="block text-xs text-zinc-500 hover:underline">
						{ping.chat_title}
					</a>
				{/if}
				{#if ping.snippet}
					<p class="line-clamp-2 text-xs text-zinc-600">{ping.snippet}</p>
				{/if}
			</li>
		{/each}
	</ul>
{/if}
