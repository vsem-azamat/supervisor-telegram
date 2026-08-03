<script lang="ts">
	// The public half. No session is asked for, none is offered, and no request
	// on these pages needs one — the only endpoint they touch is
	// `/api/public/catalog`.
	//
	// The sign-in link is the one deliberate seam between the halves. It points
	// at `/login`, which is a page and not a route group, so nothing about the
	// console leaks into a bundle a student downloads.
	import { LogIn } from '@lucide/svelte';

	let { children } = $props();
</script>

<div class="min-h-screen bg-zinc-50 text-zinc-900">
	<header class="border-b border-zinc-200 bg-white">
		<div class="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
			<a href="/" class="flex items-center gap-2">
				<div
					class="flex h-7 w-7 items-center justify-center rounded-md bg-zinc-900 text-sm font-semibold text-white"
				>
					K
				</div>
				<span class="text-sm font-semibold tracking-tight text-zinc-900">Konnekt</span>
			</a>
			<div class="flex items-center gap-2">
				<a
					href="/ads"
					class="rounded-md px-3 py-1.5 text-sm font-medium text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900"
				>
					Реклама
				</a>
				<a
					href="/login"
					class="flex items-center gap-1.5 rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-100"
				>
					<LogIn class="h-3.5 w-3.5" />
					Вход для админов
				</a>
			</div>
		</div>
	</header>

	<main>
		{@render children()}
	</main>

	<footer class="mx-auto max-w-6xl px-6 py-10 text-xs text-zinc-500">
		Студенческие чаты Чехии. Модерируются, спам вычищается.
	</footer>
</div>
