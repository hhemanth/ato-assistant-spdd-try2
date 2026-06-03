# ATO Assistant — Agent Guidance

## Project
ATO Assistant: a Retrieval-Augmented Generation (RAG) chat application that
answers user queries about Australian Tax Office (ATO) matters using only
content from `ato.gov.au`, with inline citations.

## Authority
The project Constitution at `.specify/memory/constitution.md` is authoritative.
This file defers to it when in conflict.

## Workflow (Spec Kit)
All feature work flows through:
`/speckit.specify` → `/speckit.clarify` → `/speckit.plan` → `/speckit.tasks` → `/speckit.implement`
Skipping `specify` or `plan` for production features is prohibited.

## Core Principles (summary — see constitution for full text)
1. **Spec-Driven Development** — no code without a ratified spec.
2. **Test-First (NON-NEGOTIABLE)** — Red-Green-Refactor; RAG evaluation harness gates releases.
3. **Clear Naming & Explicit Interfaces** — domain-named symbols; typed, documented interfaces.
4. **Single Responsibility Principle** — retrieval, ranking, generation, citation, state, presentation each live in separate modules.
5. **Grounded Answers with Verifiable Citations (NON-NEGOTIABLE)** —
   every factual claim cites an `ato.gov.au` URL; refuse rather than speculate.

## Hard Rules for Agents
- Never fabricate or paraphrase tax guidance without a retrieved ATO source.
- Never cite non-ATO sources as authoritative.
- Never log TFN/ABN/PII in plaintext; never send PII to third-party tooling.
- Refuse out-of-scope, personalized-advice, or low-confidence queries explicitly.
- Surface source freshness (publication / last-modified date) with every citation.

## Branching & Reviews
- Feature branches named `###-short-slug` per `speckit-git-feature`.
- PRs require: green unit/integration tests, green RAG eval harness for any
  change touching retrieval/generation/citation, one human reviewer, and a
  Constitution Check.

## Definition of Done
Tests written and passing → acceptance scenarios pass → interface/docs updated →
evaluation harness regression is zero (or justified) → merged via reviewed PR.
