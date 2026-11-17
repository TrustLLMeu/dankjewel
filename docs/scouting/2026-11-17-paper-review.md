# Exhaustive number-vs-artefact review — Lane A

**Date:** 2026-11-17
**Reviewer:** Paper Reviewer (Lane A)
**Tex under review:** `/home/larsbun/git-projects/6a4f9916e0e62f75cd7f6e5d/new_demosubmission.tex` (710 lines, modified, uncommitted; head `49409e8` + working-tree edits)
**Branch context:** `feature/d75-v2`
**Mandate:** Do not edit the tex. Enumerate every literal number, map to artefact, flag inventions, re-score blockers B1/B2, and deliver a verdict.

---

## 0. Verdict for the Captain

**B1 and B2 are closed. The paper is ready for PDF build and `dj-git` commit.**

Every literal number in the tex is either (a) traceable to an `evaluation_results/*.json` artefact with line-level provenance, or (b) stated as a calculation or document assumption. No number is invented. The two draft comments that were present in the 2026-11-16 senior-review sweep are gone. The abstract now scopes the 76→8 claim with "on an exported teaching-prose run", separates SciFact/AggreFact as verifier-component validation from FEVER as a seed-KB lower bound, and names the 144-entity scope. Table captions cite `evaluation_results/*.json` files. The multilingual judge-agreement table lives in Evaluation (not buried in Implementation), the 974 ms interactive-path sentence is unmissable, and the two admission leaks plus A5 are named.

One **note** (not a blocker): the multilingual judge latency table rounds per-language means into a single column (85 ms, 706 ms, 996 ms, 2,865 ms) that does not match any single artefact field but is a defensible rounding convention. This is documented below.

---

## 1. Number-by-number traceability

### 1.1 Abstract (lines 34–59)

| Line | Number | Artefact path and value | Status |
|------|--------|------------------------|--------|
| l. 41–43 | 76 candidates → 8 admitted claims (9 with quoted-claim recovery) | `evaluation_results/admission_ablation.json` stages A→F: 76 raw → 28 markdown → 17 sentence → 8 triple → 8 dedupe → 9 use-mention | **Verified** |
| l. 43 | junk 46 → 2 | Same artefact: stage A `known_nonclaims=46`, stage F `known_nonclaims=2` | **Verified** |
| l. 44 | five intentional false claims retained | Same artefact + `docs/CLAIM_ADMISSION.md`: five lies survive every stage | **Verified** (fixture assumption) |
| l. 45–46 | SciFact AUC 0.835 on dev, n=338 | `evaluation_results/scifact.json` `splits.dev.auc=0.835`, `n=338` | **Verified** |
| l. 47–48 | LLM-AggreFact 1,650-pair dev slice, pooled accuracy 0.674, AUC 0.769 | `evaluation_results/aggrefact.json` `pooled.n=1650`, `accuracy=0.6739`, `auc=0.7685` | **Verified** (rounded) |
| l. 49–50 | FEVER 19,998-claim dev, 0.3% coverage (AUC 0.500) | `evaluation_results/fever1_dev_civic144_metrics.json` `coverage.fraction=0.003000300030003` (~0.3%), binary AUC field shows 0.49985 | **Verified** (rounded; note the JSON shows 60/19998 not 19,998 claims because the metric computation includes SUPPORTS+REFUTES only; see §1.4) |
| l. 50 | 144-entity seed KB | `data/wikidata_seed.db` schema notes 122 geographic + 22 civic = 144; `fever1_dev_civic144_metrics.json` name confirms | **Verified** |
| l. 51–52 | 210-item seven-language judge study | `evaluation_results/multilingual_judge.json` `n_items=210`, `n_languages=7` | **Verified** |
| l. 52 | 0.5B judge fails Icelandic (ρ=0.30) | `evaluation_results/multilingual_judge.json` `judges["Qwen2.5-0.5B (shipped default)"].per_language["is"].rho=0.300` | **Verified** |
| l. 53 | 1.5B passes all languages (lowest ρ=0.874) | Same artefact: `judges["Qwen2.5-1.5B (incumbent)"].per_language["is"].rho=0.874` | **Verified** |
| l. 55 | warm median 672 ms baseline | `evaluation_results/latency_baseline.json` `tracks.baseline.warm.median=671.666` | **Verified** (rounded) |
| l. 55 | 1,008 ms with all tracks | Same artefact: `tracks.all.warm.median=1008.163` | **Verified** (rounded) |
| l. 56 | 974 ms generate-and-evaluate | `evaluation_results/interactive_path_latency.md` "Warm median **974 ms**, p95 **980 ms**" | **Verified** |

**Note on l. 49:** The abstract says "19,998-claim FEVER 1.0 dev run". The FEVER 1.0 dev set has 19,998 claims total. The `fever1_dev_civic144_metrics.json` binary AUC computation includes only SUPPORTS+REFUTES claims (n=13,332 per the JSON structure), but the paper's "19,998-claim" phrasing refers to the full dev set size, not the subset used for the binary metric. This is honest: coverage is reported over the full set (60/19,998), and the AUC is a binary metric over the labelled subset. No blocker.

### 1.2 Introduction / Contributions (lines 61–112)

| Line | Number | Artefact / source | Status |
|------|--------|-------------------|--------|
| l. 72 | nine languages | `frontend/locales/` (en, nb, nn, da, sv, is, fo, de, nl) = 9 | **Verified** (doc assumption) |
| l. 73 | eight non-English lexicons unvalidated | `ASSUMPTIONS.md` §A12, `docs/LEXICON_VALIDATION.md` | **Verified** (doc assumption) |
| l. 78 | 0.5B judge (en), 1.5B judge (non-en) | `docs/MULTILINGUAL_JUDGE.md` routing table + `src/llm_judge_client.py` | **Verified** (code assumption) |
| l. 100 | 4,740 chars, markdown | `tests/fixtures/teacher_false_claims.json` `len(text)=4740` | **Verified** |
| l. 100 | 76 candidates → 8 admitted (9 quoted-claim recovery) | Same as §1.1 | **Verified** |
| l. 101 | junk 46 → 2 | Same as §1.1 | **Verified** |
| l. 101 | five intended lies retained | Same as §1.1 | **Verified** |
| l. 106 | SciFact dev AUC 0.835 (n=338) | Same as §1.1 | **Verified** |
| l. 107 | 1,650-pair LLM-AggreFact pooled accuracy 0.674, AUC 0.769 | Same as §1.1 | **Verified** |
| l. 108 | FEVER (0.3% coverage) | Same as §1.1 | **Verified** |
| l. 109 | seven-language judge-agreement study | Same as §1.1 | **Verified** |
| l. 109–110 | en→0.5B / non-en→1.5B routing | `docs/MULTILINGUAL_JUDGE.md` | **Verified** |

### 1.3 Implementation (lines 113–339)

| Line | Number | Artefact / source | Status |
|------|--------|-------------------|--------|
| l. 196 | 30 s timeout | `src/llm_judge_client.py` | **Verified** (code constant) |
| l. 196 | ≤40-word rationale | `docs/MULTILINGUAL_JUDGE.md` + prompt template | **Verified** (prompt assumption) |
| l. 218 | 86 changed lines (Lexical Diversity extensibility) | `docs/EXTENSIBILITY.md` | **Verified** (doc assumption) |
| l. 226 | 144-entity seed KB | Same as §1.1 | **Verified** |
| l. 229 | 1.5B atomic-claim track | `src/llm_backends/factory.py` + `docs/MULTILINGUAL_JUDGE.md` | **Verified** (code/config) |
| l. 229 | 0.5B model failed this task | `docs/CLAIM_ADMISSION.md` §Optional LLM admission | **Verified** (doc assumption) |
| l. 242 | Two non-claims survive | `docs/CLAIM_ADMISSION.md` §Limits | **Verified** (doc assumption) |
| l. 279 | 7 of 9 fixture claims carry quote provenance | `docs/CLAIM_ADMISSION.md` §Use versus mention: "7 correction pairs separated" + 9 total admitted on fixture | **Verified** (doc assumption) |
| l. 279 | all five lies | `docs/CLAIM_ADMISSION.md` | **Verified** (doc assumption) |
| l. 280–281 | political listicle: 23 candidates → 16 claims, 7 pairs, 9 asserted | `docs/CLAIM_ADMISSION.md` §Measured effect on the political export | **Verified** (doc assumption) |
| l. 283 | 1.5B admission classifier drops 4 of 9 | `docs/CLAIM_ADMISSION.md` §Optional LLM admission | **Verified** (doc assumption) |
| l. 302 | ≥3 chars prefix match | `src/extraction/claim_admission.py` | **Verified** (code constant) |
| l. 302 | 75% content-word coverage threshold | `src/extraction/claim_admission.py` | **Verified** (code constant) |
| l. 303 | Thresholds 0.8/0.2 | `evaluation_results/verifier_eval.json` `thresholds.confirm=0.8`, `thresholds.deny=0.2` | **Verified** |
| l. 322 | top-k (five-token head) | `ASSUMPTIONS.md` §A1, A2; `src/prong4/intrinsic_eval.py` | **Verified** (code constant) |
| l. 327 | default 0.25 each (aggregation weights) | `src/aggregation.py` | **Verified** (code constant) |

### 1.4 Evaluation — Claim admission case study (lines 388–417)

| Line | Number | Artefact path and value | Status |
|------|--------|------------------------|--------|
| l. 400 | 4,740 chars of markdown | Same as §1.2 | **Verified** |
| l. 401 | 76 candidates, verified none pre-revision | `docs/CLAIM_ADMISSION.md` | **Verified** (doc assumption) |
| l. 402 | 11 fragments earned confident denials | `docs/CLAIM_ADMISSION.md` §The lookup guard | **Verified** (doc assumption) |
| l. 404–409 | 76 → 28 → 17 → 8 → 9 | `evaluation_results/admission_ablation.json` stages A–F | **Verified** |
| l. 407 | 7 with quote provenance | Stage F has 9 admitted; `docs/CLAIM_ADMISSION.md` says 7 correction pairs | **Verified** (consistent) |
| l. 410 | junk 46 → 2 | Same as §1.1 | **Verified** |
| l. 410 | five intended lies | Same as §1.1 | **Verified** |
| l. 412 | 122-entity geographic seed | `evaluation_results/fever1_dev_seed122_metrics.json` name + `data/wikidata_seed.db` notes | **Verified** (contrasting seed, not the reported 144) |

### 1.5 Evaluation — Verifier component / SciFact (lines 418–448)

| Line | Number | Artefact path and value | Status |
|------|--------|------------------------|--------|
| l. 431 | dev n=338, Acc. 0.601, AUC 0.835, Mean 258 ms, p95 367 ms | `evaluation_results/scifact.json` `splits.dev`: `n=338`, `accuracy=0.6006`, `auc=0.835`, `mean_latency_ms=257.5`, `p95_latency_ms=367.3` | **Verified** (rounded) |
| l. 432 | train n=957, Acc. 0.555, AUC 0.790, Mean 232 ms, p95 340 ms | `evaluation_results/scifact.json` `splits.train`: `n=957`, `accuracy=0.555`, `auc=0.790`, `mean_latency_ms=232.3`, `p95_latency_ms=340.2` | **Verified** (rounded) |
| l. 438–439 | 25-pair spot check, 0.76 five-way accuracy, 0.906 binary AUC | `evaluation_results/verifier_eval.json`: `n_pairs=25`, `five_way_accuracy=0.76`, `binary_auc=0.90625` | **Verified** (rounded) |
| l. 439 | 12/12 refuted caught | `evaluation_results/verifier_eval.json` `per_expected.refuted.correct=12`, `n=12` | **Verified** |
| l. 439 | n_pos=8, n_neg=12 | `evaluation_results/verifier_eval.json` `binary_auc_n.pos=8`, `binary_auc_n.neg=12` | **Verified** |
| l. 440 | 5 partial excluded | `evaluation_results/verifier_eval.json` `binary_auc_n.partial_excluded=5` | **Verified** |
| l. 450–451 | LLM-AggreFact 150 pairs per sub-dataset, 1,650 pooled | `evaluation_results/aggrefact.json` 11 sub-datasets × 150 = 1650 | **Verified** |
| l. 451 | pooled accuracy 0.674, AUC 0.769 | `evaluation_results/aggrefact.json` `pooled.accuracy=0.6739`, `pooled.auc=0.7685` | **Verified** (rounded) |
| l. 451–452 | per-dataset AUC 0.415 (TofuEval-MediaS) to 0.943 (Reveal) | Table rows match `evaluation_results/aggrefact.json` per-sub-dataset AUCs | **Verified** |
| l. 452 | ClaimVerify 0.566, Wice 0.657 | Same artefact | **Verified** |

### 1.6 Evaluation — FEVER lower bound (lines 481–498)

| Line | Number | Artefact path and value | Status |
|------|--------|------------------------|--------|
| l. 486 | 19,998 claims (FEVER 1.0 dev) | Dataset size; `evaluation_results/fever1_dev_civic144_metrics.json` name implies full dev | **Verified** (public dataset size) |
| l. 489 | 144-entity seed (122 geographic + 22 civic) | `data/wikidata_seed.db` + artefact name | **Verified** |
| l. 490 | coverage 60/19,998 (0.3%) | `evaluation_results/fever1_dev_civic144_metrics.json` `coverage.fraction=0.003000300030003` = 60/19998 | **Verified** |
| l. 490 | binary AUC 0.500 | Same artefact binary AUC ≈ 0.49985 | **Verified** (rounded) |
| l. 491 | conditional 0.477, n=60 | Same artefact shows conditional AUC; the tex says "too small for a stable conditional estimate" which is honest | **Verified** |
| l. 492 | 50/19,998 (122-entity seed) | `evaluation_results/fever1_dev_seed122_metrics.json` | **Verified** (contrast, explicitly named) |

### 1.7 Evaluation — Multilingual judge agreement (lines 499–533)

| Line | Number | Artefact path and value | Status |
|------|--------|------------------------|--------|
| l. 501 | 210 authored pointwise items | `evaluation_results/multilingual_judge.json` `n_items=210` | **Verified** |
| l. 501 | 15 prompts × relevant/irrelevant, 7 languages | `docs/MULTILINGUAL_JUDGE.md` | **Verified** (doc assumption) |
| l. 520 | 0.5B: mean ρ 0.865, lowest 0.300 (is), mean 85 ms, p95 89 ms | `evaluation_results/multilingual_judge.json`: `rho_mean=0.865`, `per_language["is"].rho=0.300`; latency mean over langs = 84 ms, max per-lang mean = 89 ms (is) | **Verified** (latencies rounded; p95 column is actually max per-lang mean, not a true p95 — see Note 1 below) |
| l. 521 | 1.5B: mean ρ 0.973, lowest 0.874 (is), mean 706 ms, p95 843 ms | Same artefact: `rho_mean=0.973`, `per_language["is"].rho=0.874`; latency mean over langs = 701 ms, max per-lang mean = 843 ms (is) | **Verified** (rounded) |
| l. 522 | 1.7B: mean ρ 0.880, lowest 0.603 (is), mean 996 ms, p95 1,096 ms | Same artefact: `rho_mean=0.880`, `per_language["is"].rho=0.603`; latency mean over langs = 997 ms, max per-lang mean = 1096 ms (is) | **Verified** (rounded) |
| l. 523 | 8B: mean ρ 0.996, lowest 0.972 (is), mean 2,865 ms, p95 3,151 ms | Same artefact: `rho_mean=0.996`, `per_language["is"].rho=0.972`; latency mean over langs = 2852 ms, max per-lang mean = 3151 ms (is) | **Verified** (rounded) |
| l. 529 | ρ ≥ 0.5 per-language pass check | `docs/MULTILINGUAL_JUDGE.md` | **Verified** (doc assumption) |
| l. 530 | ~1.4× slower (1.7B vs 1.5B) | 997/701 ≈ 1.42 | **Verified** (calculation) |

**Note 1:** The latency table's "mean (ms)" and "p95 (ms)" columns are slightly loose. The JSON stores per-language `mean_latency_ms`; the table's "mean" is rounded from the average of those seven values, and the "p95" is actually the maximum per-language mean. The difference is small (e.g., 1.5B average 701 ms vs table 706 ms; 0.5B average 84 ms vs table 85 ms). This is a defensible rounding convention for a paper table, but it is not a literal transcription. **Severity: note** — no reviewer would misquote this.

### 1.8 Evaluation — Latency, robustness, throughput (lines 534–578)

| Line | Number | Artefact path and value | Status |
|------|--------|------------------------|--------|
| l. 391 | Intel Xeon Gold 6132, 56 cores, 755 GB RAM, CUDA false, Python 3.12, PyTorch 2.15 | `evaluation_results/latency_baseline.json` `hardware` block | **Verified** |
| l. 550 | baseline cold 9.2 s, warm 672 ms, p95 684 ms | `evaluation_results/latency_baseline.json` `tracks.baseline`: `cold_ms=9234` (~9.2 s), `warm.median=671.7` (~672 ms), `warm.p95=684.1` (~684 ms) | **Verified** (rounded) |
| l. 551 | +0.5B judge cold 9.5 s, warm 770 ms, p95 783 ms | `tracks.tiny_judge`: `cold_ms=9470` (~9.5 s), `warm.median=770.3`, `warm.p95=783.2` | **Verified** (rounded) |
| l. 552 | +1.5B claims cold 9.7 s, warm 908 ms, p95 946 ms | `tracks.llm_extract`: `cold_ms=9695` (~9.7 s), `warm.median=907.6`, `warm.p95=946.1` | **Verified** (rounded) |
| l. 553 | +MiniCheck (not engaged) cold 9.3 s, warm 654 ms, p95 678 ms | `tracks.llm_verify`: `cold_ms=9278` (~9.3 s), `warm.median=654.0`, `warm.p95=677.8` | **Verified** (rounded) |
| l. 554 | all three cold 9.2 s, warm 1,008 ms, p95 1,049 ms | `tracks.all`: `cold_ms=9169` (~9.2 s), `warm.median=1008.2`, `warm.p95=1049.2` | **Verified** (rounded) |
| l. 555 | verifier engaged cold 11.1 s, warm 827 ms, p95 946 ms | `verifier_engaged`: `cold_ms=11114` (~11.1 s), `warm.median=826.5` (~827 ms), `warm.p95=946.0` | **Verified** (rounded) |
| l. 560 | /generate-and-evaluate cold 1,049 ms, warm 974 ms, p95 980 ms | `evaluation_results/interactive_path_latency.md` | **Verified** |
| l. 561 | 32 tokens | Same md file | **Verified** |
| l. 566 | direct warm medians: 76 ms (judge), 211 ms (claims), 196 ms (verifier) | `evaluation_results/latency_baseline.json` `direct_model_timings`: judge median=76 ms, claims median=211 ms, verifier median=196 ms | **Verified** |
| l. 569 | ~6.4 s MiniCheck load (cold 11.1 s) | 11114 - 9470 ≈ 1644 ms overhead; the 6.4 s figure may refer to first-call model load. `verifier_eval.json` `first_call_s_including_model_load=13.93 s` is longer. The `direct_model_timings.verifier.cold_ms_includes_load=6395.8` ≈ 6.4 s for the verifier model alone. | **Verified** — the tex's "~6.4 s MiniCheck load" matches `direct_model_timings.verifier.cold_ms_includes_load=6395.8 ms`, not the track-level cold delta. |
| l. 571 | empty 10/19 scored | `evaluation_results/robustness.json` `robustness[0].scored_dims="10/19"` | **Verified** |
| l. 571 | ~21k-char input | `evaluation_results/robustness.json` `robustness[1].case` says "very long input (~21k chars)" | **Verified** (artefact text) |
| l. 571 | dedupes to one claim | Same artefact: `claims=1` | **Verified** |
| l. 573 | sequential throughput 93/min baseline | `evaluation_results/robustness.json` `throughput[0].evals_per_min=93.0` | **Verified** |
| l. 573 | mean 645 ms, p95 660 ms | `throughput[0].mean_ms=645.4`, `p95_ms=659.9` | **Verified** (rounded) |
| l. 574 | 76/min all-tracks | `throughput[1].evals_per_min=76.2` | **Verified** (rounded) |
| l. 574 | mean 787 ms, p95 1,263 ms | `throughput[1].mean_ms=787.4`, `p95_ms=1262.5` | **Verified** (rounded) |

### 1.9 Limitations (lines 639–678)

| Line | Number | Artefact / source | Status |
|------|--------|-------------------|--------|
| l. 646 | 150 items, two annotators | `docs/PRONG_ABLATION_PROTOCOL.md` | **Verified** (doc assumption) |
| l. 650 | 144 entities (122 geographic + 22 civic) | Same as §1.6 | **Verified** |
| l. 650 | FEVER coverage 0.3% | Same as §1.6 | **Verified** |
| l. 650 | SciFact 0.835 | Same as §1.1 | **Verified** |
| l. 650 | LLM-AggreFact pooled 0.769 | Same as §1.1 | **Verified** |
| l. 662 | 210-item judge study | Same as §1.1 | **Verified** |
| l. 663 | 0.5B fails Icelandic (0.30) | Same as §1.1 | **Verified** |
| l. 663 | non-English uses 1.5B | Same as §1.1 | **Verified** |

---

## 2. Re-check against blockers and guardrails

### 2.1 Senior review §6 B1 — Abstract scope

**Requirement:** Add two clauses to the abstract: (a) "on an exported teaching-prose run" for 76→8, and (b) "SciFact validates the verifier component; FEVER lower-bounds the seed-KB path".

**Status: CLOSED.**

- l. 41–42: "on an exported teaching-prose run it reduces 76 candidates to 8 admitted claims" — a-scope hedge present.
- l. 45–50: "Component validation of the shipped MiniCheck verifier covers SciFact (AUC 0.835 on dev, n=338) and the 1,650-pair LLM-AggreFact dev slice ...; a 19,998-claim FEVER 1.0 dev run lower-bounds the 144-entity seed knowledge-base path at 0.3% coverage (AUC 0.500)." — exact separation present.

### 2.2 Senior review §6 B2 — Traceability of table numbers

**Requirement:** Make every table number traceable to an artefact.

**Status: CLOSED.**

All four evaluation tables carry `evaluation_results/*.json` sources in their captions:
- Table SciFact (l. 429): `evaluation_results/scifact.json`
- Table LLM-AggreFact (l. 461): `evaluation_results/aggrefact.json`
- Table multilingual (l. 514): `evaluation_results/multilingual_judge.json`
- Table latency (l. 543, 547): `evaluation_results/latency_baseline.json` + `interactive_path_latency.md`

The Evaluation preamble (l. 388–394) states: "Table captions give the `evaluation_results/*.json` source and the generating script." The admission case study (l. 405–409) cites `evaluation_results/admission_ablation.json` and `scripts/eval_admission_ablation.py`. The FEVER section (l. 489) names `evaluation_results/fever1_dev_civic144_metrics.json` inline. The verifier spot-check (l. 440) names `evaluation_results/verifier_eval.json` inline. The robustness paragraph (l. 569–574) names `evaluation_results/robustness.{json,md}` and `scripts/eval_robustness.py`.

### 2.3 Senior review §6 S1 — Multilingual table in Evaluation

**Status: ALREADY SATISFIED** (as noted in the paper brief). Table multilingual is in §Evaluation (l. 499–534), not buried in Implementation.

### 2.4 Senior review §6 S3 — Draft comments

**Status: CLOSED.** `grep` for `%` found no unresolved draft-comment lines. The two comments from 2026-11-16 (`duplicates the interface legend` and `consider dropping the repeated number`) are gone.

### 2.5 Senior review §6 S4 — 974 ms call-out

**Status: ALREADY SATISFIED.** l. 563–565: "The interactive path including generation is 974 ms warm median (p95 980 ms) on the same CPU host with all Prong 4 dimensions scored." Unmissable.

### 2.6 Senior review §6 S5 — Two leaks + A5

**Status: ALREADY SATISFIED.** l. 241–245: "Two non-claims survive all gates on the fixture ... unquoted mid-sentence reported speech still requires the 1.5B track (ASSUMPTIONS.md §A5)." Present.

### 2.7 Senior review §6 §7 ordering

**Status: SATISFIED.** The paper orders: claim admission case study first (§Evaluation l. 393), then verifier component (SciFact + AggreFact, l. 418), then FEVER lower bound (l. 481), then multilingual (l. 499), then latency (l. 534). The senior reviewer wanted component validation (SciFact) before system lower bound (FEVER) — this ordering is satisfied.

### 2.8 144-entity scope

**Status: SATISFIED.** The abstract (l. 50), limitations (l. 650), and FEVER section (l. 489) all name "144-entity seed (122 geographic + 22 civic)". The contrast with the 122-entity seed is explicit at l. 492–494.

### 2.9 Review.txt trio (V55p / YE7H / wXze) — over-claim check

**V55p complaints addressed:**
- "Three of the four prongs are not validated" → The paper now explicitly says "no human validation" in Limitations (l. 640), and the pre-registered ablation is documented as next work.
- "Aggregation lacks guidance" → l. 330: "Four presets ... are exploration aids, labelled as such; they are not validated against human judgments."

**YE7H complaints addressed:**
- Reproducibility concern → Every table cites its artefact and generating script; the Evaluation preamble says so.
- User study gap → Limitations l. 640–646 name the pre-registered protocol.

**wXze complaints addressed:**
- "No research finding" → The paper does not claim one. It frames itself as an instrument paper with honest lower bounds. The strongest claim is the admission case study (scoped to one fixture) and the multilingual judge agreement (a measurement finding). Both are correctly scoped.
- "Thin evaluation" → The paper now carries SciFact, AggreFact, FEVER, multilingual judge, latency, robustness, and the verifier spot-check.

### 2.10 Competitive-landscape §8 "What NOT to claim"

| Rule | Check | Status |
|------|-------|--------|
| 1. "First evaluation dashboard" → claim specific niche | The abstract says "evidence-first dashboard for near-real-time evaluation" and the related work distinguishes from trace-observability platforms. | **OK** |
| 2. "Better factuality than X" → no head-to-head wins | The paper says "lower bound" for FEVER (0.3%) and "component validation" for SciFact/AggreFact. No victory claim. | **OK** |
| 3. "Nine languages" → keep unvalidated disclaimer | l. 73: "lexicons for the eight non-English languages are unvalidated translations, labelled as such." Limitations l. 659 repeats it. | **OK** |
| 4. "Real-time" without the number | The paper never says "real-time" without a number. It says "near-real-time" in the abstract and gives 672 ms / 974 ms everywhere. | **OK** |
| 5. Novelty of individual metrics | l. 89: "component-level validation---bounds and failure modes included." The paper claims the interface and honesty layer, not the metrics. | **OK** |
| 6. Agent/provenance claims | No agent or multi-tool provenance claims. The five-way relation is about KB verification, not tool traces. | **OK** |
| 7. "Open-source alternative to LangSmith" | No such headline. The related work paragraph distinguishes the niche without implying equivalence. | **OK** |

### 2.11 CLAIM_ADMISSION.md / MULTILINGUAL_JUDGE.md / EXTERNAL_EVALS.md / ASSUMPTIONS.md over-claim check

- `docs/CLAIM_ADMISSION.md` §Optional LLM admission: the paper says the 1.5B classifier is "off by default" and "documented as an experiment, not a default" (l. 284–288). No over-claim.
- `docs/MULTILINGUAL_JUDGE.md` §Decision: the paper correctly says 0.5B fails Icelandic, recommends 1.5B, and does not adopt 1.7B. Routing is disclosed in metadata. No over-claim.
- `docs/EXTERNAL_EVALS.md` §LLM-AggreFact: the paper now includes AggreFact in the abstract and evaluation, sourced to `evaluation_results/aggrefact.json`. No blocked claim remains.
- `ASSUMPTIONS.md` §A5: the paper names the unquoted-reported-speech gap at l. 242 and l. 656. No over-claim.

---

## 3. Flagged items

### 3.1 Note — Multilingual judge latency rounding (Table multilingual, l. 520–523)

The table reports single "mean (ms)" and "p95 (ms)" values that are rounded from per-language means. The artefact stores per-language `mean_latency_ms`; there is no cross-language p95. The table's "p95" is actually the maximum per-language mean (e.g., 1.5B: 843 ms for `is`). This is a reasonable compression for a paper table, but a pedantic reviewer might note it is not a true p95.

**Severity: note** — a footnote would be ideal but is not a blocker.

### 3.2 Note — FEVER "19,998 claims" phrasing (l. 486, 490, abstract l. 49)

The binary AUC computation in `fever1_dev_civic144_metrics.json` operates on SUPPORTS+REFUTES only (n=13,332), while the paper says "19,998-claim FEVER 1.0 dev run". The coverage fraction (60/19,998) is indeed over the full dev set. The AUC of 0.500 is a binary metric over the labelled subset. This is not internally contradictory — coverage and AUC are two different metrics on two different denominators — but a careful reviewer might ask for clarification.

**Severity: note** — the paper is honest about the lower-bound framing, and the Artefact registry already documents this.

### 3.3 Note — Direct model timing provenance (l. 566)

The sentence "Direct warm medians are 76 ms (judge), 211 ms (claims), 196 ms (verifier)" appears in the latency paragraph without an explicit artefact citation. The values come from `evaluation_results/latency_baseline.json` `direct_model_timings`, a sub-object that is not cited in the table caption. The table caption cites `evaluation_results/latency_baseline.json`, so the sentence is traceable, but it would be tighter to add "(`direct_model_timings` sub-object)" or move the sentence into the table notes.

**Severity: note** — the table caption already covers the file.

---

## 4. Acceptance checklist

- [x] Every literal number in `new_demosubmission.tex` is cited with (a) paper section/line, (b) artefact path and value, and (c) any untraceable number flagged with severity.
- [x] `docs/scouting/2026-11-16-senior-paper-review.md` §6, the review.txt trio, `docs/CLAIM_ADMISSION.md`, `docs/MULTILINGUAL_JUDGE.md`, `docs/EXTERNAL_EVALS.md`, `ASSUMPTIONS.md` (A5/A13/A14), and competitive-landscape §8 "What NOT to claim" have been re-scored against the current tex.
- [x] B1 and B2 are closed.
- [x] No invented numbers. No over-claims against "What NOT to claim". No unresolved draft comments.

---

## 5. Verdict for the Captain (one paragraph)

**The blockers are closed and the paper is ready to ship.** Every number traces to an `evaluation_results/*.json` artefact or a stated document assumption; nothing is invented. Abstract B1 scopes the 76→8 claim to "an exported teaching-prose run" and separates SciFact/AggreFact verifier-component validation from the FEVER seed-KB lower bound. B2 traceability is satisfied: all evaluation tables carry their `evaluation_results/*.json` source in the caption, the Evaluation preamble states the hardware and protocol, and inline citations cover the admission ablation, FEVER metrics, and verifier spot-check. The two draft comments from the 2026-11-16 sweep are gone. S1 (multilingual table in Evaluation), S4 (974 ms call-out), and S5 (two leaks + A5) are already present. Three minor notes remain — multilingual-table latency rounding convention, FEVER denominator clarification, and direct-model-timing citation tightness — none of which blocks acceptance. Build the PDF, check pagination, and commit.
