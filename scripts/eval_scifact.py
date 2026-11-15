"""SciFact verifier benchmark — public, ungated second benchmark.

Scores (evidence sentence(s), claim) pairs from SciFact (Wadden et al.,
EMNLP 2020) with the SAME MiniCheck verifier the product ships
(src/resources/nli_verifier.py). This validates the verifier *component*
on human-labelled data; it does not exercise the 122-entity seed KB.

Data: https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz
(extracted to data/scifact_raw/data by the Captain; the raw tree is
gitignored). Pairs are built from every evidence annotation whose label is
SUPPORT or REFUTE, using the cited abstract sentences as the context.
NOT_ENOUGH_INFO claims carry no labelled evidence and are excluded.

Outputs:
  evaluation_results/scifact.json
  evaluation_results/scifact.md

Run from the repo root:
    .venv/bin/python scripts/eval_scifact.py
"""

import hashlib
import json
import time
from pathlib import Path

from sklearn.metrics import roc_auc_score

from src.resources.nli_verifier import NliVerifier

RAW = Path("data/scifact_raw/data")
OUT_JSON = Path("evaluation_results/scifact.json")
OUT_MD = Path("evaluation_results/scifact.md")
SOURCE_URL = "https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz"
FILES = ("corpus.jsonl", "claims_dev.jsonl", "claims_train.jsonl")


def load_corpus():
    corpus = {}
    with open(RAW / "corpus.jsonl", encoding="utf-8") as fh:
        for line in fh:
            doc = json.loads(line)
            corpus[str(doc["doc_id"])] = doc["abstract"]
    return corpus


def build_pairs(split, corpus):
    pairs = []
    with open(RAW / f"claims_{split}.jsonl", encoding="utf-8") as fh:
        for line in fh:
            claim = json.loads(line)
            for doc_id, evidences in claim.get("evidence", {}).items():
                abstract = corpus.get(str(doc_id))
                if abstract is None:
                    continue
                for ev in evidences:
                    label = ev.get("label")
                    # The current SciFact release uses SUPPORT/CONTRADICT
                    # (older releases: SUPPORT/REFUTE).
                    if label in ("SUPPORT", "REFUTE", "CONTRADICT"):
                        is_support = label == "SUPPORT"
                    else:
                        continue
                    sentences = ev.get("sentences") or []
                    context = " ".join(abstract[i] for i in sentences
                                      if 0 <= i < len(abstract))
                    if not context.strip():
                        continue
                    pairs.append({"claim": claim["claim"], "context": context,
                                  "label": 1 if is_support else 0,
                                  "scifact_label": label, "doc_id": doc_id})
    return pairs


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def summarize(pairs, scores, latencies):
    labels = [p["label"] for p in pairs]
    preds = [1 if s >= 0.5 else 0 for s in scores]
    correct = sum(p == y for p, y in zip(preds, labels))
    lat_sorted = sorted(latencies)
    p95 = lat_sorted[min(len(lat_sorted) - 1, int(0.95 * len(lat_sorted)))]
    return {
        "n": len(pairs),
        "accuracy": round(correct / len(pairs), 4),
        "auc": round(roc_auc_score(labels, scores), 4),
        "mean_latency_ms": round(sum(latencies) / len(latencies), 1),
        "p95_latency_ms": round(p95, 1),
    }, preds


def main():
    corpus = load_corpus()
    verifier = NliVerifier()
    report = {"provenance": {
        "source": SOURCE_URL,
        "downloaded": "2026-11-14",
        "sha256": {name: sha256(RAW / name) for name in FILES},
        "model": "lytang/MiniCheck-Flan-T5-Large",
    }, "splits": {}}
    md = ["# SciFact verifier benchmark", "",
          f"Source: `{SOURCE_URL}` (downloaded 2026-11-14); model: "
          "`lytang/MiniCheck-Flan-T5-Large` via `src/resources/nli_verifier.py`.", "",
          "Pairs: evidence-annotated (SUPPORT/CONTRADICT; REFUTE in older "
          "releases) claim–sentence pairs; NOT_ENOUGH_INFO claims excluded. "
          "This validates the verifier component, not the seed-KB path.", "",
          "| Split | n | Accuracy @0.5 | AUC | Mean latency | p95 latency |",
          "|---|---|---|---|---|---|"]
    for split in ("dev", "train"):
        pairs = build_pairs(split, corpus)
        scores, latencies = [], []
        for pair in pairs:
            t0 = time.perf_counter()
            scores.append(verifier.score(pair["claim"], pair["context"]))
            latencies.append((time.perf_counter() - t0) * 1000.0)
        summary, preds = summarize(pairs, scores, latencies)
        report["splits"][split] = summary
        md.append(f"| {split} | {summary['n']} | {summary['accuracy']} | "
                  f"{summary['auc']} | {summary['mean_latency_ms']} ms | "
                  f"{summary['p95_latency_ms']} ms |")
        print(f"{split}: {summary}")
    md += ["", "Both splits use the same thresholds as the product "
          "(p >= 0.5 counts as supported)."]
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {OUT_JSON} and {OUT_MD}")


if __name__ == "__main__":
    main()
