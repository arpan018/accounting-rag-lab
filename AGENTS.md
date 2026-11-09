# Project instructions

This file is the entry point for Codex and other agents working in this repository. Follow the owner's latest instructions, then consult the project sources below before planning or changing files.

## Read these sources of truth

1. `.work/rag-prechecks_finance.md` — project requirements, scope, environment assumptions, money precision, data safety, and review ownership.
2. `.work/codex-planning-prompt.md` — planning and implementation workflow and approval boundaries.
3. `.work/project-plan.md` — current architecture, phases, evaluation criteria, and known risks.
4. `.work/task-board.md` — task order, dependencies, acceptance evidence, and status.
5. `.work/decisions.md` — confirmed requirements, recommendations, and unresolved decisions.
6. `.work/progress.md` — inspected inputs, observed environment, completed work, and next steps.

If documents appear inconsistent, preserve the requirements in `rag-prechecks_finance.md`, follow the workflow in `codex-planning-prompt.md`, and obey the owner's latest instruction. Update the task board and progress log when work changes a task's status or establishes a relevant fact.

## Work one task at a time

- Take the next not-started task in `.work/task-board.md`; do not silently skip ahead or bundle later tasks.
- Finish that task's stated acceptance evidence, then update the task board and progress log.
- Report what changed, which files changed, what checks actually ran, any limitations, and the next task. Pause for the owner's direction before starting another task.
- Keep explanations plain and suitable for someone learning Python. Prefer small, runnable milestones and reusable code in `src/`; use notebooks for inspection and learning.

## Project guardrails

- Keep v1 local and within the approved invoice/PO/GR scope. OCR, agents, web services, Docker, frontend, deployment, pgvector, production integrations, and tax rules are out of scope unless the owner separately approves a change.
- Do not add dependencies, download or copy datasets, use hosted or paid models, publish files, install system-wide software, or change system settings without the required owner approval. Never alter global Python; use the project virtual environment.
- Keep source/private documents, secrets, local indexes, embeddings, and unreviewed derived data out of Git. Do not put sensitive source text in evaluation results.
- Use `Decimal` constructed from source strings for all monetary parsing, comparison, arithmetic, tolerances, and expected values. Never use binary float for money. Preserve source text and normalized values; make currency and rounding explicit.
- Treat model-extracted fields as untrusted candidates. The owner verifies ground truth and business meaning; deterministic code checks arithmetic; humans review ambiguous, missing, conflicting, material, or low-confidence cases. Confidence is not correctness.
- Do not claim real-corpus accuracy without owner-verified labels. Distinguish synthetic checks from real-corpus evaluation and report only checks that actually ran.
- The reference `invoice-agent` project was used only in a temporary environment to generate the synthetic corpus. Keep its source credit and raw dataset, but do not import its application code, extraction/matching policy, thresholds, labels, or published evaluation results as this project's implementation or baseline. Build and evaluate this project's pipeline independently.
