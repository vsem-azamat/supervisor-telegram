<script lang="ts">
	// The first screen answers one question: is anything wrong right now.
	// Everything else on it is context for that answer.
	import ChatTreeNode from '$lib/components/chat/ChatTreeNode.svelte';
	import { enrichTree } from '$lib/components/chat/tree';
	import BarChartH from '$lib/components/charts/BarChartH.svelte';
	import DivergingBars from '$lib/components/charts/DivergingBars.svelte';
	import ActionTile from '$lib/components/home/ActionTile.svelte';
	import Tile from '$lib/components/home/Tile.svelte';
	import SpamPingsList from '$lib/components/spam/SpamPingsList.svelte';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import { num, plural } from '$lib/format';
	import { MessageSquare, Network, RefreshCw, ShieldAlert } from '@lucide/svelte';
	import type { components } from '$lib/api/types';

	type HomeStats = components['schemas']['HomeStats'];
	type Tree = components['schemas']['ChatNode'][];

	const stats = useLivePoll<HomeStats>('/api/stats/home');
	const tree = useLivePoll<Tree>('/api/chats/graph', 120_000);

	const enrichedTree = $derived(tree.data ? enrichTree(tree.data) : []);

	const spamCount24h = $derived(stats.data?.spam_pings.count_24h ?? 0);
	const spamCount7d = $derived(stats.data?.spam_pings.count_7d ?? 0);
	const trackedChats = $derived(stats.data?.members_delta.length ?? 0);
	const messages7d = $derived(
		(stats.data?.chat_heatmap ?? []).reduce((acc, c) => acc + c.total_messages, 0)
	);
</script>

<div class="space-y-6 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Сводка</h2>
			<p class="mt-0.5 text-xs text-zinc-500">Что происходит в чатах прямо сейчас.</p>
		</div>
		<div class="flex items-center gap-3 text-xs text-zinc-500">
			{#if stats.error}
				<span class="text-red-600">Ошибка: {stats.error}</span>
			{:else if stats.lastUpdatedAt}
				<span>Обновлено {stats.lastUpdatedAt.toLocaleTimeString('ru-RU')}</span>
			{/if}
			<button
				type="button"
				class="flex items-center gap-1 rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs font-medium hover:bg-zinc-100"
				onclick={() => stats.refresh()}
			>
				<RefreshCw class="h-3 w-3" />
				<span>Обновить</span>
			</button>
		</div>
	</header>

	<section class="space-y-2">
		<div class="text-[10px] font-semibold tracking-wider text-zinc-400 uppercase">
			Требует внимания
		</div>
		<div class="grid grid-cols-1 gap-3 md:grid-cols-3">
			<ActionTile
				title="Реклама за сутки"
				value={spamCount24h}
				caption="Срабатываний детектора по всем чатам"
				icon={ShieldAlert}
				tone={spamCount24h > 0 ? 'warning' : 'default'}
				href="/admin/chats"
			/>
			<ActionTile
				title="Реклама за неделю"
				value={spamCount7d}
				caption="Скользящий недельный итог"
				icon={ShieldAlert}
				href="/admin/chats"
			/>
			<ActionTile
				title="Сообщений за неделю"
				value={num(messages7d)}
				caption={`${trackedChats} ${plural(trackedChats, 'чат', 'чата', 'чатов')} со снимками участников`}
				icon={MessageSquare}
				href="/admin/chats"
			/>
		</div>
	</section>

	<section class="space-y-2">
		<div class="text-[10px] font-semibold tracking-wider text-zinc-400 uppercase">Чаты</div>
		<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
			<Tile title="Сообщений за 7 дней">
				<BarChartH
					items={(stats.data?.chat_heatmap ?? []).map((c) => ({
						label: c.title ?? `#${c.chat_id}`,
						value: c.total_messages,
						href: `/admin/chats/${c.chat_id}`
					}))}
					empty={stats.loading ? 'загружаем…' : 'Активности не записано'}
				/>
			</Tile>

			<Tile title="Участники, Δ за сутки">
				<DivergingBars
					items={(stats.data?.members_delta ?? []).map((m) => {
						const d = m.delta_24h;
						const secondary =
							d === null || d === undefined
								? `${num(m.current)} · нет базы для сравнения`
								: `${num(m.current)} · ${d > 0 ? '+' : ''}${d}`;
						return {
							label: m.title ?? `#${m.chat_id}`,
							value: d ?? null,
							secondary,
							href: `/admin/chats/${m.chat_id}`
						};
					})}
					empty={stats.loading ? 'загружаем…' : 'Снимков ещё нет'}
				/>
			</Tile>
		</div>
	</section>

	<section class="space-y-2">
		<div class="text-[10px] font-semibold tracking-wider text-zinc-400 uppercase">
			Последние события
		</div>
		<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
			<Tile title="Свежие срабатывания на рекламу">
				<SpamPingsList
					items={(stats.data?.spam_pings.recent ?? []).slice(0, 4)}
					empty={stats.loading ? 'загружаем…' : 'Ничего не срабатывало.'}
					showChat
				/>
			</Tile>

			<Tile title="Дерево чатов">
				{#snippet action()}
					<Network class="h-3.5 w-3.5 text-zinc-400" />
				{/snippet}
				{#if tree.loading}
					<p class="text-xs text-zinc-500">загружаем…</p>
				{:else if enrichedTree.length === 0}
					<p class="text-xs text-zinc-500">Чатов пока нет.</p>
				{:else}
					<ul class="space-y-1">
						{#each enrichedTree.slice(0, 3) as root (root.id)}
							<ChatTreeNode node={root} defaultExpandedDepth={1} />
						{/each}
					</ul>
					<a
						href="/admin/hierarchy"
						class="mt-2 inline-block text-xs text-zinc-500 hover:underline"
					>
						Всё дерево →
					</a>
				{/if}
			</Tile>
		</div>
	</section>
</div>
