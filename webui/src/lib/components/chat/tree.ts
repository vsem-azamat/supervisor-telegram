import type { components } from '$lib/api/types';

type RawNode = components['schemas']['ChatNode'];

export type EnrichedNode = {
	id: number;
	title: string | null;
	relation_notes: string | null | undefined;
	depth: number;
	subtreeSize: number; // 1 + sum of children's subtreeSize
	children: EnrichedNode[];
};

/** Recursively annotate every node with its depth and subtree size.
 * Subtree size includes the node itself, so leaves are 1.
 */
export function enrichTree(nodes: RawNode[], depth = 0): EnrichedNode[] {
	return nodes.map((n) => {
		const children = enrichTree(n.children, depth + 1);
		const subtreeSize = 1 + children.reduce((acc, c) => acc + c.subtreeSize, 0);
		return {
			id: n.id,
			title: n.title,
			relation_notes: n.relation_notes,
			depth,
			subtreeSize,
			children
		};
	});
}

export type TreeStats = {
	total: number;
	rootCount: number;
	maxDepth: number; // 0 = single-node tree
	biggestNetwork: number; // largest subtreeSize across roots
};

export function computeStats(roots: EnrichedNode[]): TreeStats {
	let total = 0;
	let maxDepth = 0;
	let biggest = 0;
	const visit = (n: EnrichedNode): void => {
		total += 1;
		if (n.depth > maxDepth) maxDepth = n.depth;
		n.children.forEach(visit);
	};
	for (const r of roots) {
		biggest = Math.max(biggest, r.subtreeSize);
		visit(r);
	}
	return { total, rootCount: roots.length, maxDepth, biggestNetwork: biggest };
}

/** Collect every id reachable in the forest. */
export function collectIds(roots: EnrichedNode[]): Set<number> {
	const out = new Set<number>();
	const visit = (n: EnrichedNode): void => {
		out.add(n.id);
		n.children.forEach(visit);
	};
	roots.forEach(visit);
	return out;
}

/** Filter the tree to nodes whose title or relation_notes match `query`,
 * keeping every ancestor of a match so the path is preserved. Returns a
 * new tree (immutable). Empty query returns the input unchanged.
 *
 * Matching is case-insensitive substring; falsy fields are ignored.
 */
export function filterTree(roots: EnrichedNode[], query: string): EnrichedNode[] {
	const q = query.trim().toLowerCase();
	if (!q) return roots;

	const matches = (n: EnrichedNode): boolean => {
		const t = (n.title ?? '').toLowerCase();
		const r = (n.relation_notes ?? '').toLowerCase();
		const idStr = String(n.id);
		return t.includes(q) || r.includes(q) || idStr.includes(q);
	};

	const walk = (nodes: EnrichedNode[]): EnrichedNode[] => {
		const out: EnrichedNode[] = [];
		for (const n of nodes) {
			const filteredChildren = walk(n.children);
			if (matches(n) || filteredChildren.length > 0) {
				out.push({ ...n, children: filteredChildren });
			}
		}
		return out;
	};
	return walk(roots);
}

/** Stable hash → palette index for avatar color. The exact palette lives in
 * the Svelte component; this just produces an integer so consumers can index
 * into whatever array they like.
 */
export function hashId(n: number): number {
	// xorshift-ish; we just want consistent dispersion across small ints.
	let x = n | 0;
	x ^= x << 13;
	x ^= x >>> 17;
	x ^= x << 5;
	return Math.abs(x);
}

export function initialsFor(title: string | null, id: number): string {
	if (!title) return `#${String(id).slice(-2)}`;
	const cleaned = title.trim();
	if (!cleaned) return `#${String(id).slice(-2)}`;
	const words = cleaned.split(/\s+/).slice(0, 2);
	const letters = words.map((w) => w.replace(/[^\p{L}\p{N}]/gu, '').charAt(0).toUpperCase()).join('');
	return letters || cleaned.charAt(0).toUpperCase();
}
