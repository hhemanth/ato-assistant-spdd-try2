/**
 * T049 [US1] Typed wrapper around the backend `POST /chat` endpoint.
 *
 * Single responsibility: marshal the request, dispatch the HTTP call,
 * narrow the response to the OpenAPI-defined discriminated union, and
 * surface failures as a typed `ChatApiError`. No React, no state, no
 * Tailwind — keeps unit-testing trivial.
 *
 * Base URL precedence:
 *   1. `opts.baseUrl` (test/Storybook override).
 *   2. `process.env.NEXT_PUBLIC_BACKEND_BASE_URL` (build-time injected
 *      by Next.js — see `frontend/.env.example`).
 *   3. `http://localhost:8000` (dev fallback).
 */
import type { ChatRequest, ChatResponse } from '@/lib/types';

const DEFAULT_BASE_URL = 'http://localhost:8000';

/**
 * Typed error raised for any non-success HTTP response or for a
 * structurally invalid body (missing/unknown `kind` discriminator).
 *
 * `status === 0` indicates a network-level failure (fetch rejected) or
 * the body discriminator check failed without an HTTP status to attach.
 */
export class ChatApiError extends Error {
  readonly status: number;
  readonly body?: unknown;

  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.name = 'ChatApiError';
    this.status = status;
    this.body = body;
  }
}

export interface PostChatOptions {
  /** Override the resolved base URL. Useful for tests. */
  baseUrl?: string;
  /** Override the global fetch — useful for tests. Defaults to `globalThis.fetch`. */
  fetchImpl?: typeof fetch;
  /** Optional AbortSignal to cancel the request. */
  signal?: AbortSignal;
}

function resolveBaseUrl(override?: string): string {
  if (override) return override;
  const fromEnv = process.env.NEXT_PUBLIC_BACKEND_BASE_URL;
  if (fromEnv && fromEnv.length > 0) return fromEnv;
  return DEFAULT_BASE_URL;
}

async function safeParseJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

function isChatResponse(value: unknown): value is ChatResponse {
  if (!value || typeof value !== 'object') return false;
  const kind = (value as { kind?: unknown }).kind;
  return kind === 'answer' || kind === 'refusal';
}

/**
 * POST a chat request to the backend.
 *
 * @throws {ChatApiError} on non-2xx HTTP status or structurally invalid body.
 */
export async function postChat(
  req: ChatRequest,
  opts?: PostChatOptions,
): Promise<ChatResponse> {
  const baseUrl = resolveBaseUrl(opts?.baseUrl).replace(/\/+$/, '');
  const fetchImpl = opts?.fetchImpl ?? globalThis.fetch;

  let response: Response;
  try {
    response = await fetchImpl(`${baseUrl}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(req),
      signal: opts?.signal,
    });
  } catch (err) {
    throw new ChatApiError(
      `Network error contacting chat backend: ${(err as Error).message}`,
      0,
    );
  }

  if (!response.ok) {
    const body = await safeParseJson(response);
    throw new ChatApiError(
      `Chat backend responded with HTTP ${response.status}`,
      response.status,
      body,
    );
  }

  const body = await safeParseJson(response);
  if (!isChatResponse(body)) {
    throw new ChatApiError(
      'Chat backend returned a response with missing or unknown `kind` discriminator',
      response.status,
      body,
    );
  }
  return body;
}
