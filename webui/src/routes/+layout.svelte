<script lang="ts">
	// The root layout owns the two things every page needs whoever is looking:
	// the stylesheet and the favicon. Nothing else belongs here, because
	// everything else belongs to one audience or the other.
	//
	// It used to decide, in one `$effect`, whether a page was standalone, public
	// or protected, and bounce anonymous visitors around accordingly. That put
	// the authorisation rule in the same file as the public landing page's
	// chrome, which is how a public page ends up one edit away from demanding a
	// session — or worse, how a protected one ends up not demanding it. The rule
	// now lives in `(admin)/+layout.svelte` and covers exactly the routes nested
	// under it.
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

{@render children()}
