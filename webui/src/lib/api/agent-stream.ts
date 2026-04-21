/**
 * SSE consumer for POST /api/agent/turn.
 *
 * EventSource is GET-only, so we hand-parse the `text/event-stream` body
 * coming back from `fetch`. Yields one event object per SSE frame; the
 * caller decides how to render each `type`. Cancelling the AbortController
 * stops the network read AND the underlying agent run (the route's
 * generator catches CancelledError and tears down the runner task).
 */

export type AgentStreamEvent =
	| { type: 'tool_call'; tool_name: string; tool_call_id: string; label: string }
	| {
			type: 'tool_result';
			tool_name: string;
			tool_call_id: string;
			result_preview: string;
	  }
	| { type: 'token'; text: string }
	| { type: 'done'; final_text: string; message_count: number }
	| { type: 'error'; message: string };

export async function* streamAgentTurn(
	message: string,
	signal?: AbortSignal
): AsyncGenerator<AgentStreamEvent> {
	const res = await fetch('/api/agent/turn', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
		body: JSON.stringify({ message }),
		signal
	});
	if (!res.ok || !res.body) {
		throw new Error(`agent turn HTTP ${res.status}`);
	}
	const reader = res.body.getReader();
	const decoder = new TextDecoder('utf-8');
	let buffer = '';
	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			buffer += decoder.decode(value, { stream: true });
			let sep: number;
			while ((sep = buffer.indexOf('\n\n')) !== -1) {
				const frame = buffer.slice(0, sep);
				buffer = buffer.slice(sep + 2);
				const event = parseFrame(frame);
				if (event) yield event;
			}
		}
		const tail = buffer.trim();
		if (tail) {
			const event = parseFrame(tail);
			if (event) yield event;
		}
	} finally {
		reader.releaseLock();
	}
}

function parseFrame(frame: string): AgentStreamEvent | null {
	const dataLines: string[] = [];
	for (const line of frame.split('\n')) {
		if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
	}
	if (dataLines.length === 0) return null;
	try {
		return JSON.parse(dataLines.join('\n')) as AgentStreamEvent;
	} catch {
		return null;
	}
}
