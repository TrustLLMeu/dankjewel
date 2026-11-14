#!/usr/bin/env python3
"""Discriminative-signal evaluation for the Prong 3 MiniCheck verifier (V55p).

Scores each pair's claim against its subject's formatted seed-KB facts
with the NliVerifier (lytang/MiniCheck-Flan-T5-Large, 770M, CPU) and
reports:

  - five-way accuracy at the product thresholds (p >= 0.8 supported,
    p <= 0.2 refuted, else partially_supported)
  - binary AUC over true-vs-false pairs (partials excluded)
  - a per-pair table (score, predicted, expected, latency)
  - mean per-pair latency

Pair sources:
  - data/benchmark_claims.json — the repo's labeled benchmark claims
    (ground_truth true/false; the hedged null claims are excluded).
    The subject for the KB document comes from the repo's own spaCy
    triple extractor.
  - data/verifier_eval.json — authored false/partial pairs about
    seed-DB entities (see that file's header note: authored for this
    PoC, not a public benchmark).

Both sets are small and partly authored — this is discriminative-
signal evidence for the five-way track, not a public-benchmark claim.
Like the FEVER numbers, coverage is bounded by the seed KB: a claim
about a fact the KB does not store cannot be supported by its
document.

Outputs (gitignored):
  evaluation_results/verifier_eval.json
  evaluation_results/verifier_eval.md

Usage:
    python scripts/eval_verifier.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from src.extraction.claim_extractor import ClaimExtractor
from src.resources.nli_verifier import NliVerifier, VerifierUnavailableError
from src.resources.wikidata_offline import OfflineWikidata

BENCHMARK_PATH = Path("data/benchmark_claims.json")
AUTHORED_PATH = Path("data/verifier_eval.json")
OUTPUT_DIR = Path("evaluation_results")
JSON_OUT = OUTPUT_DIR / "verifier_eval.json"
MD_OUT = OUTPUT_DIR / "verifier_eval.md"

CONFIRM_THRESHOLD = 0.8
DENY_THRESHOLD = 0.2

# Map the author's expected labels to the five-way relation names.
EXPECTED_TO_RELATION = {
    "supported": "confirmed",
    "refuted": "denied",
    "partial": "partially_supported",
}


def load_pairs():
    """Assemble (id, claim, subject, expected) pairs from both sources."""
    pairs = []

    benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    extractor = ClaimExtractor()
    for row in benchmark:
        if row.get("ground_truth") is None:
            continue  # hedged claims have no usable label
        triples = extractor.extract(row["claim"]).claims
        if not triples:
            print(f"  [skip] {row['id']}: no triple extracted for the subject")
            continue
        expected = "supported" if row["ground_truth"] else "refuted"
        pairs.append({
            "id": row["id"],
            "claim": row["claim"],
            "subject": triples[0].subject,
            "expected": expected,
            "source": "benchmark",
        })

    authored = json.loads(AUTHORED_PATH.read_text(encoding="utf-8"))
    for row in authored["pairs"]:
        pairs.append({
            "id": row["id"],
            "claim": row["claim"],
            "subject": row["subject"],
            "expected": row["expected"],
            "source": "authored",
        })
    return pairs


def predict_relation(p):
    """Map a verifier support probability to the five-way relation."""
    if p >= CONFIRM_THRESHOLD:
        return "confirmed"
    if p <= DENY_THRESHOLD:
        return "denied"
    return "partially_supported"


def manual_auc(pos_scores, neg_scores):
    """AUC by concordant/discordant pairs (same method as eval_fever2.py)."""
    concordant = discordant = ties = 0
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
        return None
    return (concordant + 0.5 * ties) / total


def main():
    wikidata = OfflineWikidata()
    pairs = load_pairs()
    print(f"Loaded {len(pairs)} labeled pairs "
          f"({sum(1 for p in pairs if p['source'] == 'benchmark')} benchmark, "
          f"{sum(1 for p in pairs if p['source'] == 'authored')} authored).")

    # Format each pair's grounding document; drop pairs with no KB facts.
    scored, no_facts = [], []
    for pair in pairs:
        qid = wikidata.lookup_entity(pair["subject"])
        doc = wikidata.format_entity_facts(qid) if qid else None
        if not doc:
            no_facts.append(pair)
            continue
        pair["doc"] = doc
        scored.append(pair)
    if no_facts:
        print(f"  [skip] {len(no_facts)} pairs with unresolved subject / no KB facts:")
        for p in no_facts:
            print(f"    {p['id']}: subject {p['subject']!r}")
    print(f"Scoring {len(scored)} pairs against their subjects' KB facts ...")

    verifier = NliVerifier()
    t_load = time.perf_counter()
    records = []
    try:
        for pair in scored:
            t0 = time.perf_counter()
            p = verifier.score(pair["claim"], pair["doc"])
            latency_ms = (time.perf_counter() - t0) * 1000.0
            predicted = predict_relation(p)
            expected = EXPECTED_TO_RELATION[pair["expected"]]
            records.append({
                "id": pair["id"],
                "source": pair["source"],
                "claim": pair["claim"],
                "subject": pair["subject"],
                "expected": pair["expected"],
                "expected_relation": expected,
                "verifier_score": round(p, 4),
                "predicted_relation": predicted,
                "correct": predicted == expected,
                "latency_ms": round(latency_ms, 1),
            })
    except VerifierUnavailableError as e:
        print(f"ERROR: verifier unavailable: {e}")
        sys.exit(1)
    warm_up = time.perf_counter() - t_load  # includes the one-time model load

    # ── Metrics ────────────────────────────────────────────────────────
    n = len(records)
    correct = sum(1 for r in records if r["correct"])
    accuracy = correct / n if n else None

    per_expected = {}
    for r in records:
        bucket = per_expected.setdefault(r["expected"], {"n": 0, "correct": 0})
        bucket["n"] += 1
        bucket["correct"] += 1 if r["correct"] else 0

    pos = [r["verifier_score"] for r in records if r["expected"] == "supported"]
    neg = [r["verifier_score"] for r in records if r["expected"] == "refuted"]
    partial = [r for r in records if r["expected"] == "partial"]
    auc = manual_auc(pos, neg) if pos and neg else None

    latencies = [r["latency_ms"] for r in records]
    mean_latency = sum(latencies) / len(latencies) if latencies else None

    summary = {
        "model": verifier.model_name,
        "thresholds": {"confirm": CONFIRM_THRESHOLD, "deny": DENY_THRESHOLD},
        "n_pairs": n,
        "n_benchmark": sum(1 for r in records if r["source"] == "benchmark"),
        "n_authored": sum(1 for r in records if r["source"] == "authored"),
        "skipped_no_facts": [p["id"] for p in no_facts],
        "five_way_accuracy": accuracy,
        "per_expected": per_expected,
        "binary_auc": auc,
        "binary_auc_n": {"pos": len(pos), "neg": len(neg),
                          "partial_excluded": len(partial)},
        "mean_latency_ms": mean_latency,
        "first_call_s_including_model_load": round(warm_up, 2),
        "records": records,
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    JSON_OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")

    # ── Markdown report ─────────────────────────────────────────────────
    lines = [
        "# MiniCheck verifier evaluation (Prong 3 five-way track)",
        "",
        f"Model: `{verifier.model_name}` (Flan-T5-large, 770M, CPU) — "
        "official MiniCheck protocol, transformers, no new deps.",
        "",
        "Pair sources: `data/benchmark_claims.json` (labeled benchmark claims; "
        "hedged claims excluded) + `data/verifier_eval.json` (authored "
        "false/partial pairs about seed-DB entities — **authored for this "
        "PoC, not a public benchmark**). Each claim is scored against its "
        "subject's formatted seed-KB facts.",
        "",
        "Thresholds: p ≥ 0.8 → confirmed, p ≤ 0.2 → denied, else "
        "partially_supported.",
        "",
        "## Summary",
        "",
        f"- Five-way accuracy: **{accuracy:.3f}** ({correct}/{n})",
    ]
    if auc is not None:
        lines.append(f"- Binary AUC (supported vs refuted, partials excluded): "
                     f"**{auc:.3f}** (n_pos={len(pos)}, n_neg={len(neg)}, "
                     f"{len(partial)} partials excluded)")
    else:
        lines.append("- Binary AUC: not computable (one class empty)")
    lines += [
        f"- Mean latency: **{mean_latency:.0f} ms/pair** "
        f"(first call included the one-time model load; total {warm_up:.1f} s "
        "for load + all pairs)",
        "",
        "## Per-expected-class accuracy",
        "",
        "| Expected | n | correct | accuracy |",
        "|---|---|---|---|",
    ]
    for exp in ("supported", "refuted", "partial"):
        b = per_expected.get(exp)
        if not b:
            continue
        lines.append(f"| {exp} | {b['n']} | {b['correct']} | "
                     f"{b['correct'] / b['n']:.3f} |")
    lines += [
        "",
        "## Per-pair results",
        "",
        "| id | source | claim | subject | p | predicted | expected | correct | ms |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['id']} | {r['source']} | {r['claim']} | {r['subject']} | "
            f"{r['verifier_score']:.3f} | {r['predicted_relation']} | "
            f"{r['expected_relation']} | {'✓' if r['correct'] else '✗'} | "
            f"{r['latency_ms']:.0f} |")
    lines += [
        "",
        "## Caveats",
        "",
        "- The pairs are a small, partly authored PoC set — discriminative-"
        "signal evidence, not a public-benchmark claim.",
        "- The grounding documents are the seed KB's claim rows formatted as "
        "`<label> <predicate phrase> <value>.` lines; facts the seed does not "
        "store cannot support (or refute) a claim — the same honest lower "
        "bound as the FEVER coverage numbers.",
        "- Binary AUC uses the raw support probability; the five-way accuracy "
        "uses the 0.8/0.2 thresholds the product uses.",
        "",
    ]
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {MD_OUT}")

    # ── Console summary ─────────────────────────────────────────────────
    print("\n=== Verifier eval summary ===")
    print(f"  Model:            {verifier.model_name}")
    print(f"  Pairs scored:     {n} "
          f"({summary['n_benchmark']} benchmark + {summary['n_authored']} authored)")
    if no_facts:
        print(f"  Skipped (no KB facts): {len(no_facts)}")
    print(f"  Five-way accuracy: {accuracy:.3f} ({correct}/{n})")
    for exp in ("supported", "refuted", "partial"):
        b = per_expected.get(exp)
        if b:
            print(f"    {exp:<10} n={b['n']} correct={b['correct']}")
    if auc is not None:
        print(f"  Binary AUC (supported vs refuted): {auc:.3f} "
              f"(n_pos={len(pos)}, n_neg={len(neg)}, {len(partial)} partials excluded)")
    print(f"  Mean latency:     {mean_latency:.0f} ms/pair "
          f"(model load + all pairs: {warm_up:.1f} s)")


if __name__ == "__main__":
    main()
