<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import Sparkline from '$lib/components/charts/Sparkline.svelte';
	import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
	import type { components } from '$lib/api/types';

	type Summary = components['schemas']['SessionCostSummary'];
	type History = components['schemas']['CostHistoryResponse'];

	let days = $state<number>(30);

	const cost = useLivePoll<Summary>('/api/costs/session', 60_000);
	const history = useLivePoll<History>(() => `/api/costs/history?days=${days}`, 120_000);

	function fmt(usd: number): string {
		return usd < 0.01 ? '<$0.01' : `$${usd.toFixed(4)}`;
	}

	function fmtCompact(usd: number): string {
		if (usd === 0) return '$0';
		if (usd < 0.01) return '<$0.01';
		return `$${usd.toFixed(2)}`;
	}

	const sparkValues = $derived(history.data?.series.map((d) => d.cost_usd) ?? []);
	const maxDay = $derived.by(() => {
		const series = history.data?.series ?? [];
		if (series.length === 0) return null;
		return series.reduce((a, b) => (a.cost_usd > b.cost_usd ? a : b));
	});
</script>

<div class="mx-auto max-w-5xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<div>
			<h2 class="text-lg font-semibold tracking-tight">Costs</h2>
			<p class="mt-0.5 text-xs text-zinc-500">Session-level + persistent daily cost history.</p>
		</div>
		{#if cost.lastUpdatedAt}
			<span class="text-xs text-zinc-500">Updated {cost.lastUpdatedAt.toLocaleTimeString()}</span>
		{/if}
	</header>

	<Card.Root>
		<Card.Header class="flex flex-row items-center justify-between space-y-0">
			<Card.Title class="text-sm">
				Daily cost
				<span class="ml-1 text-xs font-normal text-zinc-500">last {days} days</span>
			</Card.Title>
			<select
				bind:value={days}
				class="rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs"
				onchange={() => history.refresh()}
			>
				<option value={7}>7 days</option>
				<option value={14}>14 days</option>
				<option value={30}>30 days</option>
				<option value={90}>90 days</option>
			</select>
		</Card.Header>
		<Card.Content class="space-y-3 text-sm">
			{#if history.loading}
				<p class="text-zinc-500">Loading…</p>
			{:else if history.error}
				<p class="text-red-600">Error: {history.error}</p>
			{:else if history.data}
				{@const total = history.data.total_cost_usd}
				<div class="grid grid-cols-3 gap-4 text-xs">
					<div>
						<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Total</div>
						<div class="text-xl font-semibold text-zinc-900">{fmt(total)}</div>
					</div>
					<div>
						<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Calls</div>
						<div class="text-xl font-semibold text-zinc-900">{history.data.total_calls.toLocaleString()}</div>
					</div>
					<div>
						<div class="text-[10px] font-medium tracking-wider text-zinc-500 uppercase">Avg / day</div>
						<div class="text-xl font-semibold text-zinc-900">{fmt(total / Math.max(1, days))}</div>
					</div>
				</div>
				{#if sparkValues.length > 0 && total > 0}
					<Sparkline values={sparkValues} />
					{#if maxDay && maxDay.cost_usd > 0}
						<p class="text-xs text-zinc-500">
							Peak: <strong>{fmtCompact(maxDay.cost_usd)}</strong> on {maxDay.day} ·
							{maxDay.calls} calls
						</p>
					{/if}
				{:else}
					<p class="text-xs text-zinc-500">
						No persisted events yet. New LLM calls will appear here.
					</p>
				{/if}
			{/if}
		</Card.Content>
	</Card.Root>

	<Card.Root>
		<Card.Header>
			<Card.Title class="text-sm">Session summary</Card.Title>
			<p class="text-xs text-zinc-500">In-memory aggregation. Resets on bot restart.</p>
		</Card.Header>
		<Card.Content class="space-y-1 text-sm">
			{#if cost.loading}
				<p class="text-zinc-500">Loading…</p>
			{:else if cost.error}
				<p class="text-red-600">Error: {cost.error}</p>
			{:else if cost.data}
				<div>Total cost: <strong>{fmt(cost.data.total_cost_usd)}</strong></div>
				<div>Total calls: {cost.data.total_calls}</div>
				<div>Total tokens: {cost.data.total_tokens.toLocaleString()}</div>
				<div>Cache read tokens: {cost.data.cache_read_tokens.toLocaleString()}</div>
				<div>Cache write tokens: {cost.data.cache_write_tokens.toLocaleString()}</div>
				<div>Cache savings: {fmt(cost.data.cache_savings_usd)}</div>
			{/if}
		</Card.Content>
	</Card.Root>

	<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Breakdown by operation</Card.Title></Card.Header>
			<Card.Content>
				{#if !cost.data || cost.data.by_operation.length === 0}
					<p class="text-sm text-zinc-500">No usage yet this session.</p>
				{:else}
					<Table.Root>
						<Table.Header>
							<Table.Row>
								<Table.Head>Operation</Table.Head>
								<Table.Head class="w-16">Calls</Table.Head>
								<Table.Head class="w-24">Tokens</Table.Head>
								<Table.Head class="w-24">Cost</Table.Head>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{#each [...cost.data.by_operation].sort((a, b) => b.cost_usd - a.cost_usd) as b (b.operation)}
								<Table.Row>
									<Table.Cell class="font-mono text-xs">{b.operation}</Table.Cell>
									<Table.Cell>{b.calls}</Table.Cell>
									<Table.Cell>{b.tokens.toLocaleString()}</Table.Cell>
									<Table.Cell>{fmt(b.cost_usd)}</Table.Cell>
								</Table.Row>
							{/each}
						</Table.Body>
					</Table.Root>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Breakdown by model</Card.Title></Card.Header>
			<Card.Content>
				{#if !cost.data || cost.data.by_model.length === 0}
					<p class="text-sm text-zinc-500">No usage yet this session.</p>
				{:else}
					<Table.Root>
						<Table.Header>
							<Table.Row>
								<Table.Head>Model</Table.Head>
								<Table.Head class="w-16">Calls</Table.Head>
								<Table.Head class="w-24">Tokens</Table.Head>
								<Table.Head class="w-24">Cost</Table.Head>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{#each [...cost.data.by_model].sort((a, b) => b.cost_usd - a.cost_usd) as b (b.model)}
								<Table.Row>
									<Table.Cell class="font-mono text-xs">{b.model}</Table.Cell>
									<Table.Cell>{b.calls}</Table.Cell>
									<Table.Cell>{b.tokens.toLocaleString()}</Table.Cell>
									<Table.Cell>{fmt(b.cost_usd)}</Table.Cell>
								</Table.Row>
							{/each}
						</Table.Body>
					</Table.Root>
				{/if}
			</Card.Content>
		</Card.Root>
	</div>
</div>
