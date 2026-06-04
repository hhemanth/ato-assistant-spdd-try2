# Feature Specification: ATO Chat with Cited Answers and RAG Pipeline

**Feature Branch**: `001-ato-chat-rag`

**Created**: 2026-06-03

**Status**: Draft

**Input**: User description:
"Build an ATO chat app that answers Australian-tax questions with citations
sourced exclusively from the ATO official website. Every answer must carry a
citation; without a citation the system refuses to answer. Each answer is
graded on confidence and correctness. User input is scanned for PII (name,
email, date of birth, and similar identifiers): if PII can be safely masked
without changing the question, the masked version is sent to the language
model; otherwise the system refuses. The system refuses inappropriate
content and non-Australian-tax questions. The system does not give advice —
only facts backed by ATO citations. A predominant app-level disclaimer is
shown to every user, and every answer carries a per-answer disclaimer
directing the user to a registered tax accountant for personal advice. A
golden evaluation set of 30 question/expected-answer pairs is produced for
quality measurement. The corpus is built by a module that first crawls the
ATO website to produce a list of leaf-level URLs and then scrapes those
pages to populate the RAG pipeline."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a question, receive a cited answer or a refusal (Priority: P1) 🎯 MVP

A member of the public visits the ATO Assistant, reads the predominant
disclaimer at session entry, and types a tax question. The system either
returns a concise factual answer that is grounded in retrieved ATO content
and carries one or more inline citations to ato.gov.au, or it refuses with a
clear explanation. Every answer also displays a per-answer disclaimer
directing the user to consult a registered tax agent for personal advice.

**Why this priority**: This is the product's core value proposition and the
minimum viable slice. Without it, the rest of the system has no user-facing
outcome to protect. It exercises every architectural boundary
(retrieve → ground → cite → present → refuse) end-to-end on a seed corpus.

**Independent Test**: Operate the assistant against a small hand-curated
seed corpus of ATO pages. Submit a known in-scope question and verify the
answer contains a citation that resolves to the correct ATO URL and that
both the predominant and per-answer disclaimers are visible. Submit a
question for which the seed corpus has no relevant content and verify the
system refuses to answer.

**Acceptance Scenarios**:

1. **Given** the seed corpus contains the ATO page on "Tax-free threshold",
   **When** the user asks "What is the tax-free threshold in Australia?",
   **Then** the system returns an answer that states the threshold figure
   and includes an inline citation that resolves to the relevant
   `ato.gov.au` URL, and the per-answer disclaimer is displayed beneath the
   answer.

2. **Given** the seed corpus has no content covering an asked topic,
   **When** the user asks an in-scope question for which no source is
   indexed, **Then** the system refuses to answer, states it cannot find an
   authoritative ATO source, and does not produce a speculative answer.

3. **Given** any session, **When** the user opens the chat, **Then** the
   predominant app-level disclaimer is visible above the input field before
   the first question is sent.

4. **Given** a generated answer, **When** the answer is rendered,
   **Then** the per-answer disclaimer ("This information is sourced from
   ato.gov.au and is not personal advice — consult a registered tax agent
   for advice on your specific situation") is rendered with the answer.

---

### User Story 2 - PII in queries is masked before the LLM or the query is refused (Priority: P2)

Before a user query reaches the language model, the system scans it for
personally identifiable information (full name, email address, phone number,
date of birth, residential address, TFN, ABN). If the PII is incidental to
the question's meaning, the system masks the PII tokens and forwards the
masked query. If the PII is integral to the question (e.g., the user asks
about their own specific TFN), the system refuses and tells the user to
contact the ATO or a registered tax agent directly with personal details.

**Why this priority**: Trust and legal compliance. Sending taxpayer-
identifying data to a third-party language model would breach Australian
Privacy Principles and the project constitution. This must be in place
before any external user exposure.

**Independent Test**: Submit a curated set of queries containing each PII
class — half "incidental" (e.g., name appears in a story), half "integral"
(e.g., "What is the tax rate on $X earned by John Smith with TFN
123-456-789?"). Verify the incidental queries reach the LLM with PII
redacted and the integral queries are refused. Verify no PII appears in
logs, audit records, or downstream telemetry.

**Acceptance Scenarios**:

1. **Given** a query containing an email address that is incidental to the
   question, **When** the user submits the query, **Then** the email is
   replaced with a redaction token before the query reaches the LLM, and
   the masking action is recorded in the audit log without storing the
   original email in plaintext.

2. **Given** a query in which a TFN is integral to the question,
   **When** the user submits the query, **Then** the system refuses with a
   redirect to the ATO contact channel or a registered tax agent and the
   query is never forwarded to the LLM.

3. **Given** any masked query, **When** logs and audit records are
   inspected, **Then** no plaintext PII is present.

---

### User Story 3 - Out-of-scope, inappropriate, and personal-advice questions are refused (Priority: P2)

The system classifies every incoming query against three refusal classes
before retrieval: out-of-scope (not about Australian tax), inappropriate
(unsafe, abusive, illegal), and personal-advice (requires professional
judgment). Refused queries return a brief explanation of why and, where
appropriate, a pointer to where the user can get help.

**Why this priority**: A grounded RAG system can still produce misleading
output if it tries to answer questions outside its competence. Refusing
explicitly is more trustworthy than over-stretching to an unrelated source.

**Independent Test**: Submit a curated set of queries: 5 out-of-scope (NZ
tax, US tax, weather), 3 inappropriate (illegal advice, abusive content), 5
personal-advice ("should I incorporate?", "is X deductible for me?"), and
5 in-scope/general (control). Verify each refusal category is detected and
the in-scope controls are not falsely refused.

**Acceptance Scenarios**:

1. **Given** a question about US federal income tax, **When** the user
   submits it, **Then** the system refuses and explains the scope is limited
   to Australian Taxation Office content.

2. **Given** a question asking whether a specific deduction applies to the
   user's personal situation, **When** the user submits it, **Then** the
   system refuses with a redirect to a registered tax agent rather than
   speculate about the user's circumstances.

3. **Given** an in-scope general question (e.g., "What is GST?"), **When**
   the user submits it, **Then** the system does not falsely refuse and
   instead proceeds to retrieval.

---

### User Story 4 - Crawl the ATO website to produce a leaf-level URL inventory (Priority: P2)

An ingestion module crawls the configured ATO seed pages and produces a
machine-readable inventory of leaf-level URLs (pages with substantive
content, not navigation hubs). Each entry records the URL, discovery
timestamp, crawl depth, HTTP status, and whether the page was classified
as a leaf. The crawler respects `robots.txt` and a configured polite rate
limit, and identifies itself with a project-specific user agent.

**Why this priority**: The retrieval index quality is bounded by the URL
inventory. Producing this list as a discrete, reviewable artifact lets
domain reviewers audit corpus scope before content is ingested.

**Independent Test**: Run the crawler against a single configured ATO
section (e.g., "Individuals → Income and deductions") with a small depth
cap. Verify the inventory file contains the expected leaf URLs (compared
against a hand-curated reference list of at least 20 URLs in that section)
and excludes navigation hubs, search pages, and PDF download links unless
explicitly enabled.

**Acceptance Scenarios**:

1. **Given** a configured ATO seed URL, **When** the crawler runs to its
   configured depth, **Then** it produces an inventory file containing
   discovered leaf URLs with their HTTP status and discovery timestamp.

2. **Given** any crawl run, **When** the crawler encounters a URL
   disallowed by `robots.txt`, **Then** it skips the URL and records the
   skip reason in the run report.

3. **Given** any crawl run, **When** the crawler issues requests, **Then**
   it does so at no more than the configured rate (default: 1 request per
   second) and identifies itself with the project user agent.

---

### User Story 5 - Scrape inventory URLs and populate the retrieval index (Priority: P2)

Given a leaf-URL inventory from User Story 4, the scraping module fetches
each page, extracts the main content (excluding navigation, headers,
footers, and unrelated sidebars), chunks the content, embeds the chunks,
and writes them to the retrieval index. Every chunk is stored with its
source URL, fetch timestamp, content hash, and the source's last-modified
timestamp.

**Why this priority**: This replaces the seed corpus introduced in User
Story 1 with a representative corpus drawn from the full URL inventory,
making the assistant useful beyond demo questions.

**Independent Test**: Run the scraper against a 50-URL slice of the
inventory. (If User Story 4 has not been completed, a hand-curated URL
list of equivalent size MAY be substituted as the input so this story
remains independently testable.) Verify each chunk in the index is
traceable to a real source URL, that re-running the scrape after a
content change produces an updated chunk and a superseded record, and
that retrieval can return a chunk by content keyword.

**Acceptance Scenarios**:

1. **Given** an inventory entry for a live ATO page, **When** the scraper
   processes it, **Then** the main content is extracted, chunked, embedded,
   and written to the index with provenance metadata (URL, fetch_at,
   content_hash, last_modified).

2. **Given** a page whose content changes between two scrape runs,
   **When** the scraper re-runs, **Then** the new content is reflected in
   the index and the prior version is marked as superseded with an audit
   record.

3. **Given** any chunk in the index, **When** an auditor queries by chunk
   ID, **Then** the full provenance (source URL, fetch timestamp, content
   hash, last-modified) is returned.

---

### User Story 6 - Golden evaluation set and harness (Priority: P2)

A golden evaluation set of 30 question/expected-answer/expected-citation
triples is authored and stored under version control. An evaluation harness
runs the set against the assistant and produces a report measuring
citation correctness (does the cited URL actually support the answer?),
refusal correctness (are out-of-scope and PII-integral questions refused
as expected?), and groundedness (do the cited URLs cover all factual
claims in the answer?).

**Why this priority**: Per the constitution, the answer-quality evaluation
harness gates releases. The 30-question golden set is the smallest viable
gold standard for that gate.

**Independent Test**: Run the harness against the assistant built in User
Story 1 (seed corpus) and confirm a pass/fail verdict per question and
aggregate metrics are produced. Hand-verify five randomly selected
verdicts.

**Acceptance Scenarios**:

1. **Given** the golden set file is present, **When** the harness runs,
   **Then** every question yields a verdict (pass / fail / refused) and the
   harness exits with a non-zero status if any of the configured thresholds
   are missed.

2. **Given** a question in the golden set whose expected outcome is a
   refusal, **When** the harness runs, **Then** an actual refusal is scored
   as a pass and an actual answer is scored as a fail.

3. **Given** any harness run, **When** the run completes, **Then** the
   report contains per-question detail and aggregate metrics for citation
   correctness, refusal correctness, and groundedness.

---

### User Story 7 - Per-answer confidence and correctness grading (Priority: P3)

Every generated answer is accompanied by a confidence score (derived from
retrieval similarity and generation signals) and a correctness score
(derived from how well the cited sources support each factual claim in
the answer). Scores are surfaced to the user as a coarse badge (e.g.,
High / Medium / Low) and recorded in the audit log as numeric values.
When either score falls below the configured threshold, the system refuses
the answer rather than display a low-confidence response.

**Why this priority**: Grading improves user calibration but the core
product still works without it. It depends on a populated index (US5) and
the eval harness (US6) for threshold tuning.

**Independent Test**: Submit a mix of questions: well-covered topics,
edge topics with thin support, and topics covered by stale or conflicting
sources. Verify the grading badge appears on every answer, the numeric
scores are recorded in the audit log, and below-threshold answers are
refused rather than shown.

**Acceptance Scenarios**:

1. **Given** any generated answer above threshold, **When** it is
   rendered, **Then** a confidence-and-correctness badge is shown next to
   the answer.

2. **Given** any generated answer, **When** the audit record is inspected,
   **Then** the numeric confidence and correctness scores are present.

3. **Given** an answer whose grading falls below threshold, **When**
   delivery is attempted, **Then** the system refuses with an explanation
   instead of rendering the low-quality answer.

---

### Edge Cases

- **Conflicting ATO sources**: When two retrieved ATO chunks give
  inconsistent figures or guidance, the system surfaces both citations and
  notes the conflict rather than picking one silently.
- **Stale cited source**: If a cited URL returns 404 or has changed
  materially since indexing, the system surfaces a "source unavailable"
  warning and refuses to render the previously generated answer.
- **Hallucinated citation**: If the LLM emits a citation URL that does not
  appear in the retrieval result, the answer is rejected at the citation-
  alignment check and a refusal is returned. This is a production-severity
  incident and is logged.
- **Subtle PII**: Partial identifiers (e.g., "John S. with TFN ending 789")
  that fall under the masking heuristic but cannot be safely redacted
  without changing meaning trigger refusal rather than partial masking.
- **Borderline-scope query**: A query about expat or dual-tax situations
  (Australian + foreign) is treated as in-scope only if the cited ATO
  source covers it; otherwise refused with a redirect to a registered tax
  agent.
- **Non-English query**: The MVP supports English only; queries in other
  languages are refused with a clear explanation.
- **Index drift**: If the most recent successful index refresh is older
  than the configured staleness threshold, the system displays a "corpus
  may be out of date" banner.
- **Crawler trap**: Repeating URL patterns, infinite calendars, and
  session-tokened URLs are detected by depth cap, normalized URL
  comparison, and duplicate-content hashing.

## Requirements *(mandatory)*

### Functional Requirements

#### Answering and refusal

- **FR-001**: System MUST require at least one citation to an `ato.gov.au`
  source for every user-facing answer; answers without an aligned citation
  MUST be refused before display.
- **FR-002**: System MUST display a predominant app-level disclaimer at
  session entry, visible before the first query is submitted.
- **FR-003**: System MUST attach a per-answer disclaimer to every rendered
  answer stating the answer is sourced from ato.gov.au and directing the
  user to consult a registered tax agent for personal advice.
- **FR-004**: System MUST NOT provide personal financial, legal, or tax
  advice; answers MUST be limited to factual statements supported by cited
  ATO content.
- **FR-005**: System MUST refuse — with a brief explanation — when no
  retrieved source covers the question, when retrieval confidence is below
  the configured threshold, or when the citation-alignment check fails.
- **FR-006**: System MUST surface source freshness (publication or last-
  modified date) alongside every citation.

#### Input gating (PII, scope, safety)

- **FR-007**: System MUST scan every incoming query for PII covering at
  minimum: full name, email, phone number, date of birth, residential
  address, TFN, ABN.
- **FR-008**: System MUST mask incidental PII tokens before any
  transmission to the language model and MUST refuse when PII is integral
  to the question's meaning.
- **FR-009**: System MUST NOT log, persist, or transmit detected PII in
  plaintext.
- **FR-009a**: When the PII scanner errors, times out, or returns a
  result below the configured confidence threshold, the system MUST
  refuse the query (fail closed) and MUST NOT forward the query to the
  language model. A scanner-fail refusal MUST be logged as a distinct
  refusal reason code for incident review.
- **FR-010**: System MUST classify every incoming query against
  out-of-scope, inappropriate, and personal-advice classes and refuse
  with an explanation when any class triggers.
- **FR-010a**: The refusal classifier MUST be composed of two layers:
  (1) deterministic rules that handle unambiguous cases (e.g., non-
  English text, banned-keyword sets) without invoking a model; and
  (2) a dedicated classifier — separate from the answering language
  model — for boundary cases. The classifier MUST be independently
  versioned, independently testable, and independently regressible
  against the golden evaluation set.
- **FR-011**: System MUST decline non-English queries for v1 with a clear
  explanation.
- **FR-011a**: The chat user interface MUST conform to WCAG 2.2 Level AA
  across every user-facing surface (query input, predominant disclaimer,
  rendered answers and citations, per-answer disclaimer, refusal
  messages, confidence/correctness badge).

#### Retrieval, generation, citation

- **FR-012**: System MUST retrieve candidate chunks only from an index
  built from `www.ato.gov.au` HTML pages; chunks sourced from any other
  domain or content class MUST NOT be retrievable.
- **FR-013**: System MUST verify that every citation in a generated
  answer resolves to a chunk present in the retrieval result for the
  query before rendering the answer (citation-alignment check).
- **FR-014**: System MUST attach a confidence score and a correctness
  score to every generated answer, recorded in the audit log.
- **FR-015**: System MUST refuse to render an answer whose confidence or
  correctness score is below the configured threshold.
- **FR-016**: System MUST surface a coarse confidence-and-correctness
  badge alongside every rendered answer.

#### Audit and provenance

- **FR-017**: System MUST persist for every user-facing turn: original
  user prompt (after PII masking), retrieval query, retrieved chunk IDs,
  model identity and version, generation parameters, rendered answer,
  citations, confidence and correctness scores, refusal reason (if any).
- **FR-018**: Auditors MUST be able to retrieve the full provenance
  (source URL, fetch timestamp, content hash, source last-modified) for
  any chunk in the retrieval index.
- **FR-018a**: Cross-border processing is permitted for v1. The system
  MUST nonetheless: (1) ensure no detected PII is transmitted to any
  third-party service in plaintext, in line with FR-008 and FR-009;
  (2) display, on the predominant app-level disclaimer, a notice that
  some processing may occur outside Australia, in line with Australian
  Privacy Principle 8 (cross-border disclosure of personal information);
  and (3) record the processing region for the LLM, embedding service,
  and observability service in the audit record for every user-facing
  turn (per FR-017). The audit log storage and the retrieval index
  storage SHOULD be located in Australia where the chosen provider
  offers an Australian region, but this is not a hard requirement.

#### Ingestion (crawl and scrape)

- **FR-019**: Crawler MUST produce a machine-readable inventory of leaf-
  level URLs from configured ATO seed pages, recording URL, discovery
  timestamp, crawl depth, HTTP status, and leaf classification.
- **FR-020**: Crawler MUST respect `robots.txt` and a configured polite
  rate limit, and MUST identify itself with a project-specific user agent.
- **FR-021**: Scraper MUST extract main content from each inventory URL,
  chunk it, embed it, and write it to the retrieval index with provenance
  (source URL, fetch timestamp, content hash, source last-modified).
- **FR-022**: Scraper MUST detect and skip duplicate content via content
  hashing and MUST mark superseded chunks when a re-scrape changes content.

#### Evaluation

- **FR-023**: Project MUST publish a golden evaluation set of exactly 30
  question / expected-answer / expected-citation triples under version
  control, covering at minimum: GST, income tax brackets, tax-free
  threshold, deductions, BAS, PAYG, and refusal cases (out-of-scope, PII-
  integral, personal-advice).
- **FR-024**: Evaluation harness MUST run the golden set against the
  assistant and produce a report with per-question verdicts (pass / fail /
  refused) and aggregate metrics for citation correctness, refusal
  correctness, and groundedness.
- **FR-025**: Evaluation harness MUST exit with a non-zero status when any
  configured threshold is missed so it can act as a CI release gate.

### Key Entities *(include if feature involves data)*

- **Query**: The user-submitted question. Carries the original text, the
  PII-masked text used downstream, detected PII classes, session ID, and
  timestamp.
- **Source Document**: An ATO web page snapshot. Carries source URL,
  fetched-at timestamp, source last-modified timestamp, raw content hash,
  and extracted main text.
- **Chunk**: A retrievable unit derived from a Source Document. Carries
  the source-document reference, chunk index, text, embedding vector, and
  is-superseded flag.
- **Retrieval**: The result of a query against the index. Carries the
  query reference, ranked chunk IDs with similarity scores, and a top-k
  cutoff.
- **Answer**: A generated, user-facing response. Carries the response
  text, citations, confidence score, correctness score, per-answer
  disclaimer, generated-at timestamp, model identity and version, and
  refusal reason (if refused).
- **Citation**: A pointer from an Answer to a Chunk and its Source
  Document. Carries source URL, optional anchor, snippet, and source
  last-modified timestamp.
- **Refusal**: A non-answer response. Carries reason code (no-source,
  low-confidence, citation-misalignment, pii-integral, pii-scanner-fail,
  out-of-scope, inappropriate, personal-advice, non-english) and a
  user-facing message.
- **PII Detection Result**: Per-query record of detected PII entities and
  whether masking or refusal was applied. Does NOT carry plaintext PII.
- **URL Inventory Entry**: A row in the crawl inventory. Carries URL,
  discovery timestamp, crawl depth, HTTP status, leaf classification, and
  the configured user-agent.
- **Eval Question**: An item in the golden evaluation set. Carries
  question text, expected outcome (answer-with-citation or refusal-with-
  reason), expected citation URLs, topic tag, and difficulty.
- **Eval Result**: Per-question outcome of a harness run. Carries the
  eval-question reference, actual answer / refusal, citation-correctness
  verdict, refusal-correctness verdict, groundedness verdict, and
  numeric scores.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of user-facing answers carry at least one inline
  citation that resolves to a live `ato.gov.au` URL covered by the
  configured corpus scope.
- **SC-002**: 0% of user-facing answers contain fabricated, hallucinated,
  or non-ATO citations. (Zero tolerance — any occurrence is treated as a
  production-severity incident.)
- **SC-003**: 100% of user-facing answers carry the per-answer disclaimer,
  and the predominant app-level disclaimer is visible to 100% of session
  entries before the first query is submitted.
- **SC-004**: On the golden evaluation set, at least 90% of in-scope
  questions return an answer whose citations correctly support every
  factual claim (groundedness verdict = pass).
- **SC-005**: On the golden evaluation set, at least 95% of out-of-scope,
  PII-integral, inappropriate, and personal-advice questions are refused
  with the correct reason code.
- **SC-006**: 0% of user queries forwarded to the language model contain
  un-masked PII as detected by the PII scanner. (Zero tolerance.)
- **SC-007**: The crawler captures at least 95% of leaf-level URLs in the
  configured ATO scope, measured against a hand-curated audit list of at
  least 50 URLs.
- **SC-008**: The user receives an answer or a refusal within 5 seconds at
  the 50th percentile and within 10 seconds at the 95th percentile of
  measured turns.
- **SC-009**: Every evaluation harness run produces per-question verdicts
  for all 30 questions and an aggregate report with citation correctness,
  refusal correctness, and groundedness metrics.
- **SC-010**: For every chunk in the retrieval index, an auditor can
  retrieve source URL, fetch timestamp, content hash, and source
  last-modified timestamp.
- **SC-011**: An automated accessibility audit of the chat UI reports
  zero WCAG 2.2 Level AA violations across every user-facing surface
  before any non-internal release.

## Clarifications

### Session 2026-06-03

- Q: Which ATO domains and content classes are in-scope for the retrieval
  index? → A: `www.ato.gov.au` HTML pages only. PDF publications,
  `community.ato.gov.au`, and external legislation references on
  `legislation.gov.au` are explicitly out of scope for v1. Expansion to
  additional sources requires a constitution-compatible amendment.
- Q: Where must the retrieval index, audit logs, and language-model
  inference physically reside? → A: Australia only. All processing —
  index storage, audit records, and LLM inference — MUST run in
  Australian data-centre regions. Cross-border processing (including
  fallback regions outside Australia) is prohibited for v1.
- Q: When the PII scanner errors, times out, or returns low confidence,
  how should the system behave? → A: Fail closed. Scanner unavailability
  is treated as an automatic refusal so that no query reaches the LLM
  without a positive scanner verdict.
- Q: What is the accessibility conformance target for the chat UI in v1?
  → A: WCAG 2.2 AA. The chat UI MUST meet WCAG 2.2 Level AA for all
  user-facing surfaces: query input, predominant disclaimer, answer +
  citations + per-answer disclaimer, refusal messages, and confidence
  badge.
- Q: How should out-of-scope, inappropriate, and personal-advice
  refusals be classified? → A: Rules-plus-classifier hybrid.
  Deterministic rules handle unambiguous cases (non-English detection,
  banned-keyword sets); a separate dedicated classifier handles boundary
  cases. The classifier MUST be independently testable and regressible
  against the golden eval set and MUST NOT be the answering LLM.
- Q: Is Australia-only data residency a hard requirement for v1
  (supersedes earlier session answer)? → A: No. AU residency is not a
  hard requirement for v1. The hard rules instead are: (1) PII never
  crosses any boundary in plaintext (the PII guard is the residency
  guarantee); (2) users are notified of cross-border processing per
  Australian Privacy Principle 8; (3) ATO content ingested into the
  index is already public, so its cross-border processing during
  ingestion is acceptable. FR-018a is relaxed accordingly.

## Assumptions

- **Corpus scope**: `www.ato.gov.au` HTML pages only (resolved by
  Clarification, Session 2026-06-03); PDFs, community forum, and external
  legislation sites are out of scope for v1.
- **Language**: English-language input and output only for v1; non-English
  queries are refused.
- **Modality**: Text-only input and output for v1; image upload and
  document upload are out of scope.
- **Session model**: Single-turn Q&A for v1; conversational memory across
  turns is out of scope.
- **Access**: Anonymous, no-login access for v1; identity-based features
  and personalization are out of scope.
- **Deployment**: Internal development preview for v1; public deployment
  is gated on the golden evaluation set meeting the SC-004, SC-005, and
  SC-006 thresholds.
- **Golden set authorship**: The 30 question/expected-answer/expected-
  citation triples are authored by the engineering team using ATO-
  published FAQs and tax-topic indexes as primary references, and are
  reviewed by at least one second reader.
- **PII default behavior**: Tiered — incidental PII is masked and the
  masked query proceeds; PII that is integral to the question's meaning
  triggers refusal with a redirect to ATO direct channels or a registered
  tax agent.
- **Grading display**: Confidence and correctness are surfaced to the
  user as a coarse badge (High / Medium / Low) and persisted as numeric
  values in the audit log.
- **Crawler politeness**: `robots.txt` respected, default rate limit of
  one request per second, project-identifying user agent string.
- **Index refresh cadence**: Nightly incremental re-crawl of changed
  pages using `Last-Modified` and conditional GETs.
- **Disclaimer wording**: Templated and reviewed by the project team
  before launch; final text is captured in design artefacts produced by
  `/speckit.plan`.
- **Refusal phrasing**: Brief, neutral, with a one-sentence reason and,
  where appropriate, a pointer to ATO contact channels or a registered
  tax agent. No partial answers in refusals.
- **Dependency on existing system/service**: Requires read access to the
  public ATO website (`www.ato.gov.au`). No internal ATO systems are in
  scope.
