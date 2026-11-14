# Commit index — `feature/d75-v2`

Browsable history for this branch. Git Historian owns this file.
Newest first. `git log` remains the source of truth for hashes.

## Where we are

- **Branch:** `feature/d75-v2`
- **Latest commit:** `37fa6e4` — Add a browsable commit history page at /commits
- **Tree:** dirty (scouting briefs and `omniprov.txt` stay unstaged)
- **Open slices:** slice 5 tiny 0.5B judge; slice 6 Prong 3 extraction waits on Go (Claimify flag)

## Table

| date | short hash | prong / area | subject | review.txt item |
|------|------------|--------------|---------|-----------------|
| 2026-11-14 | `37fa6e4` | dashboard | Add a browsable commit history page at /commits | YE7H / wXze history in the UI |
| 2026-11-14 | `0e1be7d` | chore / index | Complete slice 3 entries in the commit index | chore |
| 2026-11-14 | `28d2464` | dashboard | Show Equal as the active weight preset on load | wXze weights / active preset |
| 2026-11-14 | `873d651` | chore / index | Record slice 3 instrument panel in commit index | chore |
| 2026-11-14 | `7129c89` | dashboard | Add instrument panel: unknown marks, weight presets, radar | wXze / YE7H panel, unknown≠0.5 |
| 2026-11-14 | `e2935f0` | chore / index | Record slice 2 honesty land in commit index | chore |
| 2026-11-14 | `38e3731` | honesty | Add scored/unknown/error status so missing evidence is not 0.5 | wXze / V55p unknown≠0.5 |
| 2026-11-14 | `90ab84d` | eval / latency | Refresh /evaluate latency baseline with a second timed run | YE7H |
| 2026-11-14 | `0214efd` | chore / index | Record slice 1 latency land in commit index | chore |
| 2026-11-14 | `9c1e9a1` | eval / latency | Add /evaluate latency harness and CPU baseline numbers | YE7H / wXze real-time unmeasured |
| 2026-11-14 | `455dee8` | chore / index | Record first two lands in commit index | chore |
| 2026-11-14 | `7ae5801` | chore / crew | Add herdr crew charter and D7.5 v2 plan | chore — slice 0 |
| 2026-11-14 | `df3f47a` | chore / ignore | Ignore local agentic inspiration files | chore |

## Commits

### `37fa6e4` — Add a browsable commit history page at /commits (2026-11-14)

- **Hash:** `37fa6e4922d292c77f3e6de4d62e7b9fc20490b0`
- **Why:** Slice 4 extra — a human can browse `feature/d75-v2` without `git log`. Git Historian wrote the page and routes; the named pane dropped before committing, so Captain landed them.
- **Files:** `frontend/commits.html`, `frontend/index.html`, `src/api.py`
- **Closes:** browsable history (`docs/commit-index.md` plus `/commits`)
- **Verify:** TestClient GET `/commits` 200, GET `/api/commits` 200 branch `feature/d75-v2` 12 commits; Selenium: header link, honesty chip, empty search, expand, Evaluator back-link, 390px no horizontal overflow

### `0e1be7d` — Complete slice 3 entries in the commit index (2026-11-14)

- **Hash:** `0e1be7d4d9024ffe294bb3fe41d8ef263fb7b9c5`
- **Why:** The previous index land only rewrote the Latest line. Record the instrument-panel commit, the active-preset glue, and the missing slice 1–2 index rows.
- **Files:** `docs/commit-index.md`
- **Closes:** chore
- **Verify:** untested (docs only)

### `28d2464` — Show Equal as the active weight preset on load (2026-11-14)

- **Hash:** `28d2464c837ef951f9118bfaaa8a8a391b1be07a`
- **Why:** Slice 3 glue — the Equal button was highlighted, but the “Active: …” line was empty until a click. Plan requires the panel to show which preset is active.
- **Files:** `frontend/index.html`
- **Closes:** missing active-preset label on first paint
- **Verify:** Chromium evaluate-only; label reads “Active: Equal” on load, “Active: Factual QA” after click; gauge 0.822 → 0.847

### `7129c89` — Add instrument panel: unknown marks, weight presets, radar (2026-11-14)

- **Hash:** `7129c8965142aeb0324df720cdbc1f6ec22a7146`
- **Why:** Slice 3 — D7.5 visualisation plus honesty flags from slice 2. Unknown/error is grey dashed, not a green 0.5. Four named weight presets re-aggregate client-side. SVG radar of scored prongs (P1–P3 when Prong 4 has no logprobs).
- **Files:** `frontend/index.html`, `frontend/locales/*.json`
- **Closes:** wXze / YE7H instrument panel; unknown≠0.5 in the UI; unlabelled weights
- **Verify:** Chromium evaluate-only (desktop and 390px): paste “The capital of France is Paris…”; Partial coverage; Prong 4 Unknown; embeddings subtitle; empty-paste alert; radar labels P1/P2/P3

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
