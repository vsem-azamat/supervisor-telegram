<script lang="ts">
	import ActionTile from './ActionTile.svelte';
	import type { components } from '$lib/api/types';
	import type { Component } from 'svelte';
	import {
		AtSign,
		Inbox,
		Lightbulb,
		Network,
		Power,
		Shield,
		Tv,
		VolumeX
	} from '@lucide/svelte';

	type Suggestion = components['schemas']['SuggestionItem'];
	type Tone = 'default' | 'attention' | 'success' | 'warning';

	type Props = {
		items: Suggestion[];
		loading?: boolean;
	};

	let { items, loading = false }: Props = $props();

	const iconByKind: Record<string, Component> = {
		disabled_channel: Power,
		channel_without_sources: Inbox,
		channel_without_username: AtSign,
		unmoderated_chat: Shield,
		silent_chat: VolumeX,
		orphan_chat: Network,
		network_without_channel: Tv
	};

	function toneFor(severity: string): Tone {
		if (severity === 'attention') return 'attention';
		if (severity === 'warning') return 'warning';
		return 'default';
	}

	function iconFor(kind: string): Component {
		return iconByKind[kind] ?? Lightbulb;
	}
</script>

{#if loading}
	<p class="text-xs text-zinc-500">loading…</p>
{:else if items.length === 0}
	<!-- Render nothing — the parent decides whether to show the section header. -->
{:else}
	<div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
		{#each items as item (item.kind + ':' + (item.target_id ?? ''))}
			<ActionTile
				title={item.title}
				caption={item.hint}
				icon={iconFor(item.kind)}
				tone={toneFor(item.severity)}
				href={item.action_url ?? undefined}
				cta={item.action_label ?? 'Open'}
			/>
		{/each}
	</div>
{/if}
