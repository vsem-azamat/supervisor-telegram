<script lang="ts">
	import { hashId, initialsFor } from './tree';

	type Props = {
		chatId: number;
		title: string | null;
		hasPhoto: boolean;
		size?: 'xs' | 'sm' | 'md' | 'lg';
	};
	let { chatId, title, hasPhoto, size = 'sm' }: Props = $props();

	// Lazy fallback to initials if the image fails to decode (e.g. file_id
	// went stale before the next snapshot tick rotated it). The state flag
	// is keyed by chatId so the component re-arms when the parent recycles
	// it across rows.
	let imgFailed = $state(false);
	$effect(() => {
		// trigger re-eval whenever chatId changes
		void chatId;
		imgFailed = false;
	});

	const palette = [
		'bg-amber-100 text-amber-700',
		'bg-emerald-100 text-emerald-700',
		'bg-sky-100 text-sky-700',
		'bg-violet-100 text-violet-700',
		'bg-rose-100 text-rose-700',
		'bg-fuchsia-100 text-fuchsia-700',
		'bg-lime-100 text-lime-700',
		'bg-orange-100 text-orange-700'
	];
	const fallbackClass = $derived(palette[hashId(chatId) % palette.length]);
	const initials = $derived(initialsFor(title, chatId));

	const dim = $derived(
		size === 'xs'
			? 'h-5 w-5 text-[9px]'
			: size === 'sm'
				? 'h-6 w-6 text-[10px]'
				: size === 'md'
					? 'h-8 w-8 text-xs'
					: 'h-10 w-10 text-sm'
	);
	const showPhoto = $derived(hasPhoto && !imgFailed);
</script>

{#if showPhoto}
	<img
		src={`/api/chats/${chatId}/avatar`}
		alt=""
		class="{dim} shrink-0 rounded-full object-cover"
		loading="lazy"
		onerror={() => (imgFailed = true)}
	/>
{:else}
	<span
		class="{dim} {fallbackClass} flex shrink-0 items-center justify-center rounded-full font-semibold tracking-tight"
		aria-hidden="true"
	>
		{initials}
	</span>
{/if}
