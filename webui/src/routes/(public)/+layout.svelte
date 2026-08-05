<script lang="ts">
	// The public half. No session is asked for, none is offered, and no request
	// on these pages needs one — the only endpoint they touch is
	// `/api/public/catalog`.
	//
	// There is no seam to the console any more, and no link to it. Signing in
	// means opening the Mini App from the bot, so a sign-in link on a public
	// page would point at a door that only opens from the other side.
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
			<a
				href="/ads"
				class="rounded-md px-3 py-1.5 text-sm font-medium text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900"
			>
				Реклама
			</a>
		</div>
	</header>

	<main>
		{@render children()}
	</main>

	<footer class="mx-auto max-w-6xl px-6 py-10 text-xs text-zinc-500">
		Студенческие чаты Чехии. Модерируются, спам вычищается.
	</footer>
</div>
