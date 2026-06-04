/**
 * T049 [US1] Canonical TypeScript mirror of the backend HTTP contract
 * (`specs/001-ato-chat-rag/contracts/api-chat.openapi.yaml`).
 *
 * These types are the single source of truth on the frontend for the
 * `/chat` request/response payloads. They MUST stay byte-equivalent to
 * the OpenAPI schemas — CI validates the live backend against the same
 * document, and a drift here is a drift everywhere.
 *
 * Composition rule: anywhere a component needs to reason about a
 * citation, an answer, or a refusal, it imports from `@/lib/types` so
 * that the discriminator (`kind`) narrows cleanly at the call site.
 */
export interface ChatRequest {
  /** User's question. Max 4000 chars per the contract. */
  text: string;
  /** Client-generated UUIDv4 for the browser session. */
  session_id: string;
}

/** Source-freshness flag attached to every citation (FR-006). */
export type LivenessStatus = 'live' | 'unknown' | 'stale';

export interface Citation {
  /** Matches the `[N]` marker in the rendered answer text. */
  index: number;
  /** Absolute https URL into www.ato.gov.au. */
  source_url: string;
  /** Optional in-page anchor fragment (without the leading `#`). */
  anchor?: string | null;
  /** Short excerpt of the cited passage. */
  snippet: string;
  /**
   * Page's `Last-Modified` value at index time. `null` when the page
   * omitted the header.
   */
  source_last_modified?: string | null;
  /** Liveness flag from the retrieval/freshness check. */
  liveness_status: LivenessStatus;
}

/** Coarse confidence-and-correctness badge (FR-016). */
export type ConfidenceBand = 'high' | 'medium' | 'low';

export interface AnswerResponse {
  kind: 'answer';
  query_id: string;
  /** Contains inline citation markers `[1]`, `[2]` referring to `citations[i]`. */
  text: string;
  citations: Citation[];
  confidence_band: ConfidenceBand;
  /** Required per-answer disclaimer text (FR-003). */
  per_answer_disclaimer: string;
  /** e.g. claude-sonnet-4-6. */
  model_identity: string;
  /** ISO-8601 timestamp. */
  generated_at: string;
}

/** Refusal taxonomy (FR-004 + FR-005 + FR-018b). */
export type RefusalReasonCode =
  | 'no-source'
  | 'low-confidence'
  | 'citation-misalignment'
  | 'stale-source'
  | 'pii-integral'
  | 'pii-scanner-fail'
  | 'out-of-scope'
  | 'inappropriate'
  | 'personal-advice'
  | 'non-english';

export interface RefusalResponse {
  kind: 'refusal';
  query_id: string;
  reason_code: RefusalReasonCode;
  user_message: string;
  /** ISO-8601 timestamp. */
  refused_at: string;
}

/** Discriminated union over `kind`. */
export type ChatResponse = AnswerResponse | RefusalResponse;
