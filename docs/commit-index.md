# Commit index — `feature/d75-v2`

Browsable history for this branch. Git Historian owns this file.
Newest first. `git log` remains the source of truth for hashes.

## Where we are

- **Branch:** `feature/d75-v2`
- **Latest commit:** `8adab97` — Wrap the header on narrow viewports (fix 390px overflow)
- **Tree:** dirty (scouting briefs and `omniprov.txt` stay unstaged)
- **Open slices:** judge/verifier latency rows for the Phase-4 table; seed coverage still 0.3% on FEVER; slice 6b follow-ups (AVeriTeC/LLM-AggreFact second benchmark, Nordic seed, partially_supported reachable mainly via the authored eval)

## Table

| date | short hash | prong / area | subject | review.txt item |
|------|------------|--------------|---------|-----------------|
| 2026-11-14 | `PENDING` | chore / index | Record 390px header fix in commit index | chore |
| 2026-11-14 | `8adab97` | dashboard / responsive | Wrap the header on narrow viewports (fix 390px overflow) | chore / honesty (measured claims) |
| 2026-11-14 | `906c099` | chore / index | Record slice 6c qualifier gates in commit index | chore |
| 2026-11-14 | `7fd15b9` | prong 3 / tests+docs | Pin qualifier-gate abstentions and document seed pruning | wXze coverage robustness (qualifier gates) |
| 2026-11-14 | `5204f67` | chore / index | Record herdr dispatch rule in commit index | chore |
| 2026-11-14 | `d0a9fb0` | chore / crew | Dispatch crew work through herdr panes, not subagents | chore |
| 2026-11-14 | `f869ba6` | chore / index | Record slice 6b verifier land in commit index | chore |
| 2026-11-14 | `af6339a` | prong 3 / verifier | Add MiniCheck verifier, five-way Prong 3 relations, and seed expansion | wXze+V55p Prong 3 discriminative signal (five-way + verifier track) |
| 2026-11-14 | `fe29386` | chore / index | Record slice 6a LLM claim extraction in commit index | chore |
| 2026-11-14 | `a5dbb8d` | prong 3 / extraction | Add optional LLM atomic-claim extraction track for Prong 3 (dual output) | wXze coverage <10% (extraction recall) |
| 2026-11-14 | `c71b57d` | chore / index | Record slice 5 UI land in commit index | chore |
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

### `PENDING` — Record 390px header fix in commit index (2026-11-14)

- **Hash:** `PENDING` — a commit cannot record its own hash; backfill in the next index land
- **Why:** Record the 390px header fix land.
- **Files:** `docs/commit-index.md`
- **Closes:** chore
- **Verify:** untested (docs only)

### `8adab97` — Wrap the header on narrow viewports (fix 390px overflow) (2026-11-14)

- **Hash:** `8adab973938f82cd67daa5bdc537d0ff4ceddf58`
- **Why:** The header was a single non-wrapping flex row (title, status, Commits, language select, model badge); at a true 390px viewport the select and badge pushed document scrollWidth to 485 (110px overflow), before and after an evaluation. A <=640px media query now lets the header wrap (two rows), hides the desktop spacer, and right-aligns the language select. Nothing below the header overflowed. Correction worth recording: earlier "390px" Selenium runs used --window-size, which headless Chrome clamps to a 500px minimum, so the reported 485px scrollWidth was first misread as a page-layout defect; the true measurement uses CDP `Emulation.setDeviceMetricsOverride` at 390.
- **Files:** `frontend/index.html`
- **Closes:** the open "pre-existing 390px evaluator overflow" item
- **Verify:** Selenium with true CDP emulation — 390px: overflow 0 on load AND after a real evaluate-only run with the text card open (4 prongs rendered, no error); breakpoints 500/639/641/700/1280 all overflow 0; header height 84px below 640 (two rows) and 53px at/above 640 (single row); desktop 1280 unchanged (the added CSS is scoped to max-width:640px, so >640px rendering is structurally unaffected); pytest 320 passed + 2 skipped (no backend change).

### `906c099` — Record slice 6c qualifier gates in commit index (2026-11-14)

- **Hash:** `906c099521a3798abdeb115de6626ab892685b6c`
- **Why:** Record the slice 6c qualifier-gate land.
- **Files:** `docs/commit-index.md`
- **Closes:** chore
- **Verify:** untested (docs only)

### `7fd15b9` — Pin qualifier-gate abstentions and document seed pruning (2026-11-14)

- **Hash:** `7fd15b9cf3bd3fad34c5743f9e9ad98c50c11960`
- **Why:** Slice 6c — the two follow-ups the 6b reviewer authorised (no verifier or UI work). The qualifier gate in `src/resources/wikidata_offline.py` previously had no regression coverage: 13 new tests pin that role ("directed by X" with absent/contradicted director data), ordinal-series ("the third James Bond film") and temporal ("before 1990") qualifiers abstain or deny and never confirm through a weak fuzzy match; every UNKNOWN pin is paired with a control proving the same claim would confirm without the qualifier (non-vacuous). No gate fix was needed. `scripts/extend_wikidata_db.py` gains `--prune-label-only` with module-docstring documentation of which label-only rows survive (cited via P17/P131/P30/P36/P1376/P361), why the rest are pruned (227 label-only values fetched, no claims = no verification value), and the reproduction recipe for the 122-entity seed (start from the 86-entity seed, --entities list, --prune-label-only).
- **Files:** `scripts/extend_wikidata_db.py`, `tests/test_five_way.py`
- **Closes:** the 6b reviewer's blocker (unreproducible seed pruning) and should-fix (gate regression tests). Contradicted directors deny (slice 6b design: deny on explicit contradiction, abstain without data)
- **Verify:** implementer pytest 320 passed + 2 skipped in the worktree; Captain reran the full suite in the main tree (320 + 2 skipped, pre-existing live-model skips). Historian reran `tests/test_five_way.py` before committing: 49 passed. No UI or runtime scoring change.

### `5204f67` — Record herdr dispatch rule in commit index (2026-11-14)

- **Hash:** `5204f67b0da4957a8a634e8c023d5aeb1d9e989c`
- **Why:** Record the herdr dispatch rule land.
- **Files:** `docs/commit-index.md`
- **Closes:** chore
- **Verify:** untested (docs only)

### `d0a9fb0` — Dispatch crew work through herdr panes, not subagents (2026-11-14)

- **Hash:** `d0a9fb098130738b9616c9dfa8eeb300a736fd73`
- **Why:** The user follows the work in the herdr tabs; in-session subagents hide it. The charter now names the panes, the brief-file + `herdr agent prompt` pattern, the status-polling rule (`herdr agent get` / `agent read --source visible`; `prompt --wait` often times out), and the tab-focus restore. No model or rate-window change.
- **Files:** `.grok/HERDR.md`
- **Closes:** chore / crew process
- **Verify:** untested (docs only); `herdr agent prompt dj-reviewer` + status polling used for the slice 6b review this same day

### `f869ba6` — Record slice 6b verifier land in commit index (2026-11-14)

- **Hash:** `f869ba6bb71d53ee521d90dac39467b28ecdccbb`
- **Why:** Record the slice 6b land.
- **Files:** `docs/commit-index.md`
- **Closes:** chore
- **Verify:** untested (docs only)

### `af6339a` — Add MiniCheck verifier, five-way Prong 3 relations, and seed expansion (2026-11-14)

- **Hash:** `af6339a7b235ef81758bd9723507dc7b1631a668`
- **Why:** Slice 6b, per the claim-extraction scout re-rank. MiniCheck-Flan-T5-Large (770M, CPU, ~0.2 s/claim warm) implemented with the official protocol (input "predict: doc</s>claim", logits [3,209], softmax) via `transformers` — the PyPI `minicheck` name is a different project, so no pip dependency was added. Opt-in `llm_verify` flag (default false) + third UI toggle: final-UNKNOWN claims with a resolvable subject are scored against the subject's formatted seed-KB facts; p>=0.8 confirmed, p<=0.2 denied, else partially_supported. VerificationResult gains PARTIALLY_SUPPORTED + CONFLATED; a deterministic conflation rule (object resolves to a KB entity that is a valid value of the same property for another subject, while the subject's own value differs) fires on final-UNKNOWN only; binary value math unchanged, relation_counts/claim relation added as the upgraded metadata track. Seed DB 86 -> 122 entities (+36: Bergen, Trondheim, Iceland, Reykjavik, NTNU alias, SINTEF, EU, claims-bearing Europe/South America; label-only rows pruned to the location/identity whitelist). `scripts/extend_wikidata_db.py` gains `--entities`; `scripts/eval_verifier.py` + `data/verifier_eval.json` (authored PoC pairs) give the verifier evidence.
- **Files:** `.gitignore`, `README.md`, `docs/improvement-plan.md`, `data/wikidata_seed.db`, `data/verifier_eval.json`, `src/resources/nli_verifier.py`, `src/resources/wikidata_offline.py`, `src/dimensions/prong3_dimensions.py`, `src/prongs/prong3_extraction.py`, `src/pipeline.py`, `src/api.py`, `src/config.py`, `scripts/extend_wikidata_db.py`, `scripts/eval_verifier.py`, `frontend/index.html`, `frontend/locales/en.json`, `tests/test_nli_verifier.py`, `tests/test_five_way.py`
- **Closes:** the "Prong 3 carries no discriminative signal" half of V55p/wXze on covered claims (five-way labels + verifier track; binary AUC stays comparable) — NOT the coverage item (FEVER seed coverage remains 0.3%) and not the public-benchmark item (verifier pairs are PoC-authored)
- **Verify:** implementer pytest 307 passed + 2 skipped (no key) / 309 (with key); Captain reran the suite in the main tree (307+2) and Selenium 10/10: third toggle default off; real evaluation "Oslo is the capital of Norway. Trondheim is the capital of Hordaland." -> conflated chip (purple #ede9fe) + summary "1 of 2 claims covered · confirmed 1 / denied 0 / partial 0 / conflated 1 / unknown 0"; "Oslo is a city with about 700,000 inhabitants." -> verifier off: unknown, verifier on: denied (end-to-end flag wiring); partially_supported chip/tooltip via the app's renderer (amber #fef3c7; rare through the pipeline because decomposition + exact KB matching route most claims to confirmed/denied first); 390px no overflow regression (485=485 vs c71b57d). Verifier eval (25 pairs): five-way accuracy 0.760; binary AUC 0.906 (n=8/12, partials excluded); 12/12 refuted; 550 ms/pair mean. FEVER 30/class after expansion: spacy and dual both still 0/90 coverage, AUC 0.500. README honesty fix: the stale seed row (9.0%/0.494/0.500) predated the qualifier gate; full 1,174-claim rerun on BOTH the expanded 122-entity and pristine 86-entity DBs gives identical 4/1174 (0.3%) covered, AUC 0.497 — README now reads "~122 entities — a small seed, not Wikidata".

### `fe29386` — Record slice 6a LLM claim extraction in commit index (2026-11-14)

- **Hash:** `fe29386223cf47319421533ac34d40d997fd3398`
- **Why:** Record the slice 6a land and the FEVER dataset deviation (public FEVER 2.0 fixers set unavailable; the harness uses the official FEVER 1.0 shared-task dev set).
- **Files:** `docs/commit-index.md`
- **Closes:** chore
- **Verify:** untested (docs only)

### `a5dbb8d` — Add optional LLM atomic-claim extraction track for Prong 3 (dual output) (2026-11-14)

- **Hash:** `a5dbb8dc01ad5c27bdf91bd7cdc4a77ba132b6de`
- **Why:** Slice 6a, per the claim-extraction scout re-rank (Claimify/FActScore mechanism, MPropositionneur pattern). The 0.5B judge failed claim extraction (verbatim echo, no pronoun resolution, one hallucinated negation), so the `[CLAIMS]` task runs on a new local 1.5B server (127.0.0.1:18093, Qwen2.5-1.5B-Instruct, same `DANKJEWEL_JUDGE_API_KEY`); `[JUDGE]` stays on the 0.5B. `src/extraction/llm_claim_extractor.py` makes one `[CLAIMS]` call per paragraph, re-runs the existing spaCy triple logic on each decontextualized atomic claim (MPropositionneur), merges the tracks, and dedups identical triples to `source="both"`. Claims gain backward-compatible `source`/`atomic_text`; `ExtractionResult` gains `metadata` (`llm_paragraphs`/`llm_claims`/`llm_errors`). The client gains a `[CLAIMS]` task with JSON repair for the 1.5B's dropped commas. Opt-in `llm_extract` flag on `/evaluate` (default false = identical behavior) plus a UI toggle, per-claim Source column chips (spacy/llm/both), and a dual-count summary line. `eval_fever2.py` gains `--extractor {spacy,llm,dual}`.
- **Files:** `src/llm_judge_client.py`, `src/extraction/claim_extractor.py`, `src/extraction/llm_claim_extractor.py`, `src/prongs/prong3_extraction.py`, `src/pipeline.py`, `src/api.py`, `frontend/index.html`, `frontend/locales/en.json`, `scripts/eval_fever2.py`, `tests/test_llm_claim_extractor.py`
- **Closes:** the extraction-recall half of review.txt wXze coverage <10% (recall is the bottleneck) and the paraphrased/embedded-fact spaCy gap — NOT the coverage/AUC items themselves (the verifier is KB-bound; see Verify)
- **Verify:** implementer pytest 257 passed + 2 skipped (no key) / 259 passed (with key); Captain reran the full suite in the main tree (257+2) and Selenium 11/11 (headless Chromium, three server states): default off → Source column all "spacy", summary "2 of 3 claims covered"; `llm_extract` on → chips ["both","spacy","both","llm"], summary "2 of 4 claims covered · spacy 1 / llm 1 / both 2", pronoun "It is known for the Eiffel Tower" decontextualized to "Paris is known for the Eiffel Tower"; both `tiny_judge`+`llm_extract` together render; 390px no overflow regression (485=485 vs c71b57d baseline). API spot check: 4 claims, 2 verifiable, both confirmed. FEVER subsample (30/class, seed 42, seed DB): spacy 74 claims vs dual 88 claims extracted; coverage 0/90 and AUC 0.500 in both conditions — the ~86-entity seed DB contains none of the sampled entities, which is the honest lower-bound "86 entities are not Wikidata" result, not an extractor failure. Dataset deviation: the public FEVER 2.0 fixers file is unavailable (HF 401, facebookresearch repo 404), so the harness fetches the official FEVER 1.0 shared-task dev set (19,998 claims, converted to `{claim,label,id}`; provenance in a `.provenance.txt` sidecar and both reports).

### `c71b57d` — Record slice 5 UI land in commit index (2026-11-14)

- **Hash:** `c71b57d7584a9872f1fceb859719a0b764142a0d`
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
