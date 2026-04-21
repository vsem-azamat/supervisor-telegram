<script lang="ts">
	import { onMount } from 'svelte';

	type Post = {
		id: number;
		channel_id: number;
		title: string;
		post_text: string;
		status: string;
		image_url: string | null;
		image_urls: string[] | null;
		source_url: string | null;
		created_at: string;
	};

	let posts = $state<Post[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const res = await fetch('/api/posts?limit=50');
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			posts = await res.json();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});
</script>

<div class="mx-auto max-w-4xl px-6 py-10">
	<h1 class="text-3xl font-semibold tracking-tight">Konnekt — review panel</h1>
	<p class="mt-2 text-sm text-zinc-500">Dev scaffold · SvelteKit + Tailwind + FastAPI</p>

	<section class="mt-8">
		{#if loading}
			<p class="text-zinc-500">Loading…</p>
		{:else if error}
			<p class="text-red-600">Error: {error}</p>
		{:else if posts.length === 0}
			<p class="text-zinc-500">No posts yet.</p>
		{:else}
			<ul class="divide-y divide-zinc-200">
				{#each posts as post (post.id)}
					<li class="py-4">
						<div class="flex items-baseline gap-3">
							<span
								class="rounded-sm bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700"
							>
								{post.status}
							</span>
							<h2 class="text-lg font-medium">{post.title}</h2>
						</div>
						<p class="mt-2 line-clamp-3 text-sm text-zinc-600">{post.post_text}</p>
						{#if post.source_url}
							<a
								href={post.source_url}
								class="mt-2 inline-block text-xs text-blue-600 hover:underline"
								target="_blank"
								rel="noreferrer">{post.source_url}</a
							>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</section>
</div>
