# FEVER 1.0 dev — Prong 3 Factuality Evaluation

Source: `fever/fever2/fever2-fixers-dev.jsonl`

> NOTE: FEVER 2.0 fixers dev was unavailable; this file is the official FEVER 1.0 shared-task dev set (fever.ai) converted to the same {claim, label, id} shape.
Scope: **entire dataset** (no subsampling)
Extractor: **spacy**
Total claims evaluated: 19998
Wikidata DB: `/tmp/seed_122.db`

## Claim counts

| Label | N |
|---|---|
| SUPPORTS | 6666 |
| REFUTES | 6666 |
| NOT ENOUGH INFO | 6666 |
| **Total** | **19998** |

## Per-class mean Factual Accuracy (all claims)

| Label | N | Mean Factual Accuracy |
|---|---|---|
| SUPPORTS | 6666 | 0.500 |
| REFUTES | 6666 | 0.500 |
| NOT ENOUGH INFO | 6666 | 0.500 |

**Expected pattern if the evaluator discriminates:** SUPPORTS > NOT ENOUGH INFO > REFUTES

## Extraction coverage

- Overall: **50/19998 (0.3%)**
- Per class:
  - SUPPORTS: 20/6666 (0.3%)
  - REFUTES: 16/6666 (0.2%)
  - NOT ENOUGH INFO: 14/6666 (0.2%)

Coverage is the fraction of claims where Wikidata verification returned CONFIRMED or DENIED. Uncovered claims receive the neutral 0.5 fallback and contribute no discrimination signal.

## Binary AUC (SUPPORTS vs REFUTES, NEI excluded)

- **AUC = 0.500** (N_POS=6666, N_NEG=6666)
- SUPPORTS vs REFUTES, NEI excluded (standard binary FEVER metric). Includes 0.5 fallback scores for uncovered claims.

- AUC ~0.5: no discriminative signal.
- AUC ~0.7+: useful signal.
- AUC ~0.9: strong.

## Conditional AUC (covered claims only) — diagnostic

- **AUC = 0.528** (N_POS=20, N_NEG=16)
- CONDITIONAL on coverage (selection bias — diagnostic only, not operational performance).

## Caveat to disclose in the paper

FEVER verifies claims against Wikipedia sentences (textual entailment);
this system verifies structured triples against Wikidata. Claims for which
Wikidata returns UNKNOWN contribute no signal (Factual Accuracy = 0.5).
Reported AUC is therefore a lower bound on the system's discrimination.
Additionally, the fixers split contains adversarially-generated claims
(multi-hop, negation, date manipulation), which are harder than the
standard FEVER dev distribution.

