'use client';

/**
 * T052 [US1] CitationList — numbered list of citations surfacing source
 * freshness (FR-006).
 *
 * Client component because each citation link is a live click target and
 * the `liveness_status` may eventually drive interactive visual state
 * (tooltips, refresh actions). Currently renders pure markup but the
 * `'use client'` boundary is locked in to avoid future churn.
 *
 * Type strategy: `@/lib/types` (T049) does not exist yet. We define a
 * minimal `Citation` here matching the OpenAPI `Citation` schema and
 * export it so T049 can re-export from `@/lib/types`. The import
 * direction can be inverted later without touching consumers.
 */

export type LivenessStatus = 'live' | 'unknown' | 'stale';

export interface Citation {
  /** Matches the [N] marker in the rendered answer text. */
  index: number;
  /** Absolute https URL into www.ato.gov.au. */
  source_url: string;
  /** Optional in-page anchor fragment (without the leading `#`). */
  anchor?: string | null;
  /** Short excerpt of the cited passage. */
  snippet: string;
  /**
   * Page's `Last-Modified` value at index time. Surfaces FR-006 source
   * freshness. `null` when the page omitted the header.
   */
  source_last_modified?: string | null;
  /** Liveness flag from the retrieval/freshness check. */
  liveness_status: LivenessStatus;
}

export interface CitationListProps {
  citations: Citation[];
}

const dateFormatter = new Intl.DateTimeFormat('en-AU', { dateStyle: 'medium' });

function formatLastModified(value: string | null | undefined): string {
  if (!value) {
    return 'Last updated: unknown';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return 'Last updated: unknown';
  }
  return `Last updated: ${dateFormatter.format(parsed)}`;
}

/**
 * Trim the URL to a path-only display string so the visible link text
 * stays short. The full URL is preserved as the link target plus the
 * native browser tooltip via the `title` attribute.
 */
function displayPath(sourceUrl: string): string {
  try {
    const parsed = new URL(sourceUrl);
    const pathPart = `${parsed.pathname}${parsed.search}${parsed.hash}`;
    return pathPart || sourceUrl;
  } catch {
    return sourceUrl;
  }
}

function LivenessBadge({ status }: { status: LivenessStatus }): React.ReactElement {
  if (status === 'live') {
    return (
      <span
        aria-label="Source verified live"
        className="inline-flex items-center text-xs text-green-700 dark:text-green-400"
      >
        <span aria-hidden="true">✓</span>
        <span className="sr-only">live</span>
      </span>
    );
  }
  if (status === 'stale') {
    return (
      <span
        aria-label="Source may be stale"
        className="inline-flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400"
      >
        <span aria-hidden="true">⚠</span>
        <span>stale source</span>
      </span>
    );
  }
  return (
    <span
      aria-label="Source liveness unknown"
      className="inline-flex items-center text-xs text-zinc-500 dark:text-zinc-400"
    >
      <span aria-hidden="true">•</span>
      <span className="sr-only">unknown</span>
    </span>
  );
}

export function CitationList({ citations }: CitationListProps): React.ReactElement {
  return (
    <ol
      aria-label="Citations supporting this answer"
      className="mt-4 space-y-3 list-decimal pl-6 text-sm"
    >
      {citations.map((citation) => {
        const href = citation.anchor
          ? `${citation.source_url}#${citation.anchor}`
          : citation.source_url;
        return (
          <li key={citation.index} value={citation.index} className="pl-1">
            <div className="flex flex-wrap items-center gap-2">
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                title={citation.source_url}
                className="text-blue-700 dark:text-blue-300 underline break-all"
              >
                {displayPath(citation.source_url)}
              </a>
              <LivenessBadge status={citation.liveness_status} />
            </div>
            <blockquote className="mt-1 border-l-2 border-zinc-300 dark:border-zinc-700 pl-3 text-zinc-700 dark:text-zinc-300 italic">
              {citation.snippet}
            </blockquote>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              {formatLastModified(citation.source_last_modified)}
            </p>
          </li>
        );
      })}
    </ol>
  );
}

export default CitationList;
