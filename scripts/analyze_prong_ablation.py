"""Pre-specified analysis for the prong-ablation study.

Reads the adjudicated annotation CSV and a per-item scores JSON, then computes
the hypotheses frozen in docs/PRONG_ABLATION_PROTOCOL.md:

  H1  the aggregate predicts human overall quality better than the best prong
  H2  the honest aggregate (unknown excluded) beats the filled one (unknown=0.5)
  H3  each prong correlates with its human dimension

Outputs evaluation_results/prong_ablation.{json,md}. `--selftest` runs the whole
pipeline on synthetic data (no files needed) and writes to /tmp.

Input formats
-------------
annotations.csv: item_id, annotator_id, overall_1_5, relevance_1_5,
  coherence_1_5, factuality_1_5, fluency_1_5, toxicity_1_5, notes, timestamp.
  An optional row with annotator_id == "adjudicated" overrides the mean.
scores.json: {item_id: <the /evaluate response body>}

Run:
    .venv/bin/python scripts/analyze_prong_ablation.py \
        --annotations data/ablation_annotations.csv \
        --scores data/ablation_scores.json
"""

import argparse
import csv
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PRONGS = {
    "P1": "LLM-as-Judge",
    "P2": "Rule-Based",
    "P3": "Extraction-Based",
    "P4": "Intrinsic",
}
# Prong -> the human dimension it should predict (H3).
PRONG_DIMENSION = {
    "P1": "relevance_1_5",
    "P2": "fluency_1_5",
    "P3": "factuality_1_5",
    "P4": "coherence_1_5",
}
DIMENSION_KEYS = ["overall_1_5", "relevance_1_5", "coherence_1_5",
                  "factuality_1_5", "fluency_1_5", "toxicity_1_5"]


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = rank
        i = j + 1
    return out


def spearman(xs, ys):
    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) ** 0.5
           * sum((b - my) ** 2 for b in ry) ** 0.5)
    return None if den == 0 else num / den


def bootstrap_delta(items, score_a, score_b, human, n=10000, seed=20261116):
    """95% CI for rho(score_a, human) - rho(score_b, human) over items."""
    rng = random.Random(seed)
    deltas = []
    idx = list(range(len(items)))
    for _ in range(n):
        sample = [rng.choice(idx) for _ in idx]
        a = [score_a[i] for i in sample]
        b = [score_b[i] for i in sample]
        h = [human[i] for i in sample]
        ra, rb = spearman(a, h), spearman(b, h)
        if ra is not None and rb is not None:
            deltas.append(ra - rb)
    if not deltas:
        return {"delta": None, "ci95": [None, None], "n_resamples": 0}
    deltas.sort()
    lo = deltas[int(0.025 * len(deltas))]
    hi = deltas[int(0.975 * len(deltas)) - 1]
    return {"delta": round(statistics.mean(deltas), 3),
            "ci95": [round(lo, 3), round(hi, 3)],
            "n_resamples": len(deltas)}


def load_annotations(path):
    by_item = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            item = row["item_id"]
            entry = by_item.setdefault(item, {"annotators": [], "adjudicated": None})
            scores = {key: float(row[key]) for key in DIMENSION_KEYS
                      if row.get(key)}
            if row.get("annotator_id") == "adjudicated":
                entry["adjudicated"] = scores
            else:
                entry["annotators"].append(scores)
    human = {}
    for item, entry in by_item.items():
        source = ([entry["adjudicated"]] if entry["adjudicated"]
                  else entry["annotators"])
        if not source:
            continue
        human[item] = {key: statistics.mean(s[key] for s in source)
                       for key in DIMENSION_KEYS}
    return human


def prong_scores(result):
    """Per-prong scores and the honest aggregate from an /evaluate body."""
    scores = {}
    for prong in result.get("prong_results", []):
        name = prong.get("prong_name", "")
        key = next((k for k, v in PRONGS.items() if v in name), None)
        if key is None:
            continue
        dims = [d for d in prong.get("dimensions", []) if d.get("aggregate", True)]
        values = [d["value"] for d in dims
                  if d.get("status") == "scored" and d.get("value") is not None]
        scores[key] = statistics.mean(values) if values else None
    aggregated = (result.get("aggregated_scores") or {}).get("total_score")
    return scores, aggregated


def filled_aggregate(result):
    """Aggregate where unknown dimensions count as 0.5."""
    prong_values = []
    for prong in result.get("prong_results", []):
        dims = [d for d in prong.get("dimensions", []) if d.get("aggregate", True)]
        if not dims:
            continue
        vals = [d["value"] if d.get("status") == "scored" and d.get("value") is not None
                else 0.5 for d in dims]
        prong_values.append(statistics.mean(vals))
    return statistics.mean(prong_values) if prong_values else None


def analyze(human, scores):
    items = [i for i in human if i in scores]
    if len(items) < 10:
        raise SystemExit(f"only {len(items)} matched items; need >= 10")

    human_overall = [human[i]["overall_1_5"] for i in items]
    per_prong = {k: [prong_scores(scores[i])[0].get(k) for i in items]
                 for k in PRONGS}
    honest = [prong_scores(scores[i])[1] for i in items]
    filled = [filled_aggregate(scores[i]) for i in items]
    # Drop items missing the aggregate or a prong value, per comparison.
    def paired(*series):
        keep = [j for j in range(len(items)) if all(s[j] is not None for s in series)]
        return keep

    report = {"n_items": {}, "prongs": {}, "H1": {}, "H2": {}, "H3": {}}

    keep = paired(*[per_prong[k] for k in PRONGS], honest)
    report["n_items"]["all_prongs_and_aggregate"] = len(keep)
    for key in PRONGS:
        vals = [per_prong[key][j] for j in keep]
        y = [human_overall[j] for j in keep]
        report["prongs"][key] = round(spearman(vals, y), 3) if spearman(vals, y) is not None else None

    best_key = max((k for k in PRONGS if report["prongs"][k] is not None),
                   key=lambda k: report["prongs"][k])
    hv = [honest[j] for j in keep]
    hb = [per_prong[best_key][j] for j in keep]
    y = [human_overall[j] for j in keep]
    report["H1"] = {"best_prong": best_key,
                    "rho_aggregate": round(spearman(hv, y), 3),
                    "rho_best_prong": round(spearman(hb, y), 3),
                    "delta": bootstrap_delta(keep, hv, hb, y)}

    # H2: items with at least one unknown dimension.
    unknown_items = [j for j in range(len(items))
                     if any(per_prong[k][j] is None for k in PRONGS)
                     or (scores[items[j]].get("coverage") or {}).get("prongs_scored", 4) < 4]
    h2 = [j for j in unknown_items if honest[j] is not None and filled[j] is not None]
    if len(h2) >= 10:
        y2 = [human_overall[j] for j in h2]
        report["H2"] = {"n_items": len(h2),
                        "rho_honest": round(spearman([honest[j] for j in h2], y2), 3),
                        "rho_filled": round(spearman([filled[j] for j in h2], y2), 3),
                        "delta": bootstrap_delta(h2, [honest[j] for j in h2],
                                                 [filled[j] for j in h2], y2)}
    else:
        report["H2"] = {"n_items": len(h2), "note": "fewer than 10 items with unknown evidence"}

    for key, dimension in PRONG_DIMENSION.items():
        vals = [(per_prong[key][j], human[items[j]][dimension]) for j in keep
                if per_prong[key][j] is not None]
        rho = spearman([v for v, _ in vals], [h for _, h in vals])
        report["H3"][key] = {"target": dimension,
                             "rho": round(rho, 3) if rho is not None else None}

    return report


def write_report(report, out_json, out_md):
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md = ["# Prong ablation against human ratings", "",
          f"Matched items: {report['n_items']['all_prongs_and_aggregate']}", "",
          "| Prong | rho vs human overall |", "|---|---|"]
    for key in PRONGS:
        md.append(f"| {key} ({PRONGS[key]}) | {report['prongs'][key]} |")
    md += ["", "## Hypotheses", "",
           f"**H1** aggregate {report['H1']['rho_aggregate']} vs best prong "
           f"{report['H1']['best_prong']} {report['H1']['rho_best_prong']}; "
           f"delta {report['H1']['delta']['delta']} "
           f"CI {report['H1']['delta']['ci95']}.",
           f"**H2** honest {report['H2'].get('rho_honest')} vs filled "
           f"{report['H2'].get('rho_filled')} on {report['H2'].get('n_items')} items; "
           f"delta {report['H2'].get('delta', {}).get('delta')} "
           f"CI {report['H2'].get('delta', {}).get('ci95')}.",
           "", "## H3 (construct validity)", "", "| Prong | dimension | rho |", "|---|---|---|"]
    for key, value in report["H3"].items():
        md.append(f"| {key} | {value['target']} | {value['rho']} |")
    out_md.write_text("\n".join(md) + "\n", encoding="utf-8")


def selftest():
    rng = random.Random(7)
    human, scores = {}, {}
    for i in range(60):
        latent = rng.gauss(3.5, 0.9)
        item = f"item{i}"
        human[item] = {key: max(1, min(5, latent + rng.gauss(0, 0.4)))
                       for key in DIMENSION_KEYS}
        prongs = []
        for key, name in PRONGS.items():
            value = max(0, min(1, (latent - 1) / 4 + rng.gauss(0, 0.15)))
            status = "unknown" if rng.random() < 0.1 else "scored"
            prongs.append({"prong_name": name, "dimensions": [
                {"name": "d", "value": value, "status": status, "aggregate": True}]})
        aggregate = statistics.mean(
            p["dimensions"][0]["value"] for p in prongs
            if p["dimensions"][0]["status"] == "scored")
        scores[item] = {"prong_results": prongs,
                        "aggregated_scores": {"total_score": aggregate},
                        "coverage": {"prongs_scored": 4}}
    report = analyze(human, scores)
    out = Path("/tmp/prong_ablation_selftest")
    write_report(report, out.with_suffix(".json"), out.with_suffix(".md"))
    print("selftest ok:", out.with_suffix(".json"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations")
    parser.add_argument("--scores")
    parser.add_argument("--out-prefix", default="evaluation_results/prong_ablation")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.annotations or not args.scores:
        raise SystemExit("provide --annotations and --scores (or --selftest)")
    human = load_annotations(args.annotations)
    scores = json.loads(Path(args.scores).read_text())
    report = analyze(human, scores)
    prefix = Path(args.out_prefix)
    write_report(report, prefix.with_suffix(".json"), prefix.with_suffix(".md"))
    print(json.dumps(report, indent=2)[:2000])


if __name__ == "__main__":
    main()
