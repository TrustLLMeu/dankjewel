"""Admission ablation on the teacher-prose fixture.

Measures what each admission layer contributes, in pipeline order:

  A raw         spaCy triples from the uncleaned text, no gates
  B +markdown   markdown cleaning before parsing
  C +sentence   label/commentary handling and sentence admissibility
  D +triple     admit_triple (pronoun/malformed/definition/demonstrative)
  E +dedupe     filter_claims duplication removal
  F +use-mention full ClaimExtractor (adds quoted/labelled claims)

For each stage the table reports how many candidates it produced or kept,
how many of the five expected false-claim examples survive, and how many
known non-claims survive (markdown/pronoun fragments, the "smoking"
fragment, the advice sentence).

Outputs evaluation_results/admission_ablation.{json,md} (gitignored) and
prints the table. Run from the repo root:
    .venv/bin/python scripts/eval_admission_ablation.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.extraction.claim_admission import (
    admit_triple, clean_markdown, filter_claims, is_commentary_label,
    sentence_reject_reason, split_label,
)
from src.extraction.claim_extractor import ClaimExtractor

FIXTURE = Path("tests/fixtures/teacher_false_claims.json")
OUT_JSON = Path("evaluation_results/admission_ablation.json")
OUT_MD = Path("evaluation_results/admission_ablation.md")
EXPECTED = ["earth", "five eyes", "dentist", "crime", "boil"]


def claim_text(claim) -> str:
    return f"{claim.subject} {claim.predicate} {claim.object}".lower()


def expected_hits(claims) -> int:
    joined = " ".join(claim_text(c) for c in claims)
    return sum(1 for want in EXPECTED if want in joined)


def is_known_nonclaim(claim) -> bool:
    subj = (claim.subject or "").strip().lower()
    obj = (claim.object or "").strip().lower()
    if subj in {"*", "i", "it", "these", "this", "they", "we", "you"}:
        return True
    if subj.startswith("smoking") and "bad" in obj:
        return True
    if subj.startswith("critical thinking"):
        return True
    return False


def nonclaim_count(claims) -> int:
    return sum(1 for c in claims if is_known_nonclaim(c))


def parse_lines(extractor, cleaned, sentence_gate: bool):
    """Triples from cleaned lines; optionally drop inadmissible sentences."""
    out = []
    for raw_line in cleaned.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        label, content = split_label(line)
        if label is not None and is_commentary_label(label):
            continue
        parse_text = content if label is not None else line
        doc = extractor._nlp(parse_text)
        for sent in doc.sents:
            if sentence_gate and sentence_reject_reason(sent.text):
                continue
            out.extend(extractor._extract_from_sentence(sent))
    return out


def main():
    fixture = json.loads(FIXTURE.read_text())
    text = fixture["text"]
    extractor = ClaimExtractor()
    stages = []

    # A: raw, no gates
    raw = []
    for sent in extractor._nlp(text).sents:
        raw.extend(extractor._extract_from_sentence(sent))
    stages.append(("A raw", raw))

    # B: markdown cleaning
    cleaned = clean_markdown(text)
    stages.append(("B +markdown", parse_lines(extractor, cleaned, sentence_gate=False)))

    # C: sentence admissibility
    stages.append(("C +sentence", parse_lines(extractor, cleaned, sentence_gate=True)))

    # D: triple gates
    triple = [c for c in stages[-1][1] if admit_triple(c)[0]]
    stages.append(("D +triple", triple))

    # E: dedupe
    deduped, _ = filter_claims(triple)
    stages.append(("E +dedupe", deduped))

    # F: full extractor (use-mention pass included)
    stages.append(("F +use-mention", extractor.extract(text).claims))

    rows = []
    for name, claims in stages:
        rows.append({
            "stage": name,
            "claims": len(claims),
            "expected_of_5": expected_hits(claims),
            "known_nonclaims": nonclaim_count(claims),
        })

    report = {"fixture": str(FIXTURE), "stages": rows}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    md = ["# Admission ablation (teacher-prose fixture)", "",
          "Each row adds one layer to the pipeline above it. `expected_of_5` counts "
          "the five intended false-claim examples that survive; "
          "`known_nonclaims` counts the hand-labelled junk (markdown/pronoun "
          "fragments, the smoking fragment, the advice sentence).", "",
          "| Stage | Claims | Expected of 5 | Known non-claims |",
          "|---|---|---|---|"]
    for row in rows:
        md.append(f"| {row['stage']} | {row['claims']} | "
                  f"{row['expected_of_5']} | {row['known_nonclaims']} |")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
