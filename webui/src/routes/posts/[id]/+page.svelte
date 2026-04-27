<script lang="ts">
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { apiFetch } from '$lib/api/client';
	import { toast } from 'svelte-sonner';
	import type { components } from '$lib/api/types';

	type PostDetail = components['schemas']['PostDetail'];
	type PostMutationResponse = components['schemas']['PostMutationResponse'];

	let post = $state<PostDetail | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);
	let busy = $state<'approve' | 'reject' | 'save' | null>(null);
	let editing = $state(false);
	let draft = $state('');

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

	function cancelEdit(): void {
		draft = post?.post_text ?? '';
		editing = false;
	}

	const canMutate = $derived(
		post && !['approved', 'rejected', 'skipped'].includes(post.status.toLowerCase())
	);
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
					<Badge variant="secondary">{post.status}</Badge>
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
			<div class="flex shrink-0 items-center gap-2">
				<Button
					variant="default"
					size="sm"
					onclick={approve}
					disabled={!canMutate || busy !== null}
				>
					{busy === 'approve' ? 'Publishing…' : 'Approve'}
				</Button>
				<Button
					variant="outline"
					size="sm"
					onclick={reject}
					disabled={!canMutate || busy !== null}
				>
					{busy === 'reject' ? 'Rejecting…' : 'Reject'}
				</Button>
				<Button
					variant="outline"
					size="sm"
					onclick={() => (editing = !editing)}
					disabled={!canMutate || busy !== null}
				>
					{editing ? 'Cancel edit' : 'Edit'}
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
						<Button variant="ghost" size="sm" onclick={cancelEdit} disabled={busy === 'save'}
							>Cancel</Button
						>
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

		{#if post.image_urls && post.image_urls.length > 0}
			<Card.Root>
				<Card.Header><Card.Title>Images ({post.image_urls.length})</Card.Title></Card.Header>
				<Card.Content>
					<div class="grid grid-cols-2 gap-3 md:grid-cols-3">
						{#each post.image_urls as url (url)}
							<img src={url} alt="" class="h-32 w-full rounded-md object-cover" loading="lazy" />
						{/each}
					</div>
				</Card.Content>
			</Card.Root>
		{/if}
	{/if}
</div>
