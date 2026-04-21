<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { useLivePoll } from '$lib/hooks/useLivePoll';
	import type { components } from '$lib/api/types';

	type Summary = components['schemas']['SessionCostSummary'];

	const cost = useLivePoll<Summary>('/api/costs/session', 60_000);

	function fmt(usd: number): string {
		return usd < 0.01 ? '<$0.01' : `$${usd.toFixed(4)}`;
	}
</script>

<div class="mx-auto max-w-4xl space-y-4 px-6 py-6">
	<header class="flex items-baseline justify-between">
		<h2 class="text-lg font-semibold tracking-tight">Costs</h2>
		{#if cost.lastUpdatedAt}
			<span class="text-xs text-zinc-500">Updated {cost.lastUpdatedAt.toLocaleTimeString()}</span>
		{/if}
	</header>

	<Card.Root>
		<Card.Header>
			<Card.Title class="text-sm">Session summary</Card.Title>
			<p class="text-xs text-zinc-500">
				In-memory aggregation from <code>cost_tracker</code>. Resets on bot restart — persistent history is Phase 1.5.
			</p>
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
							<Table.Head class="w-24">Calls</Table.Head>
							<Table.Head class="w-32">Tokens</Table.Head>
							<Table.Head class="w-32">Cost</Table.Head>
							<Table.Head class="w-32">Cache savings</Table.Head>
						</Table.Row>
					</Table.Header>
					<Table.Body>
						{#each cost.data.by_operation as b (b.operation)}
							<Table.Row>
								<Table.Cell class="font-mono text-xs">{b.operation}</Table.Cell>
								<Table.Cell>{b.calls}</Table.Cell>
								<Table.Cell>{b.tokens.toLocaleString()}</Table.Cell>
								<Table.Cell>{fmt(b.cost_usd)}</Table.Cell>
								<Table.Cell>{fmt(b.cache_savings_usd)}</Table.Cell>
							</Table.Row>
						{/each}
					</Table.Body>
				</Table.Root>
			{/if}
		</Card.Content>
	</Card.Root>
</div>
