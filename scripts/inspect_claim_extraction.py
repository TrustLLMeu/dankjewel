#!/usr/bin/env python3
"""Inspect claim extraction on benchmark_claims.json.

Runs the rule-based ClaimExtractor (spaCy) over every item in
data/benchmark_claims.json and writes a human-annotatable report so
the Prong 3 extraction quality can be measured by manual inspection.

Outputs:
  evaluation_results/claim_extraction_inspection.md  — annotatable report
  evaluation_results/claim_extraction_inspection.json — raw structured output

Usage:
    python scripts/inspect_claim_extraction.py

Requires the spaCy model:
    python -m spacy download en_core_web_sm
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.extraction.claim_extractor import ClaimExtractor

CLAIMS_PATH = "data/benchmark_claims.json"
OUTPUT_DIR = Path("evaluation_results")
MD_PATH = OUTPUT_DIR / "claim_extraction_inspection.md"
JSON_PATH = OUTPUT_DIR / "claim_extraction_inspection.json"


def main():
    with open(CLAIMS_PATH) as f:
        items = json.load(f)
    print(f"Loaded {len(items)} benchmark claims from {CLAIMS_PATH}")

    extractor = ClaimExtractor()
    print("spaCy model loaded.")

    records = []
    for item in items:
        text = item["claim"]
        result = extractor.extract(text)
        triples = [c.to_dict() for c in result.claims]
        records.append({
            "id": item["id"],
            "category": item["category"],
            "ground_truth": item["ground_truth"],
            "original_claim": text,
            "num_extracted": len(triples),
            "triples": triples,
            "extraction_time_ms": result.extraction_time_ms,
        })

    # Auto-summary (NOT a quality judgement — just whether triples came out)
    total = len(records)
    nonzero = sum(1 for r in records if r["num_extracted"] > 0)
    zero = total - nonzero
    print("\nSummary (recall: this is coverage, NOT correctness):")
    print(f"  total items:        {total}")
    print(f"  produced >=1 triple: {nonzero}/{total}")
    print(f"  produced 0 triples:  {zero}/{total}")

    OUTPUT_DIR.mkdir(exist_ok=True)

    # Raw structured output
    with open(JSON_PATH, "w") as f:
        json.dump(records, f, indent=2)

    # Human-annotatable markdown report
    lines = []
    lines.append("# Claim Extraction — Manual Inspection")
    lines.append("")
    lines.append(f"Source: `{CLAIMS_PATH}` ({total} items)")
    lines.append("Extractor: `src/extraction/claim_extractor.py` (spaCy `en_core_web_sm`)")
    lines.append("")
    lines.append("## Auto-summary")
    lines.append("")
    lines.append(f"- Items producing >=1 triple: **{nonzero}/{total}**")
    lines.append(f"- Items producing 0 triples:  **{zero}/{total}**")
    lines.append("- NOTE: '>=1 triple' does NOT mean correct. Annotate each row below.")
    lines.append("")
    lines.append("## Annotation instructions")
    lines.append("")
    lines.append("For each item, fill in:")
    lines.append("- **Correct?** = Y / N / partial")
    lines.append("- **Notes** = failure mode, e.g. 'inverted copula', 'missing object', "
                "'spurious subject', 'wrong predicate'")
    lines.append("")
    lines.append("Then count Y's to get the N/total number to cite in the paper's Limitations.")
    lines.append("")
    lines.append("## Per-item results")
    lines.append("")
    for r in records:
        lines.append(f"### {r['id']} — {r['category']} "
                     f"(ground_truth: {r['ground_truth']})")
        lines.append(f"- **Claim:** {r['original_claim']}")
        lines.append(f"- **Triples extracted:** {r['num_extracted']}")
        if r["num_extracted"] == 0:
            lines.append("  - _(none)_")
        else:
            for i, t in enumerate(r["triples"], 1):
                lines.append(f"  - Triple {i}:")
                lines.append(f"    - subject: `{t['subject']}`")
                lines.append(f"    - predicate: `{t['predicate']}`")
                lines.append(f"    - object: `{t['object']}`")
                lines.append(f"    - modifiers: {t['modifiers']}")
                lines.append(f"    - temporal_anchor: `{t['temporal_anchor']}`")
                lines.append(f"    - comparative_tag: `{t['comparative_tag']}`")
        lines.append(f"- **Correct?** [ ]")
        lines.append(f"- **Notes:**")
        lines.append("")

    with open(MD_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nWrote:")
    print(f"  {MD_PATH}  (annotatable report)")
    print(f"  {JSON_PATH} (raw structured output)")


if __name__ == "__main__":
    main()
