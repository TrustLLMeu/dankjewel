# Commit index — `feature/d75-v2`

Browsable history for this branch. Git Historian owns this file.
Newest first. `git log` remains the source of truth for hashes.

## Where we are

- **Branch:** `feature/d75-v2`
- **Latest commit:** `38e3731` — Add scored/unknown/error status so missing evidence is not 0.5
- **Tree:** clean after index land
- **Open slices:** slice 3 — instrument panel (Dashboard)

## Table

| date | short hash | prong / area | subject | review.txt item |
|------|------------|--------------|---------|-----------------|
| 2026-11-14 | `38e3731` | honesty | Add scored/unknown/error status so missing evidence is not 0.5 | wXze / V55p unknown≠0.5 |
| 2026-11-14 | `90ab84d` | eval / latency | Refresh /evaluate latency baseline with a second timed run | YE7H |
| 2026-11-14 | `9c1e9a1` | eval / latency | Add /evaluate latency harness and CPU baseline numbers | YE7H / wXze real-time unmeasured |
| 2026-11-14 | `455dee8` | chore / index | Record first two lands in commit index | chore |
| 2026-11-14 | `7ae5801` | chore / crew | Add herdr crew charter and D7.5 v2 plan | chore — slice 0 |
| 2026-11-14 | `df3f47a` | chore / ignore | Ignore local agentic inspiration files | chore |

## Commits

### `38e3731` — Add scored/unknown/error status so missing evidence is not 0.5 (2026-11-14)

- **Hash:** `38e373193b809fb7f5d85217420c438be2fce62c`
- **Why:** Slice 2 — missing evidence must not look like a middling quality score; Prong 1 labelled as embeddings; languages scoped.
- **Files:** `src/base.py`, aggregator, prong 1/3/4 dimensions, `pipeline.py`, `README.md`, `tests/test_honesty_status.py`
- **Closes:** wXze / V55p silent 0.5; Prong 1 naming honesty; nine-language overclaim in README
- **Verify:** `.venv/bin/python -m pytest tests/ -q` → 191 passed

### `9c1e9a1` — Add /evaluate latency harness and CPU baseline numbers (2026-11-14)

- **Hash:** `9c1e9a199604cf491ded411e9f4139f5a25944b5`
- **Why:** Slice 1 — wall-clock numbers for `/evaluate` on the current system, before scoring changes.
- **Files:** `scripts/measure_latency.py`, `evaluation_results/latency_baseline.json`, `evaluation_results/latency_baseline.md`
- **Closes:** YE7H / wXze “real-time is unmeasured” for the `/evaluate` path (not `/generate-and-evaluate`)
- **Verify:** `.venv/bin/python -m pytest tests/ -q` → 172 passed; `.venv/bin/python scripts/measure_latency.py` → HTTP mean 661.7 ms on malvik CPU

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
