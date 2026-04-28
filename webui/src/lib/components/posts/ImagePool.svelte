<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { apiFetch } from '$lib/api/client';
	import { GripVertical, ImagePlus, Search, Trash2, X } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import type { components } from '$lib/api/types';

	type ImageMutationResponse = components['schemas']['ImageMutationResponse'];

	// OpenAPI surfaces image_candidates as Record<string, unknown>[] because the
	// pydantic schema uses `list[dict[str, Any]]`. We narrow at the access site
	// rather than forcing the API to be more rigid.
	type RawCandidate = { [key: string]: unknown };

	type Props = {
		postId: string | number;
		selected: string[];
		pool: RawCandidate[];
		canEdit: boolean;
		onChange: (resp: ImageMutationResponse) => void;
	};

	let { postId, selected, pool, canEdit, onChange }: Props = $props();

	function asString(v: unknown): string | undefined {
		return typeof v === 'string' ? v : undefined;
	}
	function asNumber(v: unknown): number | undefined {
		return typeof v === 'number' ? v : undefined;
	}
	function asBool(v: unknown): boolean {
		return v === true;
	}
	function urlOf(c: RawCandidate): string {
		return asString(c.url) ?? '';
	}

	let busy = $state<string | null>(null);
	let addUrl = $state('');
	let searchQuery = $state('');

	async function call(
		path: string,
		init: RequestInit,
		busyKey: string,
		successPrefix?: string
	): Promise<void> {
		busy = busyKey;
		const res = await apiFetch<ImageMutationResponse>(path, init);
		busy = null;
		if (res.error) {
			toast.error(res.error.message);
			return;
		}
		const message = res.data.message;
		if (successPrefix) toast.success(`${successPrefix} — ${message}`);
		else toast.success(message);
		onChange(res.data);
	}

	function useCandidate(idx: number): Promise<void> {
		return call(
			`/api/posts/${postId}/images/use`,
			{ method: 'POST', body: JSON.stringify({ pool_index: idx }) },
			`use-${idx}`
		);
	}

	function removeAt(position: number): Promise<void> {
		return call(`/api/posts/${postId}/images/${position}`, { method: 'DELETE' }, `remove-${position}`);
	}

	function clearAll(): Promise<void> {
		if (!confirm('Detach all images from this post? Pool is kept.')) {
			return Promise.resolve();
		}
		return call(`/api/posts/${postId}/images`, { method: 'DELETE' }, 'clear');
	}

	function addByUrl(): Promise<void> {
		const u = addUrl.trim();
		if (!u) return Promise.resolve();
		return call(
			`/api/posts/${postId}/images/url`,
			{ method: 'POST', body: JSON.stringify({ url: u }) },
			'add-url'
		).then(() => {
			addUrl = '';
		});
	}

	function searchImages(): Promise<void> {
		const q = searchQuery.trim();
		if (!q) return Promise.resolve();
		return call(
			`/api/posts/${postId}/images/search`,
			{ method: 'POST', body: JSON.stringify({ query: q }) },
			'search'
		);
	}

	async function moveSelected(from: number, dir: -1 | 1): Promise<void> {
		const to = from + dir;
		if (to < 0 || to >= selected.length) return;
		const order = selected.map((_, i) => i);
		[order[from], order[to]] = [order[to], order[from]];
		await call(
			`/api/posts/${postId}/images/reorder`,
			{ method: 'POST', body: JSON.stringify({ order }) },
			`move-${from}`
		);
	}

	const selectedSet = $derived(new Set(selected));
	const poolNotSelected = $derived(pool.filter((c) => !selectedSet.has(urlOf(c))));
</script>

<div class="space-y-4">
	<!-- Selected -->
	<div>
		<div class="mb-2 flex items-center justify-between">
			<div class="text-xs font-medium text-zinc-700">
				Selected
				<span class="ml-1 text-zinc-400">({selected.length})</span>
			</div>
			{#if canEdit && selected.length > 0}
				<Button
					variant="ghost"
					size="sm"
					class="text-red-600 hover:bg-red-50 hover:text-red-700"
					disabled={busy !== null}
					onclick={clearAll}
				>
					<Trash2 class="mr-1 h-3.5 w-3.5" />
					{busy === 'clear' ? 'Clearing…' : 'Clear all'}
				</Button>
			{/if}
		</div>
		{#if selected.length === 0}
			<p class="rounded-md border border-dashed border-zinc-200 px-3 py-6 text-center text-xs text-zinc-500">
				No images selected. Pick from the pool below or add one.
			</p>
		{:else}
			<div class="grid grid-cols-2 gap-3 md:grid-cols-3">
				{#each selected as url, i (url)}
					<div class="group relative overflow-hidden rounded-md border border-zinc-200 bg-zinc-50">
						<img src={url} alt="" class="h-32 w-full object-cover" loading="lazy" />
						<div class="absolute top-1 left-1 rounded bg-zinc-900/70 px-1.5 py-0.5 text-[10px] font-medium text-white">
							#{i + 1}
						</div>
						{#if canEdit}
							<div class="absolute right-1 bottom-1 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
								{#if selected.length > 1}
									<button
										type="button"
										title="Move left"
										class="rounded bg-zinc-900/80 px-1.5 py-0.5 text-[10px] text-white hover:bg-zinc-900"
										onclick={() => moveSelected(i, -1)}
										disabled={i === 0 || busy !== null}
									>‹</button>
									<button
										type="button"
										title="Move right"
										class="rounded bg-zinc-900/80 px-1.5 py-0.5 text-[10px] text-white hover:bg-zinc-900"
										onclick={() => moveSelected(i, 1)}
										disabled={i === selected.length - 1 || busy !== null}
									>›</button>
								{/if}
								<button
									type="button"
									title="Remove"
									class="rounded bg-rose-600/90 px-1.5 py-0.5 text-[10px] text-white hover:bg-rose-700"
									onclick={() => removeAt(i)}
									disabled={busy !== null}
								>
									<X class="h-3 w-3" />
								</button>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Pool -->
	{#if pool.length > 0}
		<div>
			<div class="mb-2 text-xs font-medium text-zinc-700">
				Pool
				<span class="ml-1 text-zinc-400">({poolNotSelected.length} unused / {pool.length} total)</span>
			</div>
			<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
				{#each pool as cand, idx (urlOf(cand) || idx)}
					{@const url = urlOf(cand)}
					{@const source = asString(cand.source) ?? 'unknown'}
					{@const description = asString(cand.description)}
					{@const quality = asNumber(cand.quality_score)}
					{@const relevance = asNumber(cand.relevance_score)}
					{@const isLogo = asBool(cand.is_logo)}
					{@const isTextSlide = asBool(cand.is_text_slide)}
					{@const isSelected = selectedSet.has(url)}
					{@const dim = isLogo || isTextSlide}
					<div
						class="group relative overflow-hidden rounded-md border bg-white {isSelected
							? 'border-emerald-300 ring-1 ring-emerald-200'
							: 'border-zinc-200'} {dim ? 'opacity-60' : ''}"
					>
						<img src={url} alt="" class="h-28 w-full object-cover" loading="lazy" />
						<div class="space-y-0.5 px-2 py-1.5 text-[10px]">
							<div class="flex items-center justify-between gap-1">
								<span class="truncate font-mono text-zinc-500" title={source}>{source}</span>
								<span class="shrink-0 tabular-nums text-zinc-600">
									q{quality ?? '–'} · r{relevance ?? '–'}
								</span>
							</div>
							{#if description}
								<div class="line-clamp-2 text-zinc-500" title={description}>
									{description}
								</div>
							{/if}
							{#if isLogo || isTextSlide}
								<div class="text-[9px] text-amber-700">
									{isLogo ? 'logo' : ''}{isLogo && isTextSlide ? ' · ' : ''}{isTextSlide ? 'text-slide' : ''}
								</div>
							{/if}
						</div>
						{#if canEdit && !isSelected}
							<button
								type="button"
								class="absolute inset-x-0 bottom-0 translate-y-full bg-zinc-900 py-1 text-[10px] font-medium text-white transition-transform group-hover:translate-y-0"
								onclick={() => useCandidate(idx)}
								disabled={busy !== null}
							>
								{busy === `use-${idx}` ? 'Adding…' : 'Use this'}
							</button>
						{:else if isSelected}
							<div class="absolute top-1 right-1 rounded bg-emerald-600 px-1.5 py-0.5 text-[10px] font-medium text-white">
								selected
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Add controls -->
	{#if canEdit}
		<div class="space-y-2 rounded-md border border-zinc-200 bg-zinc-50 p-3">
			<div class="text-[10px] font-semibold tracking-wider text-zinc-500 uppercase">Add to pool</div>
			<div class="flex gap-2">
				<Input
					placeholder="Image URL — vetted by vision model"
					bind:value={addUrl}
					class="flex-1"
					onkeydown={(e: KeyboardEvent) => {
						if (e.key === 'Enter') void addByUrl();
					}}
				/>
				<Button size="sm" onclick={addByUrl} disabled={!addUrl.trim() || busy !== null}>
					<ImagePlus class="mr-1 h-3.5 w-3.5" />
					{busy === 'add-url' ? 'Adding…' : 'Add'}
				</Button>
			</div>
			<div class="flex gap-2">
				<Input
					placeholder="Search query — Brave + vision-score"
					bind:value={searchQuery}
					class="flex-1"
					onkeydown={(e: KeyboardEvent) => {
						if (e.key === 'Enter') void searchImages();
					}}
				/>
				<Button size="sm" variant="outline" onclick={searchImages} disabled={!searchQuery.trim() || busy !== null}>
					<Search class="mr-1 h-3.5 w-3.5" />
					{busy === 'search' ? 'Searching…' : 'Search'}
				</Button>
			</div>
			<p class="flex items-center gap-1 text-[10px] text-zinc-500">
				<GripVertical class="h-3 w-3" />
				Hover a selected image to reorder or remove. Pool entries can be promoted to selected.
			</p>
		</div>
	{/if}
</div>
