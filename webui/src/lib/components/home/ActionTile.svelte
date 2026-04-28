<script lang="ts">
	import type { Component, Snippet } from 'svelte';
	import { ArrowRight } from '@lucide/svelte';

	type Props = {
		title: string;
		value?: string | number;
		caption?: string;
		href?: string;
		cta?: string;
		icon?: Component;
		tone?: 'default' | 'attention' | 'success' | 'warning';
		children?: Snippet;
	};
	let {
		title,
		value,
		caption,
		href,
		cta = 'Open',
		icon: Icon,
		tone = 'default',
		children
	}: Props = $props();

	const toneClasses: Record<NonNullable<Props['tone']>, string> = {
		default: 'border-zinc-200 bg-white',
		attention: 'border-amber-200 bg-amber-50/40',
		success: 'border-emerald-200 bg-emerald-50/40',
		warning: 'border-rose-200 bg-rose-50/40'
	};
	const iconToneClasses: Record<NonNullable<Props['tone']>, string> = {
		default: 'bg-zinc-100 text-zinc-600',
		attention: 'bg-amber-100 text-amber-700',
		success: 'bg-emerald-100 text-emerald-700',
		warning: 'bg-rose-100 text-rose-700'
	};
</script>

{#snippet body()}
	<div class="flex items-start gap-3">
		{#if Icon}
			<div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-md {iconToneClasses[tone]}">
				<Icon class="h-4 w-4" />
			</div>
		{/if}
		<div class="min-w-0 flex-1">
			<div class="text-xs font-medium text-zinc-600">{title}</div>
			{#if value !== undefined && value !== ''}
				<div class="mt-0.5 text-2xl font-semibold tracking-tight text-zinc-900">{value}</div>
			{/if}
			{#if caption}
				<div class="mt-0.5 text-xs text-zinc-500">{caption}</div>
			{/if}
			{#if children}
				<div class="mt-1.5">{@render children()}</div>
			{/if}
		</div>
		{#if href}
			<div class="flex items-center gap-1 self-end text-xs font-medium text-zinc-700">
				<span>{cta}</span>
				<ArrowRight class="h-3.5 w-3.5" />
			</div>
		{/if}
	</div>
{/snippet}

{#if href}
	<a
		{href}
		class="block rounded-lg border p-4 transition-colors hover:bg-zinc-50 {toneClasses[tone]}"
	>
		{@render body()}
	</a>
{:else}
	<div class="rounded-lg border p-4 {toneClasses[tone]}">{@render body()}</div>
{/if}
