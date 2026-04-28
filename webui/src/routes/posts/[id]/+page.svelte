<script lang="ts">
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import ImagePool from '$lib/components/posts/ImagePool.svelte';
	import { apiFetch } from '$lib/api/client';
	import { Check, Pencil, RefreshCw, Sparkles, X } from '@lucide/svelte';
	import { toast } from 'svelte-sonner';
	import type { components } from '$lib/api/types';

	type PostDetail = components['schemas']['PostDetail'];
	type PostMutationResponse = components['schemas']['PostMutationResponse'];
	type ImageMutationResponse = components['schemas']['ImageMutationResponse'];

	let post = $state<PostDetail | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);
	let busy = $state<'approve' | 'reject' | 'save' | 'regen' | null>(null);
	let editing = $state(false);
	let draft = $state('');
	let showPreCritic = $state(false);

	const postId = $derived(page.params.id);

	async function load(): Promise<void> {
		loading = true;
		const res = await apiFetch<PostDetail>(`/api/posts/${postId}`);
		if (res.error) {
			error = res.error.message;
			post = null;
		} else {
			post = res.data;
			draft = res.data.post_text ?? '';
			error = null;
		}
		loading = false;
	}

	$effect(() => {
		void load();
	});

	async function approve(): Promise<void> {
		if (busy) return;
		busy = 'approve';
		const res = await apiFetch<PostMutationResponse>(`/api/posts/${postId}/approve`, { method: 'POST' });
		busy = null;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success(res.data.message);
			await load();
		}
	}

	async function reject(): Promise<void> {
		if (busy) return;
		if (!confirm('Reject this post?')) return;
		busy = 'reject';
		const res = await apiFetch<PostMutationResponse>(`/api/posts/${postId}/reject`, { method: 'POST' });
		busy = null;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success(res.data.message);
			await load();
		}
	}

	async function save(): Promise<void> {
		if (busy) return;
		busy = 'save';
		const res = await apiFetch<PostMutationResponse>(`/api/posts/${postId}/text`, {
			method: 'PATCH',
			body: JSON.stringify({ text: draft })
		});
		busy = null;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success(res.data.message);
			editing = false;
			await load();
		}
	}

	async function regenerate(): Promise<void> {
		if (busy) return;
		if (!confirm('Regenerate this post from its source items? Current text and images will be replaced.')) return;
		busy = 'regen';
		const res = await apiFetch<PostMutationResponse>(`/api/posts/${postId}/regenerate`, {
			method: 'POST'
		});
		busy = null;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success(res.data.message);
			await load();
		}
	}

	function cancelEdit(): void {
		draft = post?.post_text ?? '';
		editing = false;
	}

	function applyImageMutation(resp: ImageMutationResponse): void {
		if (!post) return;
		post = { ...post, image_urls: resp.image_urls, image_candidates: resp.image_candidates };
	}

	const canMutate = $derived(
		post && !['approved', 'rejected', 'skipped', 'published'].includes(post.status.toLowerCase())
	);

	const STATUS_TONE: Record<string, string> = {
		draft: 'bg-zinc-100 text-zinc-700',
		sent_for_review: 'bg-amber-100 text-amber-800',
		approved: 'bg-blue-100 text-blue-800',
		scheduled: 'bg-indigo-100 text-indigo-800',
		published: 'bg-emerald-100 text-emerald-800',
		rejected: 'bg-rose-100 text-rose-800',
		failed: 'bg-rose-100 text-rose-800',
		deleted: 'bg-zinc-100 text-zinc-500'
	};
</script>

<div class="mx-auto max-w-3xl space-y-4 px-6 py-6">
	{#if loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if error}
		<p class="text-sm text-red-600">Error: {error}</p>
	{:else if post}
		<header class="flex items-start justify-between gap-4">
			<div>
				<div class="flex items-center gap-2 text-xs text-zinc-500">
					<a href="/posts" class="hover:underline">Posts</a>
					<span>›</span>
					<span class="font-mono">#{post.id}</span>
				</div>
				<h2 class="mt-1 text-xl font-semibold tracking-tight">{post.title}</h2>
				<div class="mt-2 flex items-center gap-2">
					<span
						class="rounded-md px-2 py-0.5 text-xs font-medium {STATUS_TONE[post.status] ??
							'bg-zinc-100 text-zinc-700'}"
					>
						{post.status}
					</span>
					{#if post.source_url}
						<a
							href={post.source_url}
							target="_blank"
							rel="noreferrer"
							class="text-xs text-blue-600 hover:underline">Source</a
						>
					{/if}
				</div>
			</div>
			<div class="flex shrink-0 flex-wrap items-center gap-2 justify-end">
				<Button
					variant="default"
					size="sm"
					onclick={approve}
					disabled={!canMutate || busy !== null}
				>
					<Check class="mr-1 h-3.5 w-3.5" />
					{busy === 'approve' ? 'Publishing…' : 'Approve'}
				</Button>
				<Button
					variant="outline"
					size="sm"
					onclick={reject}
					disabled={!canMutate || busy !== null}
				>
					<X class="mr-1 h-3.5 w-3.5" />
					{busy === 'reject' ? 'Rejecting…' : 'Reject'}
				</Button>
				<Button
					variant="outline"
					size="sm"
					onclick={() => (editing = !editing)}
					disabled={!canMutate || busy !== null}
				>
					<Pencil class="mr-1 h-3.5 w-3.5" />
					{editing ? 'Cancel edit' : 'Edit'}
				</Button>
				<Button
					variant="outline"
					size="sm"
					onclick={regenerate}
					disabled={!canMutate || busy !== null}
					title="Re-run generator over the post's source items"
				>
					<RefreshCw class="mr-1 h-3.5 w-3.5" />
					{busy === 'regen' ? 'Regenerating…' : 'Regenerate'}
				</Button>
			</div>
		</header>

		<Card.Root>
			<Card.Header><Card.Title>Body</Card.Title></Card.Header>
			<Card.Content>
				{#if editing}
					<textarea
						bind:value={draft}
						class="min-h-[20rem] w-full resize-y rounded-md border border-zinc-200 p-3 font-mono text-sm leading-6 focus:border-zinc-400 focus:outline-none disabled:opacity-60"
						disabled={busy === 'save'}
					></textarea>
					<div class="mt-2 flex items-center justify-end gap-2">
						<Button variant="ghost" size="sm" onclick={cancelEdit} disabled={busy === 'save'}>
							Cancel
						</Button>
						<Button size="sm" onclick={save} disabled={busy === 'save' || !draft.trim()}>
							{busy === 'save' ? 'Saving…' : 'Save'}
						</Button>
					</div>
				{:else}
					<pre
						class="font-sans text-sm leading-6 text-zinc-800 whitespace-pre-wrap">{post.post_text}</pre>
				{/if}
			</Card.Content>
		</Card.Root>

		{#if post.pre_critic_text && post.pre_critic_text !== post.post_text}
			<Card.Root>
				<Card.Header class="flex flex-row items-center justify-between space-y-0">
					<Card.Title class="flex items-center gap-1.5 text-sm">
						<Sparkles class="h-3.5 w-3.5 text-amber-600" />
						Pre-critic version
					</Card.Title>
					<Button variant="ghost" size="sm" onclick={() => (showPreCritic = !showPreCritic)}>
						{showPreCritic ? 'Hide' : 'Show'}
					</Button>
				</Card.Header>
				{#if showPreCritic}
					<Card.Content>
						<p class="mb-2 text-xs text-zinc-500">
							Generator output before the polish pass — useful when the critic over-rewrites.
						</p>
						<pre
							class="font-sans text-sm leading-6 text-zinc-700 whitespace-pre-wrap">{post.pre_critic_text}</pre>
					</Card.Content>
				{/if}
			</Card.Root>
		{/if}

		<Card.Root>
			<Card.Header>
				<Card.Title class="text-sm">
					Images
					<span class="ml-1 text-xs font-normal text-zinc-500">
						{(post.image_urls ?? []).length} selected · {(post.image_candidates ?? []).length} in pool
					</span>
				</Card.Title>
			</Card.Header>
			<Card.Content>
				<ImagePool
					postId={post.id}
					selected={post.image_urls ?? []}
					pool={post.image_candidates ?? []}
					canEdit={canMutate ?? false}
					onChange={applyImageMutation}
				/>
			</Card.Content>
		</Card.Root>

		{#if post.source_items && post.source_items.length > 0}
			<Card.Root>
				<Card.Header>
					<Card.Title class="text-sm">
						Source items
						<span class="ml-1 text-xs font-normal text-zinc-500">
							({post.source_items.length})
						</span>
					</Card.Title>
				</Card.Header>
				<Card.Content>
					<ul class="space-y-1.5 text-xs">
						{#each post.source_items as src, i (i)}
							{@const url = typeof src.url === 'string' ? src.url : null}
							{@const title = typeof src.title === 'string' ? src.title : null}
							<li class="flex items-baseline gap-2">
								<Badge variant="secondary" class="shrink-0 text-[10px]">{i + 1}</Badge>
								{#if url}
									<a href={url} target="_blank" rel="noreferrer" class="truncate text-blue-600 hover:underline">
										{title ?? url}
									</a>
								{:else}
									<span class="truncate text-zinc-700">{title ?? '(untitled)'}</span>
								{/if}
							</li>
						{/each}
					</ul>
				</Card.Content>
			</Card.Root>
		{/if}
	{/if}
</div>
