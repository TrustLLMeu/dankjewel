# Commit index — `feature/d75-v2`

Browsable history for this branch. Git Historian owns this file.
Newest first. `git log` remains the source of truth for hashes.

## Where we are

- **Branch:** `feature/d75-v2`
- **Latest commit:** `1265aba` — Add tiny-judge toggle and dual-track display to the evaluator UI
- **Tree:** dirty (scouting briefs and `omniprov.txt` stay unstaged)
- **Open slices:** pre-existing 390px horizontal overflow on the evaluator page (scrollWidth 485, present before this change; slice 3's 390px check covered /commits); judge latency row for the Phase-4 table; slice 6 Prong 3 extraction waits on Go (Claimify flag)

## Table

| date | short hash | prong / area | subject | review.txt item |
|------|------------|--------------|---------|-----------------|
| 2026-11-14 | `PENDING` | chore / index | Record slice 5 UI land in commit index | chore |
| 2026-11-14 | `1265aba` | dashboard / tiny judge | Add tiny-judge toggle and dual-track display to the evaluator UI | wXze Prong 1 no LLM (UI half) |
| 2026-11-14 | `8cbb11d` | chore / index | Record slice 5 tiny judge land in commit index | chore |
| 2026-11-14 | `86b397d` | chore / ignore | Ignore local crew worktrees and verification screenshots | chore |
| 2026-11-14 | `9013249` | tiny judge / Prong 1 | Add optional tiny-LLM judge track on Prong 1 Relevance (dual output) | wXze Prong 1 no LLM (API half) |
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

### `PENDING` — Record slice 5 UI land in commit index (2026-11-14)

- **Hash:** `PENDING` — a commit cannot record its own hash; backfill in the next index land
- **Why:** Record the slice 5 UI lands.
- **Files:** `docs/commit-index.md`
- **Closes:** chore
- **Verify:** untested (docs only)

### `1265aba` — Add tiny-judge toggle and dual-track display to the evaluator UI (2026-11-14)

- **Hash:** `1265aba3bfaac9695c7870e79cf1e59752269e29`
- **Why:** Slice 5 UI half — the reviewer can now see whether a generative judge ran. Toggle "Tiny LLM judge (Prong 1 Relevance)" in the Paste Text card (default off) sends `tiny_judge` to `POST /evaluate`. Relevance row shows the dual track: baseline stays the main value; scored judge adds model chip (0.5B-Instruct), ms chip, and "judge: x.xxx" tag with rationale+model+ms tooltip; unreachable judge shows grey dashed "judge: unknown" with the connection error in the tooltip; unusable JSON shows muted-red "judge: error". Prong 1 subtitle switches from "embeddings" to "embeddings + tiny-llm (0.5B)" when the judge ran. Captain glue: two-line flex-wrap fix on `.dim-row`/`.dim-tags` so the three chips wrap to a second line instead of clipping in the narrow results column.
- **Files:** `frontend/index.html`, `frontend/locales/en.json`
- **Closes:** UI half of review.txt "Prong 1 does not use an LLM" — the full item is closed (API half landed in 9013249)
- **Verify:** Selenium (headless Chromium) 20/20 checks against three server states (real 0.5B judge, unreachable judge, non-JSON mock judge): toggle unchecked by default; off → no judge tags, subtitle "embeddings"; on → "judge: 1.000" + "0.5B-Instruct" + ms chips, rationale tooltip, subtitle "embeddings + tiny-llm (0.5B)", baseline 0.852 stays the main value; irrelevant answer → "judge: 0.000"; dead judge → grey dashed "judge: unknown" with connection-refused tooltip, baseline intact; non-JSON judge → red "judge: error"; history restore re-renders judge tags; 390px: no overflow regression vs pre-change baseline (both 485 — pre-existing, tracked as open item). pytest 223 passed + 1 skipped (no backend change).

### `8cbb11d` — Record slice 5 tiny judge land in commit index (2026-11-14)

- **Hash:** `8cbb11d03ac72556b72f12eace715261b0ae2703`
- **Why:** Record the slice 5 lands.
- **Files:** `docs/commit-index.md`
- **Closes:** chore
- **Verify:** untested (docs only)

### `86b397d` — Ignore local crew worktrees and verification screenshots (2026-11-14)

- **Hash:** `86b397d4a5984e0649475130e20273d3c9d7be71`
- **Why:** Keep local crew artifacts out of the tree.
- **Files:** `.gitignore`
- **Closes:** chore
- **Verify:** untested (gitignore only)

### `9013249` — Add optional tiny-LLM judge track on Prong 1 Relevance (dual output) (2026-11-14)

- **Hash:** `9013249bf5349c89b39ca7ec2931e21ddbdb754a`
- **Why:** Slice 5 — Prong 1 can now call a real LLM judge (plan Phase 2 / attack order 5). Shared sync client `src/llm_judge_client.py` (httpx, env config `DANKJEWEL_JUDGE_*` defaulting to the local 0.5B server at 127.0.0.1:18092, `[JUDGE]` task prefix, few-shot strict-JSON prompt verified live 2026-11-14, 30 s timeout). Relevance gains a dual-output track: the baseline embedding score stays the aggregated value; the judge adds `llm_value`/`rationale`/`judge_status` (scored|unknown|error) to metadata. `POST /evaluate` accepts `tiny_judge` (default false; off = identical behavior).
- **Files:** `src/api.py`, `src/pipeline.py`, `src/prongs/prong1_dimensions.py`, `src/prongs/prong1_llm_as_judge.py`, `src/llm_judge_client.py`, `tests/test_tiny_judge.py`
- **Closes:** API half of review.txt “Prong 1 does not use an LLM” (UI toggle is the second half)
- **Verify:** pytest 223 passed + 1 skipped (no key) / 224 passed (with key) in the worktree; Captain reran the full suite in the main tree (223+1) and verified live end-to-end via `/evaluate`: default off unchanged (Relevance 0.93, no judge metadata), `tiny_judge=true` dual track (baseline 0.93, llm 1.0, judge 192 ms, rationale “Directly answers the question about the capital of Norway.”), irrelevant answer discriminates (baseline 0.55, llm 0.0). Known 0.5B limitations recorded in client docstring: partial answers anchor to 0; verbatim exemplar repeats echo the exemplar score.

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
