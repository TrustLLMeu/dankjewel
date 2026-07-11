#!/usr/bin/env python3
"""Evaluate Prong 3 factuality dimensions on the FEVER 2.0 fixers dev set.

By default runs the ENTIRE fever2-fixers-dev.jsonl (1174 claims).
Optionally subsample with --n-per-class N (0 = use all).

Can evaluate against either the default seed DB or a custom DB (e.g.,
the oracle-coverage DB built by scripts/build_fever_wikidata.py).

Outputs (suffix is empty for the default run, or the --output-suffix value):
  data/fever2_sample.jsonl                              — the claims evaluated
  evaluation_results/fever2[_suffix]_eval.json          — raw per-claim results
  evaluation_results/fever2[_suffix]_metrics.json       — computed metrics
  evaluation_results/fever2[_suffix]_eval_report.md     — human-readable report

Usage:
    python scripts/eval_fever2.py                                  # full dataset, seed DB
    python scripts/eval_fever2.py --n-per-class 30                 # subsample (90)
    python scripts/eval_fever2.py \
        --db-path data/wikidata_fever.db \
        --sample-path data/fever2_oracle_sample.jsonl \
        --output-suffix oracle                                      # oracle-coverage run

Requires the spaCy model:
    python -m spacy download en_core_web_sm

Cite: Aly, R., Guo, Z., Schlichtkrull, M.S., Thorne, J., Vlachos, A.,
Christodoulopoulos, C., Cocarascu, O., & Mittal, A. (2021).
FEVER 2.0: Fact Extraction and VERification 2.0.
"""
import argparse
import json
import os
import random
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline import EvaluationPipeline

FEVER2_PATH = "fever/fever2/fever2-fixers-dev.jsonl"
SAMPLE_PATH = "data/fever2_sample.jsonl"
OUTPUT_DIR = Path("evaluation_results")
RAW_PATH = OUTPUT_DIR / "fever2_eval.json"
METRICS_PATH = OUTPUT_DIR / "fever2_metrics.json"
REPORT_PATH = OUTPUT_DIR / "fever2_eval_report.md"

# Label normalization (FEVER 2.0 has inconsistent casing)
_LABEL_MAP = {
    "supports": "SUPPORTS",
    "refutes": "REFUTES",
    "refuted": "REFUTES",
    "not enough info": "NOT ENOUGH INFO",
}


def _normalize_label(raw):
    return _LABEL_MAP.get(raw.strip().lower(), raw.strip().upper())


def load_fever2(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if not obj.get("label") or not obj.get("claim"):
                continue  # skip malformed/empty rows
            obj["label"] = _normalize_label(obj["label"])
            rows.append(obj)
    return rows


def select_claims(rows, n_per_class, seed=42):
    """Return all claims, or a balanced subsample if n_per_class > 0."""
    if n_per_class <= 0:
        print(f"  Using ALL {len(rows)} claims (no subsampling)")
        return rows
    by_label = defaultdict(list)
    for r in rows:
        by_label[r["label"]].append(r)
    rng = random.Random(seed)
    sample = []
    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        pool = by_label.get(label, [])
        rng.shuffle(pool)
        taken = pool[:n_per_class]
        sample.extend(taken)
        print(f"  {label}: {len(taken)} sampled (of {len(pool)} available)")
    return sample


def save_claims(claims, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for row in claims:
            f.write(json.dumps(row) + "\n")
    print(f"Saved {len(claims)} claims to {path}")


def load_claims(path):
    claims = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                claims.append(json.loads(line))
    return claims


def _iter_dimensions(result):
    """Yield dimensions from either a pipeline dict or a direct ProngResult dict.

    The pipeline wraps results as {"prong_results": [{dimensions: [...]}]}.
    Prong3Extraction.evaluate() returns a ProngResult whose to_dict() is
    {"dimensions": [...]}. This helper handles both.
    """
    if "prong_results" in result:
        for prong in result["prong_results"]:
            for d in prong.get("dimensions", []):
                yield d
    else:
        for d in result.get("dimensions", []):
            yield d


def get_dim_value(result, name):
    """Extract a dimension score (0-1) from a result dict, or None."""
    for d in _iter_dimensions(result):
        if d.get("name") == name:
            return d.get("value")
    return None


def get_coverage_info(result):
    """Check whether Prong 3 produced any verifiable claims (coverage)."""
    for d in _iter_dimensions(result):
        if d.get("name") == "Factual Accuracy":
            meta = d.get("metadata", {})
            return meta.get("verifiable", 0) > 0, meta.get("num_claims", 0)
    return False, 0


def evaluate(claims, evaluator):
    """Evaluate claims using either the full pipeline or a direct Prong3Extraction."""
    records = []
    total = len(claims)
    for i, item in enumerate(claims, 1):
        text = item["claim"]
        label = item["label"]
        try:
            result = evaluator.evaluate(text)
            if hasattr(result, "to_dict"):
                result = result.to_dict()
            factual = get_dim_value(result, "Factual Accuracy")
            covered, n_claims = get_coverage_info(result)
        except Exception as e:
            factual = None
            covered = False
            n_claims = 0
        records.append({
            "id": item.get("id"),
            "claim": text,
            "label": label,
            "factual_accuracy": factual,
            "covered": covered,
            "num_claims_extracted": n_claims,
        })
        if i % 50 == 0 or i == total:
            print(f"  [{i}/{total}] {label:<18} factual={factual} "
                  f"claims={n_claims} covered={covered}")
    return records


def manual_auc(pos_scores, neg_scores):
    """Compute AUC by counting concordant/discordant pairs (no sklearn)."""
    concordant = 0
    discordant = 0
    ties = 0
    for p in pos_scores:
        for n in neg_scores:
            if p > n:
                concordant += 1
            elif p < n:
                discordant += 1
            else:
                ties += 1
    total = concordant + discordant + ties
    if total == 0:
        return 0.5
    return (concordant + 0.5 * ties) / total


def compute_metrics(records):
    metrics = {
        "counts": {},
        "by_class": {},
        "coverage": {},
        "binary_auc": {},
        "conditional_auc": {},
    }

    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        metrics["counts"][label] = sum(1 for r in records if r["label"] == label)
    metrics["counts"]["total"] = len(records)

    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        scores = [r["factual_accuracy"] for r in records
                  if r["label"] == label and r["factual_accuracy"] is not None]
        if scores:
            metrics["by_class"][label] = {
                "n": len(scores),
                "mean_factual_accuracy": sum(scores) / len(scores),
            }
        else:
            metrics["by_class"][label] = {"n": 0, "mean_factual_accuracy": None}

    covered = sum(1 for r in records if r["covered"])
    metrics["coverage"] = {
        "covered": covered,
        "total": len(records),
        "fraction": covered / len(records) if records else 0.0,
    }

    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        cls = [r for r in records if r["label"] == label]
        cls_cov = sum(1 for r in cls if r["covered"])
        metrics["coverage"][label] = {
            "covered": cls_cov,
            "total": len(cls),
            "fraction": cls_cov / len(cls) if cls else 0.0,
        }

    pos = [r["factual_accuracy"] for r in records
           if r["label"] == "SUPPORTS" and r["factual_accuracy"] is not None]
    neg = [r["factual_accuracy"] for r in records
           if r["label"] == "REFUTES" and r["factual_accuracy"] is not None]
    if pos and neg:
        metrics["binary_auc"] = {
            "n_pos": len(pos),
            "n_neg": len(neg),
            "auc": manual_auc(pos, neg),
            "note": "SUPPORTS vs REFUTES, NEI excluded (standard binary FEVER metric). "
                    "Includes 0.5 fallback scores for uncovered claims.",
        }
    else:
        metrics["binary_auc"] = {"auc": None, "note": "insufficient data"}

    pos_cov = [r["factual_accuracy"] for r in records
               if r["label"] == "SUPPORTS" and r["covered"]
               and r["factual_accuracy"] is not None]
    neg_cov = [r["factual_accuracy"] for r in records
               if r["label"] == "REFUTES" and r["covered"]
               and r["factual_accuracy"] is not None]
    if pos_cov and neg_cov:
        metrics["conditional_auc"] = {
            "n_pos": len(pos_cov),
            "n_neg": len(neg_cov),
            "auc": manual_auc(pos_cov, neg_cov),
            "note": "CONDITIONAL on coverage (selection bias — diagnostic only, "
                    "not operational performance).",
        }
    else:
        metrics["conditional_auc"] = {
            "n_pos": len(pos_cov),
            "n_neg": len(neg_cov),
            "auc": None,
            "note": "cannot compute (one class has 0 covered claims)",
        }

    return metrics


def write_report(records, metrics, n_per_class, db_source):
    lines = []
    lines.append("# FEVER 2.0 — Prong 3 Factuality Evaluation")
    lines.append("")
    lines.append(f"Source: `fever/fever2/fever2-fixers-dev.jsonl`")
    if n_per_class > 0:
        lines.append(f"Sample: {n_per_class} per class (seed=42)")
    else:
        lines.append("Scope: **entire dataset** (no subsampling)")
    lines.append(f"Total claims evaluated: {metrics['counts']['total']}")
    lines.append(f"Wikidata DB: `{db_source}`")
    if "oracle" in db_source.lower() or "fever" in db_source.lower():
        lines.append("")
        lines.append("> **NOTE:** This is an **oracle coverage** evaluation. The "
                     "Wikidata DB was built from FEVER evidence annotations, so "
                     "the verifier has access to exactly the entities needed. "
                     "This is diagnostic only — not operational performance.")
    lines.append("")
    lines.append("## Claim counts")
    lines.append("")
    lines.append("| Label | N |")
    lines.append("|---|---|")
    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        lines.append(f"| {label} | {metrics['counts'][label]} |")
    lines.append(f"| **Total** | **{metrics['counts']['total']}** |")
    lines.append("")
    lines.append("## Per-class mean Factual Accuracy (all claims)")
    lines.append("")
    lines.append("| Label | N | Mean Factual Accuracy |")
    lines.append("|---|---|---|")
    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        m = metrics["by_class"][label]
        mean = m["mean_factual_accuracy"]
        mean_str = f"{mean:.3f}" if mean is not None else "n/a"
        lines.append(f"| {label} | {m['n']} | {mean_str} |")
    lines.append("")
    lines.append("**Expected pattern if the evaluator discriminates:** "
                "SUPPORTS > NOT ENOUGH INFO > REFUTES")
    lines.append("")
    lines.append("## Extraction coverage")
    lines.append("")
    cov = metrics["coverage"]
    lines.append(f"- Overall: **{cov['covered']}/{cov['total']} "
                 f"({cov['fraction']*100:.1f}%)**")
    lines.append("- Per class:")
    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        c = cov[label]
        lines.append(f"  - {label}: {c['covered']}/{c['total']} "
                     f"({c['fraction']*100:.1f}%)")
    lines.append("")
    lines.append("Coverage is the fraction of claims where Wikidata verification "
                "returned CONFIRMED or DENIED. Uncovered claims receive the "
                "neutral 0.5 fallback and contribute no discrimination signal.")
    lines.append("")
    lines.append("## Binary AUC (SUPPORTS vs REFUTES, NEI excluded)")
    lines.append("")
    auc = metrics["binary_auc"]
    if auc.get("auc") is not None:
        lines.append(f"- **AUC = {auc['auc']:.3f}** "
                     f"(N_POS={auc['n_pos']}, N_NEG={auc['n_neg']})")
    else:
        lines.append("- AUC not computable (insufficient data).")
    lines.append(f"- {auc['note']}")
    lines.append("")
    lines.append("- AUC ~0.5: no discriminative signal.")
    lines.append("- AUC ~0.7+: useful signal.")
    lines.append("- AUC ~0.9: strong.")
    lines.append("")
    lines.append("## Conditional AUC (covered claims only) — diagnostic")
    lines.append("")
    cauc = metrics["conditional_auc"]
    if cauc.get("auc") is not None:
        lines.append(f"- **AUC = {cauc['auc']:.3f}** "
                     f"(N_POS={cauc['n_pos']}, N_NEG={cauc['n_neg']})")
    else:
        lines.append(f"- AUC not computable: {cauc['note']}")
    lines.append(f"- {cauc['note']}")
    lines.append("")
    lines.append("## Caveat to disclose in the paper")
    lines.append("")
    lines.append("FEVER verifies claims against Wikipedia sentences (textual entailment);")
    lines.append("this system verifies structured triples against Wikidata. Claims for which")
    lines.append("Wikidata returns UNKNOWN contribute no signal (Factual Accuracy = 0.5).")
    lines.append("Reported AUC is therefore a lower bound on the system's discrimination.")
    lines.append("Additionally, the fixers split contains adversarially-generated claims")
    lines.append("(multi-hop, negation, date manipulation), which are harder than the")
    lines.append("standard FEVER dev distribution.")
    lines.append("")
    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote report: {REPORT_PATH}")


def main():
    global RAW_PATH, METRICS_PATH, REPORT_PATH

    parser = argparse.ArgumentParser(description="Evaluate Prong 3 on FEVER 2.0")
    parser.add_argument("--n-per-class", type=int, default=0,
                        help="Claims per class to subsample (0 = use entire dataset, default)")
    parser.add_argument("--resample", action="store_true",
                        help="Re-select claims even if sample file exists")
    parser.add_argument("--db-path", default=None,
                        help="Path to a custom Wikidata SQLite DB (e.g., data/wikidata_fever.db). "
                             "If omitted, uses the default seed DB via the pipeline.")
    parser.add_argument("--sample-path", default=SAMPLE_PATH,
                        help="Path to read/save the claim sample (default: data/fever2_sample.jsonl)")
    parser.add_argument("--output-suffix", default="",
                        help="Suffix for output files (e.g., 'oracle' -> fever2_oracle_eval.json)")
    args = parser.parse_args()

    if args.output_suffix:
        RAW_PATH = OUTPUT_DIR / f"fever2_{args.output_suffix}_eval.json"
        METRICS_PATH = OUTPUT_DIR / f"fever2_{args.output_suffix}_metrics.json"
        REPORT_PATH = OUTPUT_DIR / f"fever2_{args.output_suffix}_eval_report.md"

    db_source = args.db_path if args.db_path else "data/wikidata_seed.db (default seed)"

    # Phase 1: select claims (or reuse existing)
    sample_path = args.sample_path
    if os.path.exists(sample_path) and not args.resample:
        print(f"Reusing existing claims at {sample_path}")
        claims = load_claims(sample_path)
    else:
        print(f"Loading FEVER 2.0 from {FEVER2_PATH} ...")
        rows = load_fever2(FEVER2_PATH)
        print(f"Loaded {len(rows)} claims. Selecting:")
        claims = select_claims(rows, args.n_per_class)
        save_claims(claims, sample_path)

    # Phase 2: evaluate
    print(f"\nEvaluating {len(claims)} claims with Prong 3 ...")
    if args.db_path:
        from src.prongs.prong3_extraction import Prong3Extraction
        print(f"Using custom Wikidata DB: {args.db_path}")
        evaluator = Prong3Extraction(wikidata_db_path=args.db_path)
    else:
        print("(Using default seed DB via pipeline)")
        evaluator = EvaluationPipeline(enable_prongs=[3])
    records = evaluate(claims, evaluator)

    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(RAW_PATH, "w") as f:
        json.dump(records, f, indent=2)
    print(f"Wrote raw results: {RAW_PATH}")

    # Phase 3: metrics + report
    metrics = compute_metrics(records)
    metrics["db_source"] = db_source
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    write_report(records, metrics, args.n_per_class, db_source)

    print("\n=== Summary ===")
    print(f"  Total claims:     {metrics['counts']['total']}")
    print(f"  Wikidata DB:      {db_source}")
    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        print(f"  {label:<18} n={metrics['counts'][label]}")
    print()
    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        m = metrics["by_class"][label]
        mean = m["mean_factual_accuracy"]
        mean_str = f"{mean:.3f}" if mean is not None else "n/a"
        print(f"  {label:<18} mean={mean_str}")
    cov = metrics["coverage"]
    print(f"\n  Coverage: {cov['covered']}/{cov['total']} "
          f"({cov['fraction']*100:.1f}%)")
    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        c = cov[label]
        print(f"    {label:<18} {c['covered']}/{c['total']} "
              f"({c['fraction']*100:.1f}%)")
    auc = metrics["binary_auc"]
    if auc.get("auc") is not None:
        print(f"\n  Binary AUC (SUPPORTS vs REFUTES, NEI excluded): {auc['auc']:.3f}")
    cauc = metrics["conditional_auc"]
    if cauc.get("auc") is not None:
        print(f"  Conditional AUC (covered only, diagnostic): {cauc['auc']:.3f}")
    else:
        print(f"  Conditional AUC: {cauc['note']}")


if __name__ == "__main__":
    main()