# Pre-registration: prong ablation against human ratings

**Status:** frozen protocol, not yet run. **Date:** 2026-11-16.
**Owner:** Captain (protocol); Eval Scientist (analysis); annotators (ratings).
**Why:** the senior review and the EMNLP 2026 reviews agree that the system's
weakest point is the absence of a tested research claim. This study supplies one
without changing the tool's runtime behaviour.

## Research question

Does the four-prong aggregate predict human judgments of text quality better
than any single prong, and does excluding missing evidence (the `unknown`
semantics) predict better than filling it with a neutral 0.5?

## Hypotheses (primary and secondary)

- **H1 (primary).** Spearman ρ between the aggregate score and the annotators'
  overall quality is greater than ρ for the best single prong.
- **H2 (primary).** The "honest" aggregate (unknown dimensions excluded and the
  prong average renormalized) predicts human overall quality better than the
  "filled" aggregate (unknown = 0.5) on items where at least one dimension is
  unknown.
- **H3 (secondary, construct validity).** Each prong correlates positively with
  its human dimension: Prong 1 with relevance/coherence, Prong 2 with fluency,
  Prong 3 with factuality, Prong 4 with fluency/confidence.

## Design

- **Items.** 150 English texts. Sampling frame: 50 prompts × 3 generators
  (Qwen2.5-0.5B, Qwen2.5-1.5B, Qwen3.8-27B, all local), temperature 0.7, max 256
  tokens, fixed seed; deduplicate near-identical outputs; stratify by generator
  (50 each) so quality and prong coverage vary. Store prompt, generator, and
  generation parameters with each item.
- **Scores.** Run the shipped pipeline once per item with all default tracks on
  and once with the optional tracks on (judge, claims, verifier); store the full
  `/evaluate` JSON and the evidence bundle. The annotators never see scores.
- **Annotators.** Two annotators per item, blind to each other and to the
  scores. Each rates overall quality and five dimensions on 1–5 Likert scales,
  with one-sentence justification for overall ≤2 or ≥5.
- **Instrument.** CSV: `item_id, annotator_id, overall_1_5, relevance_1_5,
  coherence_1_5, factuality_1_5, fluency_1_5, toxicity_1_5, notes, timestamp`.
  Use the `claims.csv` export to anchor factuality judgments when useful.
- **Adjudication.** Items with an overall-score gap ≥2 points get a third
  adjudicated rating; agreement is reported for the unadjudicated pairs.
- **Agreement.** Krippendorff's α (ordinal) per dimension; target ≥0.60. Report
  it regardless; α < 0.60 is a finding about the rubric, not a reason to hide.

## Analysis (pre-specified)

1. Item-level human score = mean of the two annotators (adjudicated where
   needed).
2. Spearman ρ (and Kendall τ as a robustness check) between each prong score,
   the honest aggregate, the filled aggregate, and human overall.
3. H1: paired bootstrap over items (10,000 resamples, fixed seed), 95% CI for
   Δρ = ρ(aggregate) − ρ(best single prong). Supported if the CI excludes 0 in
   the positive direction.
4. H2: same bootstrap on items with ≥1 unknown dimension; Δρ = ρ(honest) −
   ρ(filled). Supported if the CI excludes 0.
5. H3: per-prong correlations with their human dimension, with CIs.
6. Report n, missing data, per-generator subgroups, and all correlations
   including non-significant ones.

**Stopping rule.** No optional stopping; the analysis runs once on the frozen
150 items. Deviations are logged in this file with dates.

## Deliverables

- `data/ablation_annotations.csv` (adjudicated) and the raw per-annotator file.
- `scripts/analyze_prong_ablation.py` (pre-written; computes the table above and
  writes `evaluation_results/prong_ablation.{json,md}`).
- One paragraph and one table in the paper; the limitations section updated with
  the result either way.

## Ethics and data

Texts are model-generated from neutral prompts; no personal data is collected.
Annotators are informed of the task and compensated; ratings are stored without
identifiers beyond an annotator code. The generated texts and prompts are
released with the artifacts.

## Scope and known limits

English only, 150 items, two annotators. This is a small study; it can support a
claim about *relative* predictive value (H1/H2) but not absolute score
calibration. A multilingual extension (the seven judge languages) is a follow-up
once the English design is validated.
