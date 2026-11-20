"""C0a evaluation: router fixes on 93-set vs wikidata_usa_93.db + seed-144 regression.

Offline-only, zero network egress, CPU-only.
Attribution (decision_layer/layer_counts/false_confirms/by_layer) harness-level — no pipeline change.
Gates: accuracy_on_decided >=75%, false->true <=2 (KB layer), total /evaluate p50 <1.0s.

Outputs:
  evaluation_results/usa_true_false_router_fix.json  (93-set vs usa_93.db, attributed)
  evaluation_results/usa_true_false_router_fix_seed.json  (seed-144 regression)
"""
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import json, hashlib, time, collections
import scripts.attribution as attribution
import src.config as _cfg

# ── evaluate one DB path ────────────────────────────────────────────────
def evaluate_db(db_path, label, out_path):
    import importlib
    _cfg.WIKIDATA_DB_PATH = db_path
    # Reimport pipeline so it picks up the new WIKIDATA_DB_PATH
    import src.resources.wikidata_offline as wod
    from src.pipeline import EvaluationPipeline
    DS = "data/usa_true_false_clean.json"
    d = json.load(open(DS))
    items = d["items"]

    def fa_of(res):
        p = next(p for p in res["prong_results"] if "Prong 3" in p["prong_name"])
        return next(x for x in p["dimensions"] if x["name"] == "Factual Accuracy")

    def predict(relations, conflated_is_false=True):
        if not relations:
            return "abstain"
        rels = set(relations)
        if rels <= {"confirmed"}:
            return "true"
        false_set = {"denied", "conflated"} if conflated_is_false else {"denied"}
        if rels <= false_set:
            return "false"
        return "abstain"

    pipe = EvaluationPipeline(enable_prongs=[3])
    rows = []
    timings = []
    t0 = time.perf_counter()
    for n, item in enumerate(items, 1):
        row = {"id": item["id"], "statement": item["statement"], "ground_truth": item["ground_truth"],
               "section_index": item["section_index"]}
        for tag, flag in (("off", False), ("on", True)):
            start = time.perf_counter()
            res = pipe.evaluate(item["statement"], lang="en", llm_verify=flag)
            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)
            fa = fa_of(res)
            md = fa["metadata"]
            details = md.get("claim_details", [])
            rels = [cd.get("relation") for cd in details]
            # Attribution per claim
            for cd in details:
                layer, abstain_reason = attribution.attribution_for_claim(cd)
                cd["decision_layer"] = layer
                cd["abstain_reason"] = abstain_reason
            # Attribution per item
            decision_layer, layer_counts, _ = attribution.attribution_for_item(details)
            pred = predict(rels)
            pred_strict = predict(rels, conflated_is_false=False)
            false_confirm = (item["ground_truth"] == "false" and pred == "true")
            row[tag] = {
                "prediction": pred,
                "prediction_strict": pred_strict,
                "fa_value": fa["value"], "fa_status": fa["status"],
                "relations": rels,
                "decision_layer": decision_layer,
                "layer_counts": layer_counts,
                "false_confirm": false_confirm,
                "verifiable": md.get("verifiable"),
                "claims": [
                    {"subject": cd["claim"]["subject"], "predicate": cd["claim"]["predicate"],
                     "object": cd["claim"]["object"], "relation": cd.get("relation"),
                     "decision_layer": cd.get("decision_layer"), "abstain_reason": cd.get("abstain_reason"),
                     "reason": cd.get("reason"), "verifier_score": cd.get("verifier_score"),
                     "source": cd["claim"].get("source")}
                    for cd in details
                ],
                "admission": md.get("claim_admission"),
            }
        rows.append(row)
        if n % 20 == 0:
            print(f"  {n}/{len(items)} items ...", flush=True)

    elapsed_s = round(time.perf_counter() - t0, 1)

    def metrics(rows, key, field="prediction"):
        out = {"by_truth": {}, "confusion": collections.Counter(), "coverage": {}, "accuracy": {}}
        for truth in ("true", "false"):
            sel = [r for r in rows if r["ground_truth"] == truth]
            c = collections.Counter(r[key][field] for r in sel)
            out["by_truth"][truth] = {"n": len(sel), **{k: c.get(k, 0) for k in ("true", "false", "abstain")}}
            for pred, k in c.items():
                out["confusion"][f"truth={truth}|pred={pred}"] += k
        total = len(rows)
        decided = sum(1 for r in rows if r[key][field] in ("true", "false"))
        correct = sum(1 for r in rows if r[key][field] == r["ground_truth"])
        out["coverage"] = {"decided": decided, "total": total, "rate": round(decided / total, 4)}
        out["accuracy"] = {
            "on_decided": round(correct / decided, 4) if decided else None,
            "overall_abstain_wrong": round(correct / total, 4),
        }
        return out

    methods = {}
    for key, label_n in (("off", "KB exact + conflation (llm_verify off)"),
                         ("on", "KB exact + conflation + gated MiniCheck (llm_verify on)")):
        methods[key] = {"label": label_n,
                        "main": metrics(rows, key),
                        "strict_conflated_abstains": metrics(rows, key, "prediction_strict")}

    # Attribution rollup + false_confirms per condition
    attrib = {}
    for key in ("off", "on"):
        attrib[key] = attribution.attribution_metrics(rows, condition=key)

    # Latency percentiles
    timings_sorted = sorted(timings)
    p50 = timings_sorted[len(timings_sorted)//2] if timings_sorted else 0
    p90 = timings_sorted[int(len(timings_sorted)*0.9)] if timings_sorted else 0
    p99 = timings_sorted[int(len(timings_sorted)*0.99)] if timings_sorted else 0

    artifact = {
        "meta": {
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dataset_file": "data/usa_true_false_clean.json",
            "dataset_sha256": hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest(),
            "dataset_counts": d["meta"]["counts"],
            "pipeline": "EvaluationPipeline(enable_prongs=[3]), language='en'",
            "db_path": db_path,
            "db_label": label,
            "decision_rule": "Per item: all claims confirmed -> true; all denied/conflated -> false; mixed or any partial/unknown -> abstain. 'strict' treats conflated as abstain.",
            "minicheck_thresholds": {"support": 0.8, "deny": 0.2},
            "attribution": "harness-level decision_layer per claim/item + by_layer + false_confirms (see docs/scouting/2026-11-20-live-factcheck.md §7.6)",
            "elapsed_s": elapsed_s,
            "timings": {"n": len(timings), "p50_ms": round(p50, 1), "p90_ms": round(p90, 1), "p99_ms": round(p99, 1), "mean_ms": round(sum(timings)/len(timings), 1) if timings else 0},
        },
        "metrics": methods,
        "by_layer": {k: attrib[k]["by_layer"] for k in attrib},
        "false_confirms": {k: attrib[k]["false_confirms"] for k in attrib},
        "false_confirm_rate": {k: attrib[k]["false_confirm_rate"] for k in attrib},
        "items": rows,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\n=== SUMMARY ({label}, {db_path}) ===")
    for key in ("off", "on"):
        m = methods[key]["main"]
        print(f"\n{methods[key]['label']}")
        print("  coverage:", m["coverage"], "accuracy(decided):", m["accuracy"]["on_decided"])
        print("  false_confirms:", attrib[key]["false_confirms"], "false_confirm_rate:", attrib[key]["false_confirm_rate"])
        print("  by_layer.kb_exact:", attrib[key]["by_layer"]["kb_exact"])
        for truth in ("false", "true"):
            print(f"  {truth:5s}: {m['by_truth'][truth]}")
        # Gate check
        acc = m["accuracy"]["on_decided"]
        fc = attrib[key]["false_confirms"]
        acc_pass = acc is None or acc >= 0.75
        fc_pass = fc <= 2
        print(f"  [gate] accuracy {acc} >=0.75 {'PASS' if acc_pass else 'FAIL'} | false_confirms {fc} <=2 {'PASS' if fc_pass else 'FAIL'}")
    print(f"  p50 {p50:.1f}ms p99 {p99:.1f}ms p99<1000 {'PASS' if p99 < 1000 else 'FAIL'}")
    print(f"\nwrote {out_path}")
    return artifact

if __name__ == "__main__":
    # Primary: C0a — usa_93 DB (offline router fixes)
    evaluate_db("data/wikidata_usa_93.db", "wikidata_usa_93.db (C0a router fixes)", "evaluation_results/usa_true_false_router_fix.json")
    # Regression: seed-144 baseline (same router fixes, smaller DB)
    evaluate_db("data/wikidata_seed.db", "wikidata_seed.db (regression)", "evaluation_results/usa_true_false_seed_regression.json")
