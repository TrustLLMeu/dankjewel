# Whole-Project Ideas — Dankjewel Instant Evaluator

**Date:** 2026-11-16  
**Scout:** Grok Build (read-only, no code edits)  
**Branch:** `feature/d75-v2` @ `b022109`  
**Inputs read:** `README.md`, `docs/improvement-plan.md`, `docs/commit-index.md`, `review.txt`, `docs/scouting/2026-11-14-inspiration.md`, `docs/scouting/2026-11-14-claim-extraction.md`, `docs/scouting/2026-11-16-competitive-landscape.md`, `docs/CLAIM_ADMISSION.md`, `docs/MULTILINGUAL_JUDGE.md`, `docs/LEXICON_VALIDATION.md`, `docs/EXTERNAL_EVALS.md`, `ASSUMPTIONS.md`, `CONTRIBUTING.md`, `TODO.md`, `docs/EXTENSIBILITY.md`, `src/` (pipeline, prongs, dimensions, extraction, resources, llm_backends, aggregation, evidence, llm_judge_client), `src/api.py`, `frontend/index.html`, `tests/`, `evaluation_results/` (latency_baseline, robustness, scifact, multilingual_judge, admission_ablation, interactive_path_latency, verifier_eval), `.grok/HERDR.md`

> Constraints respected throughout: generative judges ≤ 1.7B, CPU-first, no fabricated numbers, `scored | unknown | error` semantics.

---

## 0. Where we stand

The project has closed most of the concrete `review.txt` holes since rejection:

- Honesty: `unknown ≠ 0.5`, Prong 1 backend labelled embeddings, weight presets, nine-language scoping.
- Latency: measured `/evaluate` warm medians 672 ms baseline, 1,008 ms all-tracks-on; `/generate-and-evaluate` 974 ms warm; sequential throughput 93/min (76 all-tracks). Hardware fingerprinted. Throughput artefact is the source of truth after the 2026-11-16 correction.
- Prong 3: admission gates 76 → 8 on teaching-prose fixture (all 5 expected lies kept), use-mention pass, MiniCheck verifier (SciFact AUC 0.835), five-way relations, seed 86 → 122 entities — but FEVER coverage stays 0.3% / AUC 0.497. Verifier component validates; KB path remains a lower bound.
- Extensibility: 86-line worked example (Lexical Diversity) with measured recipe in `docs/EXTENSIBILITY.md`.
- Evidence UI: six stages (A evidence contract, B anatomy+coverage ribbon, C claim strip, D signal matrix, E track-agreement dumbbells, F iteration timeline with delta view) — all Selenium-verified including at true 390 px.
- Multilingual: 210-item / 7-language judge-agreement fixture exists; shipped 0.5B Icelandic rho 0.300 (fails ≥ 0.5 check), 1.5B passes all seven (mean rho 0.973), 1.7B passes but trails 1.5B.
- External evals: SciFact landed as second benchmark; LLM-AggreFact harness ready but gated (one account click); AVeriTeC not attempted; human/user studies not run.

What stays open (by commit-index "Open slices" and `TODO.md`): unquoted reported speech (A5), LLM-AggreFact one-click gate, seed coverage, AVeriTeC, Nordic seed expansion + native lexicon validation, human-annotation and user studies, `llm_admit` as measured negative result, LLM readability for Prong 2.

Reviewer wXze's two research-contribution paths remain unmet: (a) a falsifiable finding about the four-prong combination, or (b) a demonstrated advance in extensibility / multilingual support over RAGAS / lm-eval-harness / HF evaluate. The inspiration brief offered two prototypes; neither has been run.

---

## 1. Ranked top 5

These are the five highest-impact changes ordered by leverage = impact / effort, biased toward what would most move `review.txt`.

| Rank | One-liner | Category | Impact | Effort | Risk | Changes paper claims? |
|------|-----------|----------|--------|--------|------|-----------------------|
| 1 | **Prong ablation with CIs on a small human-rated set** — score each prong alone vs combined, report deltas with CIs, answer whether the four-prong combination predicts a useful rating better than any single prong. | Research / Eval methodology | Closes wXze's core objection (no falsifiable claim) in one artefact; reusable for weight guidance. | M — 150 items × two annotators, harness reuses FEVER/SciFact machinery; needs participants. | Low technically; recruitment is the bottleneck. Krippendorff's alpha may be modest. | **Yes** — gives the paper a tested claim, turns "exploration aids" into measured guidance. |
| 2 | **Ship the 1.5B judge for non-English and wire auto-routing** — the 210-item test already proves 1.5B passes all seven languages (0.5B fails Icelandic). Keep 0.5B default for English, route is/nn/fo/da/de/nl/sv to 1.5B via the existing dual-host config. | Multilingual / Runtime | Closes the documented multilingual failure with no new model; uses the already-running claims server. | S — env/config + `lang→judge` routing, docs, one comparative latency row. | Low; must label which judge ran per evaluation (`metadata`). | **Yes** — strengthens multilingual from "unvalidated lexicons" to "measured judge agreement ≥ 0.87 rho per language". |
| 3 | **English-pivot for is/fo claim verification** — translate Icelandic/Faroese claims to English, verify against the English KB, project the verdict back; report pivot vs direct coverage on the multilingual fixture. | Factuality / Multilingual | Biggest coverage lever for the two languages with no KB content; avoids building an is/fo Wikidata slice. | M — one extra `[PIVOT]` task on the 1.5B claims model, English-only verifier, evaluation harness. | Medium — translation drift can flip a verdict; needs a fidelity check (back-translation or human spot-check). | **Yes** — gives Prong 3 a low-resource evaluation story and a measurable coverage comparison. |
| 4 | **Distil the 8B reference judge into the 1.5B runtime judge** — sample the multilingual fixture (or a fresh 1k-item set), collect 8B scores as soft labels, fine-tune the 1.5B judge with LoRA (or DPO on pairwise preferences), measure rho lift vs 8B on held-out languages. | Factuality / Research | Turns the 8B calibration-only model into a training signal; stays under the 1.7B cap; a publishable distillation finding. | L — needs a training slice, LoRA harness, hyperparameter sweep, held-out evaluation. | Medium — small data may overfit; Icelandic lift may be modest. | **Yes** — adds a distillation result and a "small judge closes X% of the gap to 8B" claim. |
| 5 | **Result-comparison export + shareable evaluation bundle** — one-click JSON/CSV export of the current run plus the F-stage delta, with evidence_sources, claim_details, and coverage, so a human study or external replication can consume the signal matrix directly. | Ops / Eval methodology / UI | Unblocks the human-correlation study (Idea 1), external replication, and classroom use; makes the instrument *usable* for research. | S — serialise the existing API response + matrix; add a download button next to the timeline delta. | Low; must strip API keys and bound bundle size. | **No** — enables claim-changing work without itself changing claims. |

---

## 2. Single highest-leverage change

**Prong ablation with confidence intervals on a small human-rated set (Rank 1).**

Why this one:

- `review.txt` V55p ("three of four prongs unvalidated"), wXze ("no research finding, single near-chance benchmark is the entire empirical content"), and YE7H ("no user study") converge on the same gap: the four-prong *combination* has never been tested against ground truth. Everything else is a better instrument with the same missing experiment.
- The infrastructure to run it already exists: `scripts/eval_fever2.py`, `scripts/eval_scifact.py`, `scripts/eval_multilingual_judge.py`, `scripts/eval_robustness.py` plus the evidence contract (`evidence_sources`, `coverage`, per-dimension values) and the signal-matrix export give a harness that can score each prong alone and combined on any labelled set.
- It answers two reviewer requests in one artefact: (a) a falsifiable research claim ("combination predicts a small 'useful for revising' rating better than any single prong"), and (b) weight guidance (derive a weight set from failure costs / human correlation rather than shipping four unvalidated presets as "exploration aids").
- Cost is dominated by annotation (150 items, two annotators, Krippendorff's alpha) — no new models, no latency regression, no multilingual risk.

What it needs:

- A 150-item labelled set: 50 factual QA, 50 safety-sensitive, 50 fluency/form prompts; each item rated on a small rubric (e.g. "would you revise the output given this score?" 1–5, or per-dimension 0–2). Two annotators, reported agreement.
- An ablation script: for each item, run the pipeline four times with one prong enabled plus once with all prongs; compute Spearman between each prong's score (and the weighted total) and the human rating; report per-prong rho, ablated deltas, and CIs (bootstrap or Fisher z).
- A paper-ready table: per-prong correlation, combined correlation, ablation deltas, weight-sensitivity.

Risk: annotation agreement may be modest; correlations may be low. That is still publishable if reported honestly — the finding becomes "combination does not beat single prong on this task", which is more valuable than no experiment.

---

## 3. Full idea catalog

For each idea: **what**, **why** (gap/review point), **effort** (S < day, M days, L weeks), **risk**, **claim-change** (whether it would change a paper claim).

### 3.1 Research contribution and paper framing

| # | Idea | What | Why | Effort | Risk | Claim-change |
|---|------|------|-----|--------|------|--------------|
| R1 | Prong ablation with CIs | Eval each prong alone vs combined on 150 human-rated items; report per-prong rho, ablated deltas, CIs. | Closes wXze/V55p/YE7H core — no falsifiable claim. | M | Recruitment bottleneck. | **Yes** — tested combination claim. |
| R2 | Pairwise judge pass | Complement pointwise scoring with a pairwise preference prompt ("A better than B?"), report pairwise agreement with pointwise rankings and with human pairwise labels. | Pointwise scores can mask position/rubric bias; pairwise is a distinct judge skill with its own literature (MT-Bench method). | M | Small models may be noisier pairwise. | **Yes** — new evaluation mode. |
| R3 | Pre-registered hypothesis | Write a one-page pre-registration (hypothesis, metric, sample size, decision rule) before running R1, publish the protocol alongside the artefact. | Reviewers reward honest negatives; pre-registration makes a modest result credible. | S | None. | **Yes** — frames the contribution as hypothesis-driven. |
| R4 | Competitive extensibility bake-off | Implement the same fifth prong in Dankjewel, RAGAS, lm-eval-harness, and HF evaluate; report LoC, files touched, tests needed, latency delta. | wXze's extensibility comparison — currently only an 86-line recipe, not a bake-off. | M | Some harnesses may be faster to extend. | **Yes** — turns recipe into comparative evidence. |
| R5 | Negative-result paper framing | Frame the resubmission as "An Honest Instrument" — lower-bound reporting, ablation, and distillation as contributions, not SOTA claims. | Matches wXze's praise for the FEVER script's candour; avoids the "packaging existing techniques" trap. | S | Requires discipline in wording. | **Yes** — changes the paper's argument structure. |
| R6 | Calibration study for uncertainty | Map Prong 4 confidence/entropy to empirical accuracy on a scored set (reliability diagram, ECE) rather than treating high entropy as "worse". | Prong 4 is currently unvalidated; calibration is the natural research question for intrinsic signals. | M | Needs a labelled accuracy set. | **Yes** — new evaluation of Prong 4. |

### 3.2 Evaluation methodology

| # | Idea | What | Why | Effort | Risk | Claim-change |
|---|------|------|-----|--------|------|--------------|
| E1 | Human-label correlation for all prongs | 150 items × two annotators × Krippendorff's alpha; Spearman per prong and combined. (R1 detailed above.) | V55p "three of four prongs unvalidated"; YE7H "no user study". | M | Annotator variance. | **Yes** |
| E2 | LLM-AggreFact unblock | One account click → run the ready `scripts/eval_aggrefact.py`; add the AggreFact row to the README/EXTERNAL_EVALS. | wXze single-benchmark; blocks the second factuality benchmark. | S | Still gated until click. | **Yes** — new benchmark row. |
| E3 | AVeriTeC knowledge-store slice | Download the multi-GB knowledge store, index a 500-claim dev slice, score with the existing verifier, report label accuracy. | AVeriTeC is the harder, more realistic third benchmark (real-world claims, NEI/Conflicting). | L | Download + indexing cost. | **Yes** — new benchmark. |
| E4 | Judge calibration (double-centering) | Apply the 2026 "Rank Reversal in Multilingual LLM Judges" double-centering correction to the multilingual judge scores; compare rho before/after. | The competitive landscape brief flagged rank reversal as a known multilingual judge failure; the multilingual fixture can measure it. | S | May not help on this fixture. | No — calibration quality. |
| E5 | Position-bias audit | Judge each multilingual item twice with option/pair order swapped; report flip rate ≤ 10% (MT-Bench method). | The fixture's test plan already proposes this check; it has not been run. | S | May expose bias. | No — methodology detail. |
| E6 | Language-adherence check | Automatically check that judge rationales are in the item's language (or English-by-config); report leak rate per language (nynorsk must not collapse into Bokmål). | Same — proposed in the multilingual plan, not yet measured. | S | Needs a language ID step. | No |
| E7 | Coverage-conditioned reporting | Report factual-accuracy performance as "coverage × conditional accuracy" (the two numbers that matter), not a single AUC over a 0.3% slice. | V55p's neutral-fallback concern; current AUC is over 4/1,174 claims. | S | None. | **Yes** — honest reporting. |
| E8 | Cross-benchmark consistency | Run the verifier on SciFact dev + train (already done) and on LLM-AggreFact once unblocked; report AUC/accuracy per sub-dataset and pooled, with the same 0.8/0.2 bands. | Shows the verifier is not SciFact-overfitted; the paper currently has one verifier benchmark. | S | Some sub-datasets may be weaker. | **Yes** |
| E9 | DecompScore + Hu error fixtures | Extend the ablation with DecompScore (entailed/covered/decontextualised per extractor) and Hu et al. error categories (over-split, missing context, fabricated atoms). | Separates extractor error from verifier error; pre-empts "decomposition only briefly explained". | M | Needs fixture authoring. | No — deeper methodology. |

### 3.3 Factuality pipeline

| # | Idea | What | Why | Effort | Risk | Claim-change |
|---|------|------|-----|--------|------|--------------|
| F1 | English-pivot for is/fo | Translate is/fo claims to English, verify against the English KB, project verdicts back; report pivot vs direct coverage on the multilingual fixture. | is/fo have no KB content; English pivot avoids building an is/fo slice. | M | Translation drift. | **Yes** — low-resource evaluation story. |
| F2 | Self-training KB expansion | Use the verifier on high-confidence (> 0.8 / < 0.2) claims from a larger corpus to propose new Wikidata entities; human-verify a sample, ingest the rest above a precision threshold. | Seed is 122 entities; a 200k dump is out of scope but self-training scales the seed without a dump. | L | Precision may be modest; needs a sample audit. | **Yes** — new KB scale number. |
| F3 | Distil 8B → 1.5B judge | Fine-tune the 1.5B judge on 8B soft labels (or DPO on pairwise prefs) from the multilingual fixture + synthetic is/fo data; measure rho lift on held-out languages. | Turns the calibration model into a training signal under the 1.7B cap. | L | Small data may overfit. | **Yes** — distillation finding. |
| F4 | Atomic propositions front-end (MPropositionneur-V2) | Emit decontextualized propositions from the 1.5B claims model, then run spaCy triples on those propositions as well as raw text (dual output already supports this). | Published proof that propositions raise recall for weak extractors; keeps current triples. | S | May duplicate claims; dedupe handles it. | No |
| F5 | VeriScore verifiability gate | Filter extraction output to verifiable claims only; report coverage over verifiable claims, show unverifiable as `unknown` with reason. | V55p neutral-fallback — unverifiable claims drag coverage and AUC. | S | Gate quality needs tuning. | **Yes** — honest denominator. |
| F6 | Core uniqueness filter | Lexical/embedding uniqueness + informativeness heuristic to drop tautologies ("X is a person") before scoring; dropped claims become `unknown` with reason. | 0.5B/1.5B decomposers over-produce tautologies that pad coverage and flatten AUC. | S | Over-filtering removes real claims. | No |
| F7 | Staged extraction (select → disambiguate → decompose) | Claimify-style three-stage prompt: selection drops opinion/speculation sentences, disambiguation resolves or abstains on pronouns, decomposition emits bracket-annotated claims. | Closes wXze coverage < 10% and V55p discriminative signal in one mechanism; the claim-extraction brief ranked this #1. | M | 2–3 calls per paragraph; needs abstention handling. | **Yes** — new extraction method. |
| F8 | Claimify disambiguation abstention | Explicit "Cannot be disambiguated" → `unknown` instead of a guessed triple; count abstentions in `metadata.claim_admission`. | Honest unknown semantics at the extraction stage — maps to `scored|unknown|error`. | S | Part of F7 but shippable alone. | No |
| F9 | Admission-gate audit on a second corpus | Run the 76→28→17→8→9 ablation on a non-teaching corpus (e.g. SciFact or LLM-AggreFact claims) to show the gates generalise beyond the teacher-prose fixture. | The current admission story rests on one fixture; a second corpus validates it. | S | Some gates may be less effective. | No — robustness. |
| F10 | Unquoted reported speech parser | Rule-based or small-model parser for "teacher said that X" embeddings; extract X as a quoted claim rather than depending on `llm_extract`. (ASSUMPTIONS.md A5 open slice.) | The use-mention pass handles quoted/`Claim:`-labelled claims; mid-sentence reported speech still depends on the optional LLM track. | M | Grammar-specific; language-dependent. | **Yes** — closes A5. |

### 3.4 Multilingual

| # | Idea | What | Why | Effort | Risk | Claim-change |
|---|------|------|-----|--------|------|--------------|
| M1 | Ship 1.5B for non-English | Keep 0.5B default (English), route non-English to 1.5B via `lang→judge` config; label which judge ran per evaluation. | 0.5B fails Icelandic rho 0.300; 1.5B passes all seven (lowest 0.874). | S | Two-model config complexity. | **Yes** — measured multilingual agreement. |
| M2 | Faroese inclusion | Add a 30-item Faroese subset to the multilingual fixture (the only omitted language, 210 → 240 items); report where fo lands. | Faroese omission is honest but fixable; the lexicon already ships fo. | S | No strong judge may pass fo. | **Yes** — nine-language fixture. |
| M3 | EuroLLM-1.7B evaluation | Evaluate EuroLLM-1.7B (35 EU languages, all Nordic except is/fo, Apache-2.0) as a multilingual judge candidate once the cap admits 1.7B — 30 items × 7 languages on the existing harness. | Best-matched language set for TrustLLM's nine; over cap but user already raised to 1.7B for Qwen3-1.7B. | S | Needs alignment / instruction following pass. | **Yes** — new candidate result. |
| M4 | Nordic seed expansion (measured) | Extend the Wikidata seed with the planned Nordic/TrustLLM entities (NTNU-adjacent, EU/Nordic places), re-measure FEVER coverage 4/1,174 → N/1,174. | The 86 → 122 expansion did not move FEVER coverage; a measured Nordic expansion shows whether it can. | M | May still not move FEVER (wrong entities). | **Yes** — new seed count + coverage. |
| M5 | Lexicon native validation | One native speaker per non-English language reviews the 6-cue lexicon file; report agreement or precision per language (or at least for nn vs nb split). | wXze lexicon validation — the mechanical audit (key parity, duplicates, `lol`/`hey` loanwords) passed but translation quality is unvalidated. | L | Recruitment; some gaps expected. | **Yes** — upgrades lexicon from "unvalidated" to measured. |
| M6 | Icelandic-specific judge tuning | Distil the 8B judge's Icelandic row (8B rho 0.972 on is) into the runtime judge with Icelandic-only synthetic pairs. | Icelandic is the weakest cell for every small judge (0.5B 0.300, 1.5B 0.874, 1.7B 0.603). | M | Small data; may overfit is. | **Yes** — per-language improvement. |
| M7 | Rubric language audit | Review whether the English rubric ("0 = irrelevant, 0.5 = partially, 1 = directly answers") translates well across all seven languages; author language-specific rubrics if needed. | Current fixture uses an English rubric for non-English judgments; rubric translation may affect rho. | S | Needs native speaker input. | No — methodology. |

### 3.5 Runtime and architecture

| # | Idea | What | Why | Effort | Risk | Claim-change |
|---|------|------|-----|--------|------|--------------|
| A1 | Parallel prong execution | Run Prongs 1–3 concurrently (they are independent; Prong 4 needs logprobs from the generator), aggregate when all settle. | Current throughput is sequential (93/min); parallel execution is the obvious latency lever. | M | Shared resource contention; needs per-prong timeout. | **Yes** — new latency numbers. |
| A2 | Response caching (text-hash → result) | LRU cache by `hash(text+prompt+lang+flags)` for `/evaluate`; return cached scores instantly, with a `cached: true` flag. | Repeated evaluations of the same text (iteration workflow) pay the full pipeline each time. | S | Cache invalidation on model/config change. | No — latency optimisation. |
| A3 | Streaming partial evaluation | Stream prong results as they complete over SSE (Prong 2 returns in ms, Prong 3 in ~200 ms per claim), fill the UI incrementally rather than waiting for all prongs. | `/generate/stream` already streams tokens; evaluation still blocks to completion. | M | Frontend complexity; partial states. | No — perceived latency. |
| A4 | Model pre-warming | Warm the embedding, toxicity, spaCy, and optional MiniCheck models at startup rather than on first request (cold 9.2 s → warm 672 ms). | The 9.2 s cold cost dominates first-user latency; pre-warming moves it to deploy time. | S | Startup time grows; memory pressure. | **Yes** — new cold-latency number. |
| A5 | Quantised verifier | Evaluate MiniCheck INT8 quantisation (770M → ~400 MB) for CPU; measure AUC drift vs latency win. | Verifier load is 6.4 s cold, ~200 ms warm per claim; quantisation halves memory. | M | AUC may drop; quantisation tooling. | **Yes** — new latency/quality trade-off. |
| A6 | Concurrent serving benchmark | Run `measure_latency.py` with N concurrent clients (2, 4, 8) in addition to sequential; report throughput vs latency under contention. | Reviewer-relevant: sequential throughput is measured but concurrent is "not measured". | S | Needs a small harness addition. | **Yes** — new throughput table. |
| A7 | Failure-mode circuit breaker | If the 0.5B judge or 1.5B claims server fails N times in a row, skip it for a cooldown window and serve embeddings/spaCy baselines; report `judge_status=degraded` in coverage. | Dead-port cases are tested; a flapping server is not. | S | Needs tuning. | No |
| A8 | OpenAPI contract + SDK | Publish an OpenAPI spec for `/evaluate` and `/generate-and-evaluate`; ship a tiny Python/JS SDK that wraps the API and handles `unknown`/`error` correctly. | Extensibility demo is for Python contributors; an external consumer story is missing. | M | Maintenance. | **Yes** — new extensibility surface. |

### 3.6 Evidence UI

| # | Idea | What | Why | Effort | Risk | Claim-change |
|---|------|------|-----|--------|------|--------------|
| U1 | Shareable evaluation bundle | One-click JSON/CSV export of the current run plus the F-stage delta (the signal matrix, claim_details, coverage, per-prong scores) for replication or human study. | Rank 5 — unblocks replication and the human study. | S | Bundle size; key stripping. | No |
| U2 | Weight-sensitivity sparkline | Under the preset buttons, a small sparkline showing how the total score moves as each preset is hovered (or as a weight slider is dragged), without re-running evaluation. | Presets are "exploration aids" with no validation; sensitivity makes that visible. | S | Needs client-side re-aggregation (already does for presets). | No |
| U3 | Claim-level verdict rationale | Next to each claim chip, show the MiniCheck verifier's support probability (p=0.01 …) and the KB matched fact inline, rather than only in a tooltip. | Tooltip-only evidence hides the signal from scannability; the claim strip is the right place. | S | Clutter if many claims. | No |
| U4 | Unknown-detail drill-down | Clicking an `unknown` dimension badge opens a one-line explanation of why (no prompt for Relevance, no verifiable claims, no logprobs, judge unreachable). | Honest semantics are in the data (`status`, `evidence_sources`) but not always surfaced. | S | Needs per-status copy. | No |
| U5 | Longitudinal run comparison (export) | Extend the F-stage delta view with a "compare last 5 runs" table (run × prong) and a CSV export, so a prompt-iteration session is a dataset. | D7.5's "steer prompting" workflow implies history; the timeline sparkline is the start. | M | localStorage size; pagination. | No |
| U6 | Error-state illustrations | Illustrate the empty/error/unknown states with example payloads so a first-time user sees what a failure looks like. | New users may not trigger unknown/error on first try. | S | Copy needed. | No |
| U7 | Print-friendly evaluation report | One-click printable/PDF report of the current evaluation (scores, radar, anatomy, claim strip, matrix, coverage) for inclusion in a paper or thesis. | Useful for the paper workflow and teaching. | M | Print CSS. | No |

### 3.7 Documentation, extensibility, and operations

| # | Idea | What | Why | Effort | Risk | Claim-change |
|---|------|------|-----|--------|------|--------------|
| D1 | Paper-trail traceability | Every number in the paper's tables carries a `evaluation_results/*.json` path or commit hash footnote; a CI check verifies the paper's numbers against artefacts. | Reviewer-trust: wXze praised the FEVER script's candour; traceability makes it auditable. | M | Paper build complexity. | No — but strengthens every claim. |
| D2 | YAML dimension registry | Replace hard-coded dimension registration with a declarative YAML schema (name, prong, backend, aggregate flag, weights eligibility) + registry loader. | Inspiration Ideas 5 — wXze extensibility; the captain deferred the YAML-vs-hard-coded decision. | M | Migration of existing dimensions. | **Yes** — new extensibility claim. |
| D3 | Tenth-language recipe (performed) | Perform the "add a tenth language" recipe end-to-end (e.g. `it` or `pl`) — lexicon YAML, Flesch coeff or fallback, locale file, test — and record LoC/time. | Companion to the 86-line fifth-dimension recipe; makes the multilingual extensibility claim demonstrated rather than described. | S | Needs coefficient research. | **Yes** — demonstrated multilingual extensibility. |
| D4 | Failure-mode runbook | Document the seven robustness cases (empty, long, wrong-language, dead judge/claims/verifier, malformed JSON, timeout) as a runbook with expected `status` values, not just a test. | Robustness matrix exists but is not user-facing documentation. | S | None. | No |
| D5 | Evaluation-result schema versioning | Tag the API response schema (`evaluation_results/*.json`) with a version field; document the schema in `docs/` so external consumers can rely on `evidence_sources`, `coverage`, `claim_details`. | External replication depends on a stable contract; the evidence contract (Stage A) has no version. | S | Migration path. | No |
| D6 | Reproducibility checklist for reviewers | Ship a `REPRODUCE.md` that lists every `scripts/eval_*.py` invocation, expected artefact, and verification command so a reviewer can re-measure the paper's tables. | wXze reproducibility concern; the paper currently has numbers scattered across `evaluation_results/`. | S | Maintenance. | No — but enables trust. |
| D7 | Crew operation dashboard | A `herdr status` view showing which panes are working/idle, their last commit, and queue depth — so the captain sees the crew at a glance. | Operational friction: 12 panes, NTNU rate limits, and worktree merges are currently tracked manually. | M | herdr tooling work. | No |

---

## 4. Ideas that would change the paper's claims

Collected from the catalog above — these are the ideas whose result, if adopted, belongs in the paper's abstract, results, or limitations.

| Claim area | Ideas | Current paper statement | New statement after idea |
|------------|-------|-------------------------|--------------------------|
| Research contribution | R1, R3, R6 (ablation + pre-registration + calibration) | No tested combination claim; four presets as "exploration aids". | "On a 150-item human-rated set (2 annotators, alpha = X), the four-prong combination correlates rho = Y with usefulness, Z points above the best single prong (CI [...])." Or the honest negative. |
| Factuality | E2, E3, F1, F2, F7, F5, F10, E8 | FEVER 0.3% coverage / AUC 0.497; SciFact verifier 0.835; seed 122 entities. | AggreFact + AVeriTeC rows; English-pivot coverage for is/fo; self-training seed expansion; staged-extraction lift; verifiability-gated denominator. |
| Multilingual | M1, M2, M3, M5, M6 | "Shipped 0.5B fails Icelandic rho 0.300; 1.5B passes all seven". Lexicons unvalidated. | "Language-routed judges: 0.5B English, 1.5B non-English (lowest rho 0.874); Faroese measured; EuroLLM candidate; native-validated lexicons." |
| Judge quality | F3, E4, E5, E6, F4 | 0.5B vs 1.5B vs 8B table; 1.7B not adopted. | "Distilled 1.5B closes X% of the 8B gap (is/fo lift Y); double-centering rank reversal corrected; position-bias audit Z% flip rate." Plus MPropositionneur front-end recall lift. |
| Extensibility | D2, D3, A8, R4 | 86-line worked example; no baked-off comparison. | "Fifth prong in N lines (YAML registry); tenth language in M lines; bake-off vs RAGAS/lm-eval-harness." |
| Runtime | A1, A4, A6, A5 | 672 ms baseline warm, 1,008 ms all-tracks, 93/min sequential, interactive 974 ms. | "Parallel prongs X ms; pre-warmed cold Y ms; concurrent throughput Z/min; quantised verifier trade-off." |
| Methodology | E1, E7, E9, D1 | Single-benchmark, single-fixture reporting. | "Coverage × conditional accuracy; DecompScore + Hu error breakdown; paper numbers traceable to artefacts." |

---

## 5. Rejected ideas

Things that sound good but are not worth it under the current constraints or would violate the honest-semantics contract.

### 5.1 Model and training work that violates the cap or non-goals

| Idea | Why it sounds good | Why rejected |
|------|--------------------|--------------|
| Full 200k-entity Wikidata dump | Fixes 0.3% coverage permanently. | Explicit non-goal; multi-GB ingestion + indexing + freshness story; not PoC-sized. The English-pivot (F1) and self-training (F2) are cheaper levers. |
| Fine-tune or LoRA the judge before any measurement | Stronger judge immediately. | Non-goal for v2; do the ablation (R1) first so tuning has a metric to optimise. Distillation (F3) is the scoped version. |
| Use a 7B+ judge at runtime | Better multilingual and factuality instantly. | Violates the ≤1.7B cap; the project's CPU-first identity is part of its niche (see competitive landscape §3 differentiation). |
| Bespoke-MiniCheck-7B as verifier | Stronger verifier than 770M. | Same cap violation; keep MiniCheck-FL T5-Large (770M) and quantise it (A5) instead. |
| JEDI encoder-only decomposition | No generative model at inference, one forward pass. | Needs their trained encoder + synthetic-rationale corpus; a training loop is a PoC non-goal. |
| RL-tuned decomposition policy (Lu et al.) | Optimal atomicity per verifier. | Training, out of scope; use the verifier-preferred atomicity rule as a prompt guideline instead. |
| Multilingual LLM judge for fo/is without data | "Just judge in every language." | No aligned model covers Faroese; Icelandic is weak on every small judge. English-pivot (F1) is the viable fo/is path. |

### 5.2 Architecture and product ideas that add cost without closing a reviewer gap

| Idea | Why it sounds good | Why rejected |
|------|--------------------|--------------|
| MCP server / tool marketplace | Trendy; OpenTools inspiration. | Out of frame for a text evaluator (inspiration §7 correctly skipped). An OpenAPI SDK (A8) gives external integration without MCP. |
| Real-time collaborative evaluation | Google-Docs-style shared sessions. | No reviewer asked for it; operational complexity (WebSockets, auth) for a single-user instrument. |
| Vector-DB backed KB | Modern retrieval story. | The verifier scores against formatted KB facts; a vector DB adds infrastructure for no reviewer-requested gain. The knowledge-store slice (E3) is the right retrieval story. |
| Per-user model personalisation | Adapt weights to user feedback. | Requires user data and feedback loops; the weight-sensitivity sparkline (U2) and ablation-derived presets (R1) are the honest alternatives. |
| Full provenance/CoT attribution | OmniProv-style source tracing. | OmniProv was rejected for this (no IRR, no correction rates, 0.478 source+relation accuracy); our KB path is open-domain text vs Wikidata, not tool-trace provenance. |
| LLM aggregation (judge picks the total) | "The LLM decides the final score." | Opaque; contradicts the honest unknown/error semantics and the transparent weighted-average design. The ablation (R1) should derive weights, not a black box. |
| Auto-remediation ("fix the text") | Evaluation plus rewriting. | Evaluation and generation are separate concerns; the evidence panels already show what to fix. |

### 5.3 UI and documentation ideas that would be busywork

| Idea | Why it sounds good | Why rejected |
|------|--------------------|--------------|
| Dark mode / theme switcher | Polish. | No reviewer or user asked; the responsive fix (390 px) was the real UI gap and is closed. |
| Inline model playground | Generate inside the evaluator page. | `/generate-and-evaluate` already streams; the evaluator's niche is scoring, not generation UX. |
| Exhaustive per-dimension documentation pages | Completeness. | `CONTRIBUTING.md`, `docs/EXTENSIBILITY.md`, and `docs/CLAIM_ADMISSION.md` plus method docstrings already cover it; more pages fragment the docs. |
| Native-speaker lexicon campaign before English validation is done | "Ship nine validated languages." | English validation + honest unvalidated labelling is the defensible position; a native campaign (L) should follow the human study, not precede it. |
| Public leaderboard | Visibility. | No reviewer asked; the project is an instrument, not a model, and a leaderboard implies ranking models rather than scoring text. |

### 5.4 Methodology traps

| Idea | Why it sounds good | Why rejected |
|------|--------------------|--------------|
| LLM-generated gold labels without IRR | Fast human-proxy evaluation. | The OmniProv rejection reason (GPT-5.4 labels, no IRR) — the competitive landscape brief cites it as a review-killing pattern. Any proprietary judge is calibration only. |
| Single-AUC reporting over 0.3% coverage | One number is simpler. | V55p's "no discriminative signal even on covered claims" and wXze's "near-chance" critique require coverage × conditional accuracy, not a hidden denominator. |
| Averaging rho across languages | One summary number. | Hides the Icelandic failure (0.300) — the test plan and this brief require per-language reporting, no averaging. |
| Claiming nine production languages now | Bigger market story. | The mechanical audit passed but native validation is pending; the honest claim is "English validated, eight unvalidated translations" (LEXICON_VALIDATION.md §5). |

---

## 6. How to use this brief

Suggested attack order if the captain adopts this brief (respecting the 1.7B/CPU constraints and the existing pipeline):

1. **Unblock LLM-AggreFact** (E2, S) — one click, immediate second benchmark row.
2. **Wire the 1.5B non-English judge routing** (M1, S) — closes the documented failure.
3. **Add the English-pivot for is/fo** (F1, M) — gives the low-resource story.
4. **Run the ablation harness** (R1/E1, M) — the research-contribution experiment; start recruitment early.
5. **Add result-comparison export** (U1/D5, S) — unblocks external replication of R1.
6. **Then distillation** (F3, L) and **staged extraction** (F7, M) as parallel tracks once R1 has a metric to optimise against.

Phases 1–5 of `improvement-plan.md` are closed. These ideas seed Phase 6 (research claim + human study) and a Phase 7 (KB scale + self-training) if the user approves.

---

## 7. Sources

- ACL Anthology IDs: Claimify `2025.acl-long.348`, FActScore `2023.emnlp-main.741`, MiniCheck `2024.emnlp-main.499`, VeriScore `2024.findings-emnlp.552`, WiCE `2023.emnlp-main.470`, DecompScore `2024.starsem-1.13`, Lu et al. `2025.acl-long.254`, Core `2025.findings-acl.1018`, Hu et al. `2025.naacl-long.320`, AlignScore `2023.acl-long.634`, AVeriTeC 2025 `2025.fever-1.15`, VeriFastScore `2025.findings-emnlp.491`, DnDScore `2025.emnlp-main.1205`, JEDI `2025.emnlp-main.1615`, MPropositionneur-V2 `2026.kallm-1.14` (via `2026-11-14-claim-extraction.md` + its 2026-11-14 addenda).
- Vendor/OSS competitive sweep: `docs/scouting/2026-11-16-competitive-landscape.md` (LangSmith, Langfuse, Braintrust, Phoenix ELv2, DeepEval, RAGAS, TruLens, Opik, promptfoo, etc.; stars/licences fetched 2026-11-16).
- Calibration note: "Rank Reversal in Multilingual LLM Judges" arXiv 2026-08-23 (competitive addendum).
- Benchmarks: SciFact `evaluation_results/scifact.json` (AUC 0.835 dev), FEVER re-measurement 4/1,174 (0.3%) on both 86- and 122-entity DBs, multilingual 210-item fixture (7 × 30) in `evaluation_results/multilingual_judge.json`, admission ablation 76→9 in `evaluation_results/admission_ablation.json`, latency `evaluation_results/latency_baseline.json` + `interactive_path_latency.md`, robustness `evaluation_results/robustness.json`.

Scout is idle. Nothing committed; this file stays unstaged.
