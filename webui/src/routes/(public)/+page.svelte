<script lang="ts">
	// The front door. A first-year looking for their faculty's chat currently
	// finds it only by asking somebody for a link, which means most of the
	// directory is invisible to the people it was built for.
	//
	// Everything here comes from `/api/public/catalog`, which returns four
	// fields per chat and no Telegram id, member count or moderation state. That
	// endpoint is the contract: what a stranger may see is decided once, at the
	// boundary, rather than by a conditional on this page that somebody can
	// delete.
	import { apiFetch } from '$lib/api/client';
	import { plural } from '$lib/format';
	import { Input } from '$lib/components/ui/input/index.js';
	import { ExternalLink, Search } from '@lucide/svelte';
	import type { components } from '$lib/api/types';

	type CatalogItem = components['schemas']['PublicCatalogItem'];

	// Said plainly, because a badge that reads "тихий" is only useful if it stops
	// somebody joining a room where nobody has spoken since March.
	//
	// `unknown` has no entry and renders nothing. The API says it when the
	// recording behind the number is too short to stand on, and an empty space
	// is the honest rendering of "we do not know yet" — a grey "тихий" would be
	// a claim.
	const ACTIVITY: Record<string, { label: string; class: string }> = {
		busy: { label: 'оживлённый', class: 'bg-emerald-50 text-emerald-700' },
		active: { label: 'активный', class: 'bg-zinc-100 text-zinc-600' },
		quiet: { label: 'тихий', class: 'bg-zinc-100 text-zinc-500' }
	};

	const UNGROUPED = 'Остальные';

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
			[item.title, item.group ?? ''].join(' ').toLowerCase().includes(q)
		);
	});

	// The server already sorted by group and then title, so walking the list in
	// order is enough to build the sections — no second sort, and the page
	// cannot disagree with the order the API chose.
	const sections = $derived.by(() => {
		const out: { name: string; chats: CatalogItem[] }[] = [];
		for (const item of filtered) {
			const name = item.group ?? UNGROUPED;
			const last = out.at(-1);
			if (last && last.name === name) last.chats.push(item);
			else out.push({ name, chats: [item] });
		}
		return out;
	});

	function initials(title: string): string {
		const cleaned = title.replace(/[^\p{L}\p{N} ]/gu, '').trim();
		const words = cleaned.split(/\s+/).filter(Boolean);
		if (words.length > 1) return (words[0][0] + words[1][0]).toUpperCase();
		return cleaned.slice(0, 2).toUpperCase() || '#';
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

<section class="mx-auto max-w-6xl space-y-8 px-6 pb-6">
	{#if loading}
		<p class="text-sm text-zinc-500">Загружаем…</p>
	{:else if error}
		<p class="text-sm text-red-600">Не получилось загрузить каталог: {error}</p>
	{:else if sections.length === 0}
		<p class="text-sm text-zinc-500">
			{query ? `По запросу «${query}» ничего не нашлось.` : 'Каталог пока пуст.'}
		</p>
	{:else}
		{#each sections as section (section.name)}
			<div>
				<div class="mb-3 flex items-baseline gap-3 border-b border-zinc-200 pb-2">
					<h2 class="text-sm font-semibold tracking-tight text-zinc-900">{section.name}</h2>
					<span class="font-mono text-xs text-zinc-400">
						{section.chats.length}
						{plural(section.chats.length, 'чат', 'чата', 'чатов')}
					</span>
				</div>

				<div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
					{#each section.chats as chat (chat.link)}
						<a
							href={chat.link}
							target="_blank"
							rel="noopener noreferrer"
							class="group flex items-center gap-3 rounded-md border border-zinc-200 bg-white px-3 py-3 hover:border-zinc-300 hover:bg-zinc-50"
						>
							<div
								class="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-zinc-100 text-xs font-semibold text-zinc-600"
							>
								{initials(chat.title)}
							</div>
							<div class="min-w-0 flex-1">
								<div class="truncate text-sm font-medium text-zinc-900">{chat.title}</div>
								{#if ACTIVITY[chat.activity]}
									<span
										class="mt-0.5 inline-block rounded-full px-2 py-0.5 text-[11px] font-medium {ACTIVITY[
											chat.activity
										].class}"
									>
										{ACTIVITY[chat.activity].label}
									</span>
								{/if}
							</div>
							<ExternalLink class="h-3.5 w-3.5 shrink-0 text-zinc-400 group-hover:text-zinc-600" />
						</a>
					{/each}
				</div>
			</div>
		{/each}
	{/if}
</section>
