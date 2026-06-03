# ATO Assistant

A Retrieval-Augmented Generation (RAG) chat application that answers user
queries about Australian Tax Office (ATO) matters using **only** content
from `ato.gov.au`, with inline citations to the exact source.

> **Status**: Pre-implementation. The project constitution is ratified
> ([v1.0.0](./.specify/memory/constitution.md)); no feature specs or
> source code exist yet. Use `/speckit.specify` to start the first feature.

## What this product is — and isn't

**Is**: a question-answering assistant grounded in official ATO publications,
with every factual claim backed by a verifiable citation.

**Isn't**: a tax-advice service. The assistant refuses personalized
legal/financial advice and directs users to a registered tax agent for
those questions.

## The defining rule

Per [Principle V](./.specify/memory/constitution.md) of the constitution
(**NON-NEGOTIABLE**):

> Every answer returned to a user MUST be grounded in retrieved content
> from `ato.gov.au` and its sanctioned subdomains. Every factual claim MUST
> carry an inline citation that resolves to the exact ATO source URL. When
> no retrieved source covers a question — or retrieval confidence is below
> the configured threshold — the system MUST refuse to answer rather than
> speculate.

Hallucinated, fabricated, or mis-attributed citations are production-severity
incidents. This rule overrides convenience, latency, model-choice, and
coverage trade-offs.

## Governance

The [project constitution](./.specify/memory/constitution.md) is
authoritative for all engineering decisions. Day-to-day agent guidance lives
in [`CLAUDE.md`](./CLAUDE.md) and defers to the constitution where they conflict.

### Core principles (summary)

1. **Spec-Driven Development** — no production code without a ratified spec.
2. **Test-First Development** (NON-NEGOTIABLE) — Red-Green-Refactor plus an
   automated RAG answer-quality evaluation harness gating CI.
3. **Clear Naming & Explicit Interfaces** — domain-named symbols; typed,
   documented interfaces between every RAG stage.
4. **Single Responsibility Principle** — ingestion, retrieval, ranking,
   generation, citation extraction, conversation state, and presentation
   each live in separate modules.
5. **Grounded Answers with Verifiable Citations** (NON-NEGOTIABLE) — see above.

Full text, additional RAG/domain constraints (PII handling, provenance,
refusal behavior), and the amendment process are in the
[constitution](./.specify/memory/constitution.md).

## Workflow

All feature work flows through [Spec Kit](https://github.com/github/spec-kit):

```
/speckit.specify  →  /speckit.clarify  →  /speckit.plan  →  /speckit.tasks  →  /speckit.implement
```

Skipping `specify` or `plan` for production features is prohibited.
Features live on branches named `###-short-slug` (created by
`speckit-git-feature`); direct commits to `main` are prohibited except for
documentation-only changes and constitution amendments.

## Repository layout

```
.specify/
  memory/constitution.md       # Authoritative project rules
  templates/                   # Spec / plan / tasks / checklist templates
  extensions/                  # git + agent-context extensions
  workflows/                   # Spec Kit workflow definitions
.claude/
  skills/                      # Speckit slash-command skills
CLAUDE.md                      # Agent runtime guidance (defers to constitution)
README.md                      # This file
specs/                         # Created per-feature once /speckit.specify runs
```

## Contributing

1. Read the [constitution](./.specify/memory/constitution.md) end-to-end
   before opening a pull request.
2. Run `/speckit.specify "<feature description>"` to start a new feature
   — this creates the branch and the spec scaffold.
3. Every pull request requires: green unit/integration tests, a green RAG
   evaluation harness run for any change touching retrieval/generation/citation,
   one human reviewer, and a Constitution Check section in the plan.
