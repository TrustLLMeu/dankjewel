"""LLM-AggreFact verifier benchmark (second public benchmark).

Scores the shipped MiniCheck verifier on LLM-AggreFact (Tang et al., 2024),
a pooled benchmark of 11 human-labelled fact-verification datasets with
(document, claim) pairs.

STATUS: the HuggingFace dataset `lytang/LLM-AggreFact` is gated with
auto-approval. A valid HF token is required AND the account must accept the
dataset terms on the dataset page; otherwise the download fails with a 403
GatedRepoError. This script is ready to run once that one click is done.

Dependency: pyarrow is needed to read the parquet files. It is an optional
evaluation dependency, not part of the product runtime:
    .venv/bin/pip install pyarrow

Run from the repo root:
    .venv/bin/python scripts/eval_aggrefact.py [--split dev|test]
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from huggingface_hub import hf_hub_download

from src.resources.nli_verifier import NliVerifier

DATASET = "lytang/LLM-AggreFact"
RAW_DIR = Path("data/aggrefact_raw")
OUT_JSON = Path("evaluation_results/aggrefact.json")
OUT_MD = Path("evaluation_results/aggrefact.md")


def load_rows(split: str):
    import pyarrow.parquet as pq

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"data/{split}-00000-of-00001.parquet"
    path = hf_hub_download(DATASET, filename, repo_type="dataset",
                           local_dir=str(RAW_DIR))
    table = pq.read_table(path)
    return table.to_pylist()


def pick(row: dict, *names):
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def normalize(row: dict):
    document = pick(row, "document", "doc", "evidence", "context")
    claim = pick(row, "claim", "statement")
    label = pick(row, "label", "gold", "y")
    dataset = pick(row, "dataset", "source", "subset") or "pooled"
    if document is None or claim is None or label is None:
        return None
    try:
        label = int(label)
    except (TypeError, ValueError):
        return None
    if label not in (0, 1):
        return None
    return dataset, str(document), str(claim), label


def auc(labels, scores):
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return None
    wins = sum(1 for p in pos for n in neg if p > n) + 0.5 * sum(
        1 for p in pos for n in neg if p == n)
    return wins / (len(pos) * len(neg))


def group_summary(rows, scores, latencies):
    labels = [r[3] for r in rows]
    correct = sum((s >= 0.5) == (y == 1) for s, y in zip(scores, labels))
    lat = sorted(latencies)
    return {
        "n": len(rows),
        "accuracy": round(correct / len(rows), 4),
        "auc": round(auc(labels, scores), 4) if auc(labels, scores) is not None else None,
        "mean_latency_ms": round(statistics.mean(latencies), 1),
        "p95_latency_ms": round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 1),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev", choices=["dev", "test"])
    args = parser.parse_args()

    rows = [r for r in (normalize(raw) for raw in load_rows(args.split)) if r]
    if not rows:
        raise SystemExit("no (document, claim, label) rows found")

    verifier = NliVerifier()
    by_dataset = {}
    rows_all, scores_all, lat_all = [], [], []
    for dataset, document, claim, label in rows:
        t0 = time.perf_counter()
        score = verifier.score(claim, document)
        lat = (time.perf_counter() - t0) * 1000
        by_dataset.setdefault(dataset, {"rows": [], "scores": [], "lat": []})
        by_dataset[dataset]["rows"].append((dataset, document, claim, label))
        by_dataset[dataset]["scores"].append(score)
        by_dataset[dataset]["lat"].append(lat)
        rows_all.append((dataset, document, claim, label))
        scores_all.append(score)
        lat_all.append(lat)

    report = {"dataset": DATASET, "split": args.split, "model": "lytang/MiniCheck-Flan-T5-Large",
              "per_dataset": {}, "pooled": None}
    md = [f"# LLM-AggreFact verifier benchmark ({args.split})", "",
          f"Dataset: `{DATASET}` ({args.split}); model: `lytang/MiniCheck-Flan-T5-Large` "
          "via `src/resources/nli_verifier.py`. This validates the verifier "
          "component, not the seed-KB path.", "",
          "| Dataset | n | Accuracy @0.5 | AUC | Mean latency | p95 latency |",
          "|---|---|---|---|---|---|"]
    for dataset, data in sorted(by_dataset.items()):
        summary = group_summary(data["rows"], data["scores"], data["lat"])
        report["per_dataset"][dataset] = summary
        md.append(f"| {dataset} | {summary['n']} | {summary['accuracy']} | "
                  f"{summary['auc'] if summary['auc'] is not None else '—'} | "
                  f"{summary['mean_latency_ms']} ms | {summary['p95_latency_ms']} ms |")
    pooled = group_summary(rows_all, scores_all, lat_all)
    report["pooled"] = pooled
    md.append(f"| **pooled** | {pooled['n']} | {pooled['accuracy']} | "
              f"{pooled['auc'] if pooled['auc'] is not None else '—'} | "
              f"{pooled['mean_latency_ms']} ms | {pooled['p95_latency_ms']} ms |")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
