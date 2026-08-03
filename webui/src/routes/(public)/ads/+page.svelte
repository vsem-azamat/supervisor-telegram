<script lang="ts">
	// Where the "Реклама в чатах" button in the bot lands.
	//
	// Somebody arrives here having already decided they want to buy something;
	// the page's whole job is to say how far a post would carry and who to ask.
	// Every figure comes from `/api/public/reach`, which aggregates per
	// university and never per chat — the catalogue already says which chats
	// exist, and how large each individual room is does not need publishing next
	// to a price.
	import { apiFetch } from '$lib/api/client';
	import { num, plural } from '$lib/format';
	import { Send } from '@lucide/svelte';
	import type { components } from '$lib/api/types';

	type Reach = components['schemas']['PublicReach'];

	// Who answers. The bot handles questions about chats; a person handles this.
	const CONTACT = 'czech_media_admin';

	let reach = $state<Reach | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			const res = await apiFetch<Reach>('/api/public/reach');
			if (res.error) {
				error = res.error.message;
				return;
			}
			reach = res.data;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		void load();
	});

	// Telegram does not answer for every chat every time the snapshot loop runs,
	// so the member total can cover part of the catalogue. Saying "≈18 400"
	// without saying that would be a number somebody pays against.
	const partial = $derived(!!reach && reach.measured_chats < reach.chats);
</script>

<svelte:head><title>Реклама в студенческих чатах — Konnekt</title></svelte:head>

<section class="mx-auto max-w-4xl px-6 pt-14 pb-8">
	<h1 class="text-3xl font-semibold tracking-tight text-zinc-900">Реклама в студенческих чатах</h1>
	<p class="mt-2 max-w-xl text-sm text-zinc-600">
		Чаты студентов чешских вузов — по университетам, факультетам и общежитиям. Живые, с
		модерацией: спам и чужая реклама вычищаются, поэтому ваш пост читают.
	</p>
</section>

<section class="mx-auto max-w-4xl space-y-10 px-6 pb-16">
	{#if loading}
		<p class="text-sm text-zinc-500">Загружаем…</p>
	{:else if error}
		<p class="text-sm text-red-600">Не получилось загрузить данные: {error}</p>
	{:else if reach}
		<div class="flex flex-wrap gap-10">
			<div>
				<div class="font-mono text-3xl font-semibold tabular-nums tracking-tight text-zinc-900">
					{num(reach.chats)}
				</div>
				<div class="mt-1 text-[10px] font-semibold tracking-wider text-zinc-500 uppercase">
					{plural(reach.chats, 'чат', 'чата', 'чатов')}
				</div>
			</div>
			<div>
				<div class="font-mono text-3xl font-semibold tabular-nums tracking-tight text-zinc-900">
					{partial ? '≈' : ''}{num(reach.members)}
				</div>
				<div class="mt-1 text-[10px] font-semibold tracking-wider text-zinc-500 uppercase">
					{plural(reach.members, 'участник', 'участника', 'участников')}
				</div>
			</div>
			<div>
				<div class="font-mono text-3xl font-semibold tabular-nums tracking-tight text-zinc-900">
					{num(reach.groups.length)}
				</div>
				<div class="mt-1 text-[10px] font-semibold tracking-wider text-zinc-500 uppercase">
					{plural(reach.groups.length, 'направление', 'направления', 'направлений')}
				</div>
			</div>
		</div>

		{#if partial}
			<p class="-mt-6 max-w-xl text-xs text-zinc-500">
				Участники посчитаны по {reach.measured_chats} из {reach.chats}
				{plural(reach.chats, 'чата', 'чатов', 'чатов')} — Telegram отвечает не по всем. Настоящая
				цифра выше этой, но обещать мы можем только измеренное.
			</p>
		{/if}

		{#if reach.groups.length > 0}
			<div>
				<h2 class="text-sm font-semibold tracking-tight text-zinc-900">Куда попадёт пост</h2>
				<div class="mt-3 overflow-x-auto">
					<table class="w-full min-w-md text-sm">
						<thead>
							<tr class="border-b border-zinc-200 text-left">
								<th
									class="pb-2 text-[10px] font-semibold tracking-wider text-zinc-500 uppercase"
								>
									Направление
								</th>
								<th
									class="pb-2 text-right text-[10px] font-semibold tracking-wider text-zinc-500 uppercase"
								>
									Чатов
								</th>
								<th
									class="pb-2 text-right text-[10px] font-semibold tracking-wider text-zinc-500 uppercase"
								>
									Участников
								</th>
							</tr>
						</thead>
						<tbody>
							{#each reach.groups as group (group.name)}
								<tr class="border-b border-zinc-100 last:border-0">
									<td class="py-2 text-zinc-900">{group.name}</td>
									<td class="py-2 text-right font-mono tabular-nums text-zinc-600">
										{num(group.chats)}
									</td>
									<td class="py-2 text-right font-mono tabular-nums text-zinc-600">
										{group.members > 0 ? num(group.members) : '—'}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}
	{/if}

	<div>
		<h2 class="text-sm font-semibold tracking-tight text-zinc-900">Как это работает</h2>
		<ol class="mt-3 space-y-2 text-sm text-zinc-600">
			<li class="flex gap-3">
				<span class="font-mono text-xs text-zinc-400">1</span>
				<span>Пишете, что хотите разместить.</span>
			</li>
			<li class="flex gap-3">
				<span class="font-mono text-xs text-zinc-400">2</span>
				<span>Отвечаем, в каких чатах это уместно и сколько стоит.</span>
			</li>
			<li class="flex gap-3">
				<span class="font-mono text-xs text-zinc-400">3</span>
				<span>Пост выходит, вы получаете ссылки на него.</span>
			</li>
		</ol>
	</div>

	<div class="rounded-md border border-zinc-200 bg-white p-5">
		<h2 class="text-sm font-semibold tracking-tight text-zinc-900">Что мы не размещаем</h2>
		<p class="mt-2 max-w-xl text-sm text-zinc-600">
			Займы, ставки, дипломы под ключ и всё, за что студенту потом расплачиваться. Модерация
			чистит такое каждый день — продавать то же самое сверху было бы странно.
		</p>
	</div>

	<a
		href="https://t.me/{CONTACT}"
		target="_blank"
		rel="noopener noreferrer"
		class="inline-flex items-center gap-2 rounded-md bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-zinc-800"
	>
		<Send class="h-4 w-4" />
		Написать в Telegram
	</a>
</section>
