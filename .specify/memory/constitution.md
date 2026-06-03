<!--
SYNC IMPACT REPORT
==================
Version change: TEMPLATE (uninitialized) → 1.0.0
Bump rationale: Initial ratification of the project constitution. No prior
version existed; all placeholder tokens in the template have been resolved.

Principles defined:
  I.   Spec-Driven Development
  II.  Test-First Development (NON-NEGOTIABLE)
  III. Clear Naming & Explicit Interfaces
  IV.  Single Responsibility Principle
  V.   Grounded Answers with Verifiable Citations (NON-NEGOTIABLE)

Added sections:
  - Core Principles (5 principles)
  - Additional Constraints (RAG Pipeline & Domain)
  - Development Workflow & Quality Gates
  - Governance

Removed sections: none (initial ratification)
Renamed principles: none (initial ratification)

Templates reviewed:
  ✅ .specify/templates/plan-template.md       — Constitution Check section uses a
                                                  placeholder ("[Gates determined based on
                                                  constitution file]") that is resolved at
                                                  plan-generation time; no edit required now.
  ✅ .specify/templates/spec-template.md       — Aligned (implementation-free, user-story
                                                  driven, includes measurable success criteria).
  ✅ .specify/templates/tasks-template.md      — Aligned (test-first ordering already encoded
                                                  under "Within Each User Story").
  ✅ .specify/templates/checklist-template.md  — Generic; no constitution-specific edit needed.
  N/A .specify/templates/commands/             — Directory does not exist in this project.
  ⚠  README.md / docs/quickstart.md            — Not present in repo yet. When authored, they
                                                  MUST link to this constitution and surface
                                                  Principle V (Grounded Answers with Citations).

Follow-up TODOs:
  - When README.md or docs/quickstart.md are authored, add a constitution reference.
  - When agent-context files are (re)generated via /speckit.agent-context.update,
    confirm they reference Principles II and V.
-->

# ATO Assistant Constitution

## Core Principles

### I. Spec-Driven Development

Every feature MUST begin life as a written specification at `specs/<###-feature>/spec.md`
before any production code is written. Specifications MUST capture user scenarios, functional
requirements, key entities, and measurable success criteria; they MUST remain free of
implementation detail (no language, framework, library, vendor, or model names in `spec.md`
itself — those belong in `plan.md`). Every artifact produced downstream (plan, tasks, code,
tests) MUST trace back to a specific requirement ID in the spec. Code that does not map to a
ratified spec MUST NOT be merged.

**Rationale**: Tax-domain features carry real legal and financial consequences for users.
Forcing a written, reviewed specification before code aligns the team on *what* is being
delivered and *why* before debating *how*, and creates the audit trail that domain reviewers
and regulators expect.

### II. Test-First Development (NON-NEGOTIABLE)

Tests MUST be written before the implementation they cover. The Red-Green-Refactor cycle is
mandatory: a failing test (Red) MUST be observed before implementing code (Green); refactoring
MUST be performed only against a green suite. Every user story listed in `tasks.md` MUST have
at least one independently-failing test task scheduled before its implementation tasks.
Pull requests that add behavior without an accompanying test that was first observed to fail
MUST be rejected in review.

In addition to standard unit and integration tests, the RAG pipeline MUST be covered by an
automated **answer-quality evaluation harness** measuring at minimum: retrieval recall against
a labeled gold set, citation correctness (every cited URL resolves and supports the claim),
refusal correctness (out-of-scope and low-confidence questions are refused), and PII handling.
This harness MUST run in CI and MUST gate releases.

**Rationale**: Tests-first prevents regressions, documents intent, and — uniquely for a RAG
system — catches accuracy and citation regressions that unit tests cannot detect. Without an
automated answer-quality harness, silent quality decay is the default state.

### III. Clear Naming & Explicit Interfaces

Every public symbol (module, class, function, type, REST/RPC endpoint, CLI flag, event name,
configuration key) MUST be named after the concept it represents in the domain, not after its
implementation. Abbreviations MUST be avoided except for well-known domain terms
(e.g., `ATO`, `TFN`, `ABN`, `BAS`, `GST`, `PAYG`). Every module MUST expose a typed, documented
interface; cross-module callers MUST depend on the interface, not on internal symbols.
Interface changes MUST be versioned and recorded in a changelog.

**Rationale**: Tax-domain code is read by domain experts as well as engineers. Names that map
to domain concepts shorten the path from spec to code review to audit. Explicit, typed
interfaces let RAG components (retriever, reranker, generator, citation extractor) be replaced
independently as the stack evolves.

### IV. Single Responsibility Principle

Every module, class, and function MUST have exactly one reason to change. The RAG pipeline
stages — ingestion, chunking, embedding, indexing, retrieval, ranking, generation, citation
extraction, conversation state, and presentation — MUST each live in a separate module behind
a clear interface (see Principle III). A helper that grows a second responsibility MUST be
split; a class that accumulates unrelated state MUST be decomposed. Any unit whose purpose
cannot be described in a single sentence without the word "and" MUST be refactored before merge.

**Rationale**: SRP keeps the pipeline composable. Swapping an embedding model, a reranker, or
an LLM provider should touch one module, not ripple across the system. Single-responsibility
units are also the smallest meaningful target for the evaluation harness.

### V. Grounded Answers with Verifiable Citations (NON-NEGOTIABLE)

Every answer returned to a user MUST be grounded in retrieved content from the official ATO
website (`ato.gov.au` and its sanctioned subdomains only). Every factual claim in an answer
MUST carry an inline citation that resolves to the exact ATO source URL, including a section
anchor or fragment when the source supports it. When no retrieved source covers a question —
or when retrieval confidence is below the configured threshold — the system MUST refuse to
answer and MUST tell the user it cannot find an authoritative source, rather than speculate,
infer, or generalize from training data.

The system MUST NOT cite, paraphrase, or rely on any non-ATO source as authoritative. Source
freshness (publication or last-updated date) MUST be surfaced alongside every citation so the
user can judge currency. Hallucinated, fabricated, or mis-attributed citations are treated as
production-severity incidents.

**Rationale**: The product's entire value is *accurate tax guidance backed by the authoritative
source*. Ungrounded or mis-cited answers are not defects — they cause real financial and legal
harm to users. This principle is non-negotiable and overrides convenience, latency, model-choice,
or coverage trade-offs.

## Additional Constraints (RAG Pipeline & Domain)

**Source authority**: The retrieval index MUST be built exclusively from ATO official content.
Ingestion MUST record, per chunk: source URL, fetch timestamp, content hash, and source
last-modified timestamp. Chunks older than the configured re-crawl window MUST be flagged in
evaluation reports and re-fetched.

**Provenance & audit**: Every user-facing answer MUST be persisted with the exact user prompt,
retrieval query, retrieved chunk IDs, model name and version, generation parameters, and the
rendered citations. This audit record MUST be queryable for incident review and MUST be
retained per the data retention policy defined in the spec.

**Privacy & PII handling**: Taxpayer-identifying information (TFN, ABN, full name, date of
birth, address, contact details) entered by a user MUST NOT be logged in plaintext, MUST NOT
be transmitted to third-party evaluation or analytics tooling, and MUST NOT be ingested into
the retrieval index. PII handling MUST comply with the Australian Privacy Principles (APPs).

**Refusal behavior**: The system MUST refuse — clearly, without fabrication, and without
caveats that read as partial answers — when (a) the question is out of the ATO domain,
(b) retrieval confidence is below threshold, or (c) the question requires personalized
legal/financial advice that a registered tax agent must give. Refusals MUST suggest where the
user can find authoritative help.

**Model & retrieval transparency**: Production deployments MUST expose a `system-info`
endpoint (or equivalent) reporting model name, model version, retrieval index version, and
last index-refresh timestamp, to support reproducibility and incident response.

## Development Workflow & Quality Gates

**Workflow**: Feature work MUST flow through the Spec Kit lifecycle in order:
`specify → clarify → plan → tasks → implement`. Skipping `specify` or `plan` for production
features is prohibited. Each step's output is the gate for the next.

**Branching**: Feature work MUST happen on feature branches named per the
`speckit-git-feature` convention (`###-short-slug`). Direct commits to `main` are prohibited
except for documentation-only changes and constitution amendments.

**Code review**: Every pull request MUST be reviewed by at least one human reviewer and MUST
pass: (a) the unit and integration test suite, (b) the RAG answer-quality evaluation harness
for any change touching ingestion, retrieval, generation, or citation, and (c) a Constitution
Check confirming the change violates no principle. Reviewers MUST explicitly verify Principle V
for any change that can affect the user-facing answer path.

**Definition of done**: A task is "done" only when (1) its tests were written, observed to
fail, and now pass; (2) its acceptance scenarios pass; (3) its documentation and interface
contracts are updated; (4) the evaluation harness shows zero regression — or any regression is
explicitly justified and approved; and (5) the change is merged via a reviewed pull request.

## Governance

This constitution supersedes all other engineering practices, conventions, and informal
agreements within the project. When a project document, README, agent-context file, or
informal convention conflicts with this constitution, the constitution wins.

**Amendments**: Amendments MUST be proposed via a pull request that (a) updates this file,
(b) updates the Sync Impact Report at the top of this file, and (c) bumps the version per the
policy below. Amendments MUST be approved by the project maintainers and MUST include a
migration plan if they invalidate or supersede existing artifacts.

**Versioning policy**:

- **MAJOR** — backward-incompatible governance changes, principle removals, or redefinition of
  a NON-NEGOTIABLE principle in a way that changes its enforcement.
- **MINOR** — addition of a new principle or section, or material expansion of existing
  guidance.
- **PATCH** — clarifications, typo fixes, and wording refinements that do not change meaning.

**Compliance reviews**: Every plan produced by `/speckit.plan` MUST include a Constitution
Check section that enumerates each principle and explains how the plan complies. Any violation
MUST be recorded in the plan's Complexity Tracking section with explicit justification and an
analysis of why a simpler, principle-compliant alternative was rejected.

**Runtime guidance**: Day-to-day agent behavior MUST follow `CLAUDE.md` and any other
agent-specific guidance files. Those files MUST defer to this constitution when in conflict.

**Version**: 1.0.0 | **Ratified**: 2026-06-03 | **Last Amended**: 2026-06-03
