<script lang="ts">
	// The front door. A first-year looking for their faculty's chat currently
	// finds it only by asking somebody for a link, which means half the
	// directory is invisible to the people it was built for.
	//
	// Everything here comes from `/api/public/catalog`, which returns the
	// curated links and nothing else — no member counts, no moderation state, no
	// Telegram ids. That endpoint is the contract: if a field should not be seen
	// by a stranger, it never reaches this page, rather than being hidden by a
	// conditional that somebody can delete.
	import { apiFetch } from '$lib/api/client';
	import { Input } from '$lib/components/ui/input/index.js';
	import { ExternalLink, Search } from '@lucide/svelte';
	import type { components } from '$lib/api/types';

	type CatalogItem = components['schemas']['PublicCatalogItem'];

	let query = $state('');
	let items = $state<CatalogItem[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			const res = await apiFetch<CatalogItem[]>('/api/public/catalog');
			if (res.error) {
				error = res.error.message;
				items = [];
				return;
			}
			items = res.data;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		void load();
	});

	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		if (!q) return items;
		return items.filter((item) =>
			[item.title, item.subtitle ?? ''].join(' ').toLowerCase().includes(q)
		);
	});

	function initials(title: string): string {
		return title.replace(/[^\p{L}\p{N} ]/gu, '').trim().slice(0, 2).toUpperCase() || '#';
	}
</script>

<svelte:head><title>Konnekt — студенческие чаты Чехии</title></svelte:head>

<section class="mx-auto max-w-6xl px-6 pt-14 pb-8">
	<h1 class="text-3xl font-semibold tracking-tight text-zinc-900">Найди чат своего факультета</h1>
	<p class="mt-2 max-w-lg text-sm text-zinc-600">
		Университеты, факультеты, общежития. Открытые чаты, за которыми следят модераторы.
	</p>

	<div class="relative mt-6 w-full max-w-md">
		<Search
			class="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-zinc-400"
		/>
		<Input bind:value={query} placeholder="ČVUT, информатика, Strahov…" class="h-10 pl-9" />
	</div>
</section>

<section class="mx-auto max-w-6xl px-6 pb-6">
	{#if loading}
		<p class="text-sm text-zinc-500">Загружаем…</p>
	{:else if error}
		<p class="text-sm text-red-600">Не получилось загрузить каталог: {error}</p>
	{:else if filtered.length === 0}
		<p class="text-sm text-zinc-500">
			{query ? `По запросу «${query}» ничего не нашлось.` : 'Каталог пока пуст.'}
		</p>
	{:else}
		<div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
			{#each filtered as item (`${item.resource_type}:${item.id}`)}
				<a
					href={item.subtitle ?? '#'}
					target="_blank"
					rel="noopener noreferrer"
					class="group flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-3 hover:border-zinc-300 hover:bg-zinc-50"
				>
					<div
						class="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-zinc-100 text-xs font-semibold text-zinc-600"
					>
						{initials(item.title)}
					</div>
					<div class="min-w-0 flex-1">
						<div class="truncate text-sm font-medium text-zinc-900">{item.title}</div>
					</div>
					<ExternalLink class="h-3.5 w-3.5 shrink-0 text-zinc-400 group-hover:text-zinc-600" />
				</a>
			{/each}
		</div>
	{/if}
</section>
