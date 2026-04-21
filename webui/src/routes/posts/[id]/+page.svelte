<script lang="ts">
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { apiFetch } from '$lib/api/client';
	import type { components } from '$lib/api/types';

	type PostDetail = components['schemas']['PostDetail'];

	let post = $state<PostDetail | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);

	const postId = $derived(page.params.id);

	async function load() {
		loading = true;
		const res = await apiFetch<PostDetail>(`/api/posts/${postId}`);
		if (res.error) {
			error = res.error.message;
			post = null;
		} else {
			post = res.data;
			error = null;
		}
		loading = false;
	}

	$effect(() => {
		void load();
	});

	function stub(action: string) {
		alert(`"${action}" will land in Phase 4. For now, use Telegram.`);
	}
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
						<a href={post.source_url} target="_blank" rel="noreferrer" class="text-xs text-blue-600 hover:underline">Source</a>
					{/if}
				</div>
			</div>
			<div class="flex shrink-0 items-center gap-2">
				<Button variant="outline" size="sm" onclick={() => stub('approve')}>Approve</Button>
				<Button variant="outline" size="sm" onclick={() => stub('reject')}>Reject</Button>
				<Button variant="outline" size="sm" onclick={() => stub('edit')}>Edit</Button>
			</div>
		</header>

		<Card.Root>
			<Card.Header><Card.Title>Body</Card.Title></Card.Header>
			<Card.Content>
				<pre class="whitespace-pre-wrap font-sans text-sm leading-6 text-zinc-800">{post.post_text}</pre>
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
