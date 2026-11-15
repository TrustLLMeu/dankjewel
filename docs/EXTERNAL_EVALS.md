# External and blocked work

Status of the items that depend on data, participants or infrastructure outside
this repository. None of them is silently claimed as done.

## LLM-AggreFact (second factuality benchmark)

- **Status: blocked on one account action.** The HuggingFace dataset
  `lytang/LLM-AggreFact` is gated with auto-approval (`gated: auto`). The
  machine's HF token is valid (authenticated as `larsbun`), but the account has
  not accepted the dataset terms, so downloads return `403 GatedRepoError`.
- **Ready when unblocked:** `scripts/eval_aggrefact.py` downloads the dev/test
  parquet, scores the shipped MiniCheck verifier per sub-dataset and pooled, and
  writes `evaluation_results/aggrefact.{json,md}`. It needs
  `pip install pyarrow` (an optional evaluation dependency).
- **To unblock:** open <https://huggingface.co/datasets/lytang/LLM-AggreFact>,
  accept the terms once, then run
  `.venv/bin/python scripts/eval_aggrefact.py --split dev`.
- The paper currently uses SciFact as the second benchmark and names
  LLM-AggreFact as gated; an AggreFact row can be added in a revision once the
  terms are accepted.

## AVeriTeC

- **Status: not attempted.** The shared-task release includes a knowledge store
  of several gigabytes and requires retrieval over it; that is a dedicated slice
  (download, index, retrieval, claim→evidence mapping), not a quick run.
- **Recommendation:** keep SciFact as the component benchmark and treat AVeriTeC
  as future work; use the same `NliVerifier` interface when it is added.

## Seed knowledge-base scale

- **Status: known limitation, Phase 2.** The seed has 122 entities; FEVER
  coverage is 4/1,174 claims (0.3%) with AUC 0.497. The verifier is validated as
  a component (SciFact AUC 0.835); the KB path is reported as a lower bound.
- **What it needs:** an at-scale Wikidata mirror (dump ingestion plus a property
  whitelist), which is the Phase-2 plan. No shortcut is available that would
  keep the honest semantics.

## Human-annotation study, user study, research claim

- **Status: not run; requires participants.** The system exports the inputs the
  study needs (the signal matrix, claim details, per-track values, history).
- **Suggested design:** 150 items per prong, two annotators, Krippendorff's
  alpha for agreement, Spearman correlation between dimension scores and human
  ratings; report per-prong correlation and the aggregation-weight sensitivity.
  A user study should measure whether the evidence panels change revision
  decisions, not only satisfaction.
- **What we may claim today:** the dimensions are implemented and documented; the
  aggregation presets are exploration aids; no human validation has been run.
  This is stated in the README and the paper's limitations section.
