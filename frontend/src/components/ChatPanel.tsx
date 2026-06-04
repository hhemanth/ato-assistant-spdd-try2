'use client';

/**
 * T054 [US1] ChatPanel — orchestrates the Slice 1 chat UX.
 *
 * Composes the existing slice-1 surface components into a single
 * client-side workflow:
 *   - input form (textarea + submit button) with a stable per-session UUID;
 *   - inline error notice when the backend or network fails;
 *   - answer surface: rendered text (preserving `[1]`/`[2]` markers),
 *     `<CitationList />`, `<PerAnswerDisclaimer />`, and a textual
 *     confidence line (T138/US7 swaps the textual line for a badge);
 *   - refusal surface: a minimal inline `<aside role="alert">` card —
 *     T053 will extract this into a dedicated `<RefusalCard />` in Slice 2.
 *
 * Accessibility:
 *   - The textarea has an associated `<label>` (linked via `htmlFor`).
 *   - The submit button reflects its disabled state via `aria-disabled`.
 *   - The error notice uses `role="alert"` for assertive announcement.
 *   - The response area uses `aria-live="polite"` so new answers/refusals
 *     are announced without preempting the user.
 *
 * State is intentionally local: this component is the only client-side
 * stateful node in Slice 1. Lifting state into a store would be
 * premature — there's a single submission cycle at a time.
 */
import { useState } from 'react';

import { CitationList } from '@/components/CitationList';
import { PerAnswerDisclaimer } from '@/components/PerAnswerDisclaimer';
import { ChatApiError, postChat } from '@/lib/chatClient';
import type { ChatResponse, RefusalResponse } from '@/lib/types';

function generateSessionId(): string {
  // crypto.randomUUID is in Node 20+ and every modern browser. Falls back
  // to a Math.random-derived id only if the runtime lacks the API (tests,
  // very old environments). Stable across the component lifetime.
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `sess-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
}

// TODO(T053): extract this into `frontend/src/components/RefusalCard.tsx`
// once Slice 2 (refusal taxonomy) is on deck. Keeping the markup inline
// here so Slice 1 stays self-contained.
function InlineRefusalCard({ refusal }: { refusal: RefusalResponse }) {
  return (
    <aside
      role="alert"
      aria-label="Assistant declined to answer"
      className="border border-rose-300 bg-rose-50 text-rose-900 dark:border-rose-700 dark:bg-rose-950 dark:text-rose-100 rounded-md p-4 flex flex-col gap-2"
    >
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center rounded-full bg-rose-200 dark:bg-rose-800 px-2 py-0.5 text-xs font-medium uppercase tracking-wide">
          {refusal.reason_code}
        </span>
        <span className="text-sm font-semibold">This question was declined</span>
      </div>
      <p className="text-sm leading-relaxed">{refusal.user_message}</p>
    </aside>
  );
}

export function ChatPanel(): React.ReactElement {
  const [sessionId] = useState<string>(generateSessionId);
  const [input, setInput] = useState<string>('');
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResponse, setLastResponse] = useState<ChatResponse | null>(null);

  const trimmed = input.trim();
  const disabled = submitting || trimmed.length === 0;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await postChat({ text: trimmed, session_id: sessionId });
      setLastResponse(response);
      setInput('');
    } catch (err) {
      const message =
        err instanceof ChatApiError
          ? `Chat request failed (HTTP ${err.status}): ${err.message}`
          : err instanceof Error
            ? err.message
            : 'Unknown error contacting chat backend';
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section
      aria-label="Ask the ATO Assistant"
      className="max-w-3xl mx-auto px-4 py-6 flex flex-col gap-4"
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label
          htmlFor="chat-question"
          className="text-sm font-medium text-zinc-800 dark:text-zinc-200"
        >
          Your question
        </label>
        <textarea
          id="chat-question"
          name="question"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          rows={4}
          maxLength={4000}
          placeholder="Ask a question about Australian tax"
          className="w-full rounded-md border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 p-3 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={disabled}
            aria-disabled={disabled}
            className="inline-flex items-center justify-center rounded-md bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-300 disabled:text-zinc-500 dark:disabled:bg-zinc-700 dark:disabled:text-zinc-400 text-white text-sm font-medium px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {submitting ? 'Sending…' : 'Ask'}
          </button>
        </div>
      </form>

      {error ? (
        <div
          role="alert"
          className="border border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-100 rounded-md p-3 text-sm"
        >
          {error}
        </div>
      ) : null}

      <div aria-live="polite" className="flex flex-col gap-4">
        {lastResponse?.kind === 'answer' ? (
          <article
            aria-label="Assistant answer"
            className="border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 rounded-md p-4 flex flex-col gap-2"
          >
            <p className="text-sm leading-relaxed whitespace-pre-wrap text-zinc-900 dark:text-zinc-100">
              {lastResponse.text}
            </p>
            <CitationList citations={lastResponse.citations} />
            <PerAnswerDisclaimer />
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2">
              Confidence: {lastResponse.confidence_band}
            </p>
          </article>
        ) : null}

        {lastResponse?.kind === 'refusal' ? (
          <InlineRefusalCard refusal={lastResponse} />
        ) : null}
      </div>
    </section>
  );
}

export default ChatPanel;
