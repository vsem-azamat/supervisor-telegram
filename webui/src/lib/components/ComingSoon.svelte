<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';

	type Props = { title: string; phase: number; note?: string };

	let { title, phase, note }: Props = $props();
</script>

<div class="mx-auto max-w-2xl px-6 py-10">
	<Card.Root>
		<Card.Header class="flex flex-row items-center justify-between">
			<Card.Title>{title}</Card.Title>
			<Badge variant="secondary">Phase {phase}</Badge>
		</Card.Header>
		<Card.Content>
			<p class="text-sm text-zinc-600">
				{note ?? 'This page is part of Phase ' + phase + ' of the rollout. Until then you can still do this in Telegram.'}
			</p>
		</Card.Content>
	</Card.Root>
</div>
