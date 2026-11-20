"""Attribution helpers for C0a (harness-level, no pipeline change).

Determines decision_layer per claim/item and by_layer aggregates with
false_confirms. C0a emits only kb_exact + abstain (web/verifier are stubs
for forward compatibility — see docs/scouting/2026-11-20-live-factcheck.md §7.6).
"""

from collections import Counter, defaultdict

DECISION_LAYERS = ("kb_exact", "web", "verifier", "abstain")


def attribution_for_claim(claim_detail: dict) -> tuple[str, str | None]:
    """Map a claim_details[i] to (decision_layer, abstain_reason).

    C0a rule: effective_result != UNKNOWN -> kb_exact, else abstain + reason passthrough.
    Future C1/B1 will branch on decision_layer tags (web/verifier) before this fallback.
    """
    if claim_detail.get("effective_result") != "unknown":
        return "kb_exact", None
    return "abstain", claim_detail.get("reason")


def attribution_for_item(claims: list[dict]) -> tuple[str, dict, bool]:
    """Roll up claims to item-level (decision_layer, layer_counts, false_confirm).

    layer_counts always carries all four layers (explicit 0, never KeyError).
    false_confirm is item-level harm signal; set true iff the item's prediction
    made a false→true error (caller must pass ground_truth/prediction).
    """
    if not claims:
        return "abstain", {k: 0 for k in DECISION_LAYERS}, False
    counts = Counter(attribution_for_claim(cd)[0] for cd in claims)
    layer_counts = {k: int(counts.get(k, 0)) for k in DECISION_LAYERS}
    non_zero = [k for k, v in layer_counts.items() if v > 0]
    decision_layer = non_zero[0] if len(non_zero) == 1 else "mixed"
    return decision_layer, layer_counts, False


def attribution_metrics(items: list[dict], condition: str = "off") -> dict:
    """Compute by_layer aggregates and false_confirms for one condition.

    items: eval JSON items[i] already carrying decision_layer/layer_counts/false_confirm per condition block.
    Returns dict with per-layer decided/accuracy/false_confirms/false_confirm_rate/coverage_added
    plus top-level false_confirms / false_confirm_rate.
    """
    by_layer = {}
    total = len(items)
    n_false = sum(1 for it in items if it["ground_truth"] == "false")
    for layer in DECISION_LAYERS:
        decided_items = [it for it in items if it[condition].get("decision_layer") == layer and it[condition].get("prediction") in ("true", "false")]
        decided = len(decided_items)
        correct = sum(1 for it in decided_items if it[condition]["prediction"] == it["ground_truth"])
        false_confirms = sum(1 for it in decided_items if it["ground_truth"] == "false" and it[condition]["prediction"] == "true")
        by_layer[layer] = {
            "decided": decided,
            "accuracy": round(correct / decided, 4) if decided else None,
            "false_confirms": false_confirms,
            "false_confirm_rate": round(false_confirms / n_false, 4) if false_confirms and n_false else (0.0 if false_confirms == 0 and decided == 0 else round(false_confirms / n_false, 4)) if n_false else None,
            "coverage_added": round(decided / total, 4) if total else 0.0,
        }
        if false_confirms == 0 and n_false:
            by_layer[layer]["false_confirm_rate"] = 0.0
        if decided == 0:
            by_layer[layer]["false_confirm_rate"] = None if by_layer[layer]["false_confirms"] == 0 and n_false else 0.0
            # Keep 0.0 for readable empty-layer, None only if truly no false slice
            if by_layer[layer]["false_confirms"] == 0:
                by_layer[layer]["false_confirm_rate"] = 0.0 if layer not in ("web", "verifier") else None
                if layer in ("web", "verifier"):
                    by_layer[layer]["accuracy"] = None
            by_layer[layer]["coverage_added"] = 0.0
        # Ensure accuracy is None for empty layers with no web/verifier nuance
        if decided == 0:
            by_layer[layer]["accuracy"] = None

    # Mixed pseudo-layer (C0a won't produce mixed since claims already gate, but keep for completeness)
    mixed_items = [it for it in items if it[condition].get("decision_layer") == "mixed" and it[condition].get("prediction") in ("true", "false")]
    if mixed_items:
        by_layer["mixed"] = {
            "decided": len(mixed_items),
            "accuracy": round(sum(1 for it in mixed_items if it[condition]["prediction"] == it["ground_truth"]) / len(mixed_items), 4),
            "false_confirms": sum(1 for it in mixed_items if it["ground_truth"] == "false" and it[condition]["prediction"] == "true"),
            "false_confirm_rate": round(sum(1 for it in mixed_items if it["ground_truth"] == "false" and it[condition]["prediction"] == "true") / n_false, 4) if n_false else None,
            "coverage_added": round(len(mixed_items) / total, 4),
        }

    # Top-level rollup
    false_confirms = sum(1 for it in items if it["ground_truth"] == "false" and it[condition].get("prediction") == "true")
    return {
        "by_layer": by_layer,
        "false_confirms": false_confirms,
        "false_confirm_rate": round(false_confirms / n_false, 4) if n_false else None,
    }
