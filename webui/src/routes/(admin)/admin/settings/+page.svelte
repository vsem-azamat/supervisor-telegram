<script lang="ts">
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { apiFetch } from '$lib/api/client';
	import { auth } from '$lib/stores/auth.svelte';
	import { toast } from 'svelte-sonner';
	import type { components } from '$lib/api/types';

	type AdminSessionRead = components['schemas']['AdminSessionRead'];
	type SystemStatus = components['schemas']['SystemStatus'];

	let sessions = $state<AdminSessionRead[] | null>(null);
	let system = $state<SystemStatus | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let revoking = $state<string | null>(null);

	async function load(): Promise<void> {
		loading = true;
		const [s, sys] = await Promise.all([
			apiFetch<AdminSessionRead[]>('/api/admin/sessions'),
			apiFetch<SystemStatus>('/api/admin/system')
		]);
		if (s.error) error = s.error.message;
		else sessions = s.data;
		if (sys.error) error = sys.error.message;
		else system = sys.data;
		loading = false;
	}

	$effect(() => {
		void load();
	});

	async function revokeSession(id: string): Promise<void> {
		if (!confirm('Revoke this session? The other browser will be signed out.')) return;
		revoking = id;
		const res = await apiFetch(`/api/admin/sessions/${id}`, { method: 'DELETE' });
		revoking = null;
		if (res.error) toast.error(res.error.message);
		else {
			toast.success('Session revoked');
			await load();
		}
	}

	function formatRelative(iso: string): string {
		const d = new Date(iso);
		const diffMs = Date.now() - d.getTime();
		const diffMin = Math.round(diffMs / 60_000);
		if (diffMin < 1) return 'just now';
		if (diffMin < 60) return `${diffMin}m ago`;
		const diffH = Math.round(diffMin / 60);
		if (diffH < 24) return `${diffH}h ago`;
		const diffD = Math.round(diffH / 24);
		return `${diffD}d ago`;
	}

	function shortenAgent(ua: string | null): string {
		if (!ua) return '—';
		// Pull a recognizable slice — browser name + maybe OS hint.
		const browserMatch = ua.match(/(Firefox|Chrome|Safari|Edg|Opera)\/[\d.]+/);
		const osMatch = ua.match(/(Windows NT [\d.]+|Mac OS X [\d_.]+|Linux|Android|iOS|iPhone|iPad)/);
		const parts = [browserMatch?.[0], osMatch?.[0]].filter(Boolean);
		return parts.length ? parts.join(' · ') : ua.slice(0, 60);
	}
</script>

<div class="mx-auto max-w-4xl space-y-4 px-6 py-6">
	<header>
		<h2 class="text-lg font-semibold tracking-tight">Settings</h2>
		<p class="mt-1 text-sm text-zinc-500">Operational status and active session management.</p>
	</header>

	{#if loading}
		<p class="text-sm text-zinc-500">Loading…</p>
	{:else if error}
		<p class="text-sm text-red-600">Error: {error}</p>
	{:else}
		<Card.Root>
			<Card.Header><Card.Title class="text-sm">Identity</Card.Title></Card.Header>
			<Card.Content class="text-sm">
				{#if auth.me}
					Signed in as user <span class="font-mono">#{auth.me.user_id}</span>
				{/if}
			</Card.Content>
		</Card.Root>

		<Card.Root>
			<Card.Header>
				<Card.Title class="text-sm">
					Active sessions
					{#if sessions}
						<span class="ml-1 text-xs font-normal text-zinc-500">({sessions.length})</span>
					{/if}
				</Card.Title>
			</Card.Header>
			<Card.Content>
				{#if !sessions || sessions.length === 0}
					<p class="text-xs text-zinc-500">No active sessions.</p>
				{:else}
					<ul class="divide-y divide-zinc-100 text-sm">
						{#each sessions as s (s.session_id)}
							<li class="flex items-center justify-between gap-2 py-2">
								<div class="flex min-w-0 flex-col">
									<div class="flex items-baseline gap-2">
										<span class="text-zinc-800">{shortenAgent(s.user_agent)}</span>
										{#if s.is_current}<Badge class="text-[10px]">this session</Badge>{/if}
									</div>
									<div class="text-xs text-zinc-500">
										{s.ip ?? '—'} · last seen {formatRelative(s.last_seen_at)} · expires
										{new Date(s.expires_at).toLocaleDateString()}
									</div>
								</div>
								{#if !s.is_current}
									<Button
										variant="ghost"
										size="sm"
										class="text-red-600 hover:bg-red-50 hover:text-red-700"
										onclick={() => revokeSession(s.session_id)}
										disabled={revoking === s.session_id}
									>
										{revoking === s.session_id ? '…' : 'Revoke'}
									</Button>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
			</Card.Content>
		</Card.Root>

		{#if system}
			<Card.Root>
				<Card.Header><Card.Title class="text-sm">System</Card.Title></Card.Header>
				<Card.Content class="grid grid-cols-2 gap-2 text-sm">
					<div>
						Telethon: {#if system.telethon_connected}<Badge>connected</Badge>{:else}
							<Badge variant="secondary">not configured</Badge>{/if}
					</div>
					<div>
						Publish bot: {#if system.publish_bot_ready}<Badge>ready</Badge>{:else}
							<Badge variant="secondary">not started</Badge>{/if}
					</div>
					<div>
						Super admins: <span class="font-mono text-xs">{system.super_admin_ids.join(', ')}</span>
					</div>
					<div>Session TTL: {system.session_ttl_days} days</div>
					<div class="col-span-2">
						Allowed origins:
						<span class="font-mono text-xs">
							{system.allowed_origins.length > 0 ? system.allowed_origins.join(', ') : 'http://localhost:5173 (default)'}
						</span>
					</div>
				</Card.Content>
			</Card.Root>

			<Card.Root>
				<Card.Header><Card.Title class="text-sm">Feature flags</Card.Title></Card.Header>
				<Card.Content>
					<ul class="grid grid-cols-1 gap-1 text-sm md:grid-cols-2">
						{#each system.feature_flags as f (f.name)}
							<li class="flex items-center justify-between border-b border-zinc-100 py-1 last:border-0">
								<span class="font-mono text-xs text-zinc-600">{f.name}</span>
								{#if f.enabled}<Badge>on</Badge>{:else}<Badge variant="secondary">off</Badge>{/if}
							</li>
						{/each}
					</ul>
					<p class="mt-3 text-xs text-zinc-500">
						These flags are read from environment / .env at process start. To change, redeploy.
					</p>
				</Card.Content>
			</Card.Root>
		{/if}
	{/if}
</div>
