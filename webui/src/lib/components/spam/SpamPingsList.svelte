<script lang="ts">
	import { relativeTime } from '$lib/format';
	import type { components } from '$lib/api/types';

	type Ping = components['schemas']['SpamPingRead'];
	type Props = { items: Ping[]; empty?: string; showChat?: boolean };
	let { items, empty = 'Срабатываний не записано.', showChat = false }: Props = $props();

	// What the detector caught, in the words a moderator would use for it.
	const KIND: Record<string, string> = {
		mention: 'упоминание',
		link: 'ссылка'
	};
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
							{KIND[ping.kind] ?? ping.kind}
						</span>
						{#each ping.matches as match (match)}
							<code class="truncate rounded bg-zinc-100 px-1 py-0.5 text-[11px] text-zinc-700">{match}</code>
						{/each}
					</span>
					<span class="shrink-0 text-zinc-400">{relativeTime(ping.detected_at)}</span>
				</div>
				{#if showChat && ping.chat_title}
					<a href="/admin/chats/{ping.chat_id}" class="block text-xs text-zinc-500 hover:underline">
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
