# Commit index — `feature/d75-v2`

Browsable history for this branch. Git Historian owns this file.
Newest first. `git log` remains the source of truth for hashes.

## Where we are

- **Branch:** `feature/d75-v2`
- **Latest commit:** `7ae5801` — Add herdr crew charter and D7.5 v2 plan
- **Index update:** the rows below land one commit after `7ae5801`
- **Tree:** clean
- **Open slices:** slice 1 — measure the current system (Eval); slice 2 — honesty core (Implementer)

## Table

| date | short hash | prong / area | subject | review.txt item |
|------|------------|--------------|---------|-----------------|
| 2026-11-14 | `7ae5801` | chore / crew | Add herdr crew charter and D7.5 v2 plan | chore — slice 0 |
| 2026-11-14 | `df3f47a` | chore / ignore | Ignore local agentic inspiration files | chore |

## Commits

### `7ae5801` — Add herdr crew charter and D7.5 v2 plan (2026-11-14)

- **Hash:** `7ae58011649ae0ff4c7240a35cf22cf6ee0b5f41`
- **Why:** Land the approved crew setup — charter, eight pane briefs, the D7.5 v2 plan, and the first Scout brief — so the herdr has one source of rules.
- **Files:** `.grok/HERDR.md`, `.grok/agents/` (8 briefs), `docs/improvement-plan.md`, `docs/scouting/README.md`, `docs/scouting/2026-11-14-inspiration.md`, `docs/commit-index.md`
- **Closes:** improvement-plan slice 0 (land the charter)
- **Verify:** untested (docs/config only)

### `df3f47a` — Ignore local agentic inspiration files (2026-11-14)

- **Hash:** `df3f47a1eb0a2fac9c2d53c2cb99b239de22b0e9`
- **Why:** `inspiration.txt`, `review.txt`, and `deliverable/` are local agentic inspiration, not product; ignoring them keeps them out of the index.
- **Files:** `.gitignore`
- **Closes:** chore
- **Verify:** `git check-ignore -v inspiration.txt review.txt deliverable/D7_5.tex`
