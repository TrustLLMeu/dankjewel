"""Multilingual judge-agreement test.

Scores 210 authored items (7 languages x 30; 15 relevant + 15 irrelevant
responses per language) with three judges and reports the pass checks from the
test plan: JSON validity, score separation, and Spearman correlation with the
expected relevance label. Faroese is omitted because no aligned small model
covers it; that omission is reported, not hidden.

Judges:
  incumbent  Qwen2.5-1.5B-Instruct  http://127.0.0.1:18093/v1
  candidate  Qwen3-1.7B             http://127.0.0.1:18096/v1   (/no_think)
  reference  Qwen3-8B               http://127.0.0.1:18095/v1   (/no_think)

Requires DANKJEWEL_JUDGE_API_KEY in the environment (same local key as the
product judges). Writes evaluation_results/multilingual_judge.{json,md}.

Run from the repo root:
    .venv/bin/python scripts/eval_multilingual_judge.py
"""

import json
import os
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURE = Path("data/multilingual_judge_items.json")
OUT_JSON = Path("evaluation_results/multilingual_judge.json")
OUT_MD = Path("evaluation_results/multilingual_judge.md")
KEY = os.environ.get("DANKJEWEL_JUDGE_API_KEY", "")

SYSTEM = (
    "[JUDGE] Rate how relevant the Answer is to the Prompt. 0 = irrelevant, "
    "0.5 = partially relevant, 1 = directly answers. Reply with ONLY JSON: "
    '{"score": 0 to 1, "rationale": at most 40 words}.\n'
    "Examples:\n"
    "Prompt: What is 2+2? Answer: The sum is 4. -> "
    '{"score": 1, "rationale": "Directly answers the arithmetic question."}\n'
    "Prompt: What is 2+2? Answer: Apples grow on trees. -> "
    '{"score": 0, "rationale": "No connection to the arithmetic question."}'
)

JUDGES = [
    {"name": "Qwen2.5-1.5B (incumbent)", "base": "http://127.0.0.1:18093/v1",
     "model": "Qwen/Qwen2.5-1.5B-Instruct", "no_think": False},
    {"name": "Qwen3-1.7B (candidate)", "base": "http://127.0.0.1:18096/v1",
     "model": "Qwen/Qwen3-1.7B", "no_think": True},
    {"name": "Qwen3-8B (reference)", "base": "http://127.0.0.1:18095/v1",
     "model": "Qwen/Qwen3-8B", "no_think": True},
]


def parse_score(content: str):
    """Extract a 0..1 score from the judge's reply; None when unusable."""
    text = (content or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start:end + 1])
        score = float(payload.get("score"))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if score < 0 or score > 1:
        return None
    return score


def judge_call(client, judge, prompt, response):
    system = SYSTEM + ("\n/no_think" if judge["no_think"] else "")
    payload = {
        "model": judge["model"],
        "temperature": 0.0,
        "max_tokens": 160,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Prompt: {prompt}\nAnswer: {response}"},
        ],
    }
    headers = {"Content-Type": "application/json"}
    if KEY:
        headers["Authorization"] = f"Bearer {KEY}"
    t0 = time.perf_counter()
    try:
        resp = client.post(f"{judge['base']}/chat/completions", json=payload,
                           headers=headers, timeout=120)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError,
            json.JSONDecodeError):
        return None, (time.perf_counter() - t0) * 1000
    return parse_score(content), (time.perf_counter() - t0) * 1000


def spearman(xs, ys):
    """Spearman rho with average ranks; None when one side is constant."""
    def ranks(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        out = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = rank
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) ** 0.5
           * sum((b - my) ** 2 for b in ry) ** 0.5)
    return None if den == 0 else num / den


def main():
    data = json.loads(FIXTURE.read_text())
    report = {"fixture": str(FIXTURE), "judges": {}}
    md = ["# Multilingual judge agreement", "",
          "Authored fixture: 15 prompts per language, each with one relevant and "
          "one irrelevant response (30 judgments per language). Faroese omitted: "
          "no aligned small model covers it. Judges were prompted in English with "
          "the product's relevance rubric; Qwen3 judges ran with `/no_think`.", ""]
    header = ("| Judge | Language | n | JSON valid | mean relevant | mean "
              "irrelevant | rho |")
    md += [header, "|---|---|---|---|---|---|---|"]
    with httpx.Client() as client:
        for judge in JUDGES:
            per_lang = {}
            for lang, items in data["languages"].items():
                scores, expected, lat = [], [], []
                for item in items:
                    score, ms = judge_call(client, judge, item["prompt"],
                                           item["response"])
                    scores.append(score)
                    expected.append(item["expected"])
                    lat.append(ms)
                valid = [s for s in scores if s is not None]
                rel = [s for s, e in zip(scores, expected) if e == 1 and s is not None]
                irr = [s for s, e in zip(scores, expected) if e == 0 and s is not None]
                rho = None
                if len(valid) >= 2 and len(set(scores)) > 1:
                    filled = [s if s is not None else 0.0 for s in scores]
                    rho = spearman(filled, expected)
                per_lang[lang] = {
                    "n": len(items),
                    "json_valid": round(len(valid) / len(items), 3),
                    "mean_relevant": round(statistics.mean(rel), 3) if rel else None,
                    "mean_irrelevant": round(statistics.mean(irr), 3) if irr else None,
                    "rho": round(rho, 3) if rho is not None else None,
                    "mean_latency_ms": round(statistics.mean(lat), 1),
                }
                row = per_lang[lang]
                md.append(f"| {judge['name']} | {lang} | {row['n']} | "
                          f"{row['json_valid']} | {row['mean_relevant']} | "
                          f"{row['mean_irrelevant']} | {row['rho']} |")
            langs = list(per_lang.values())
            report["judges"][judge["name"]] = {
                "per_language": per_lang,
                "json_valid_mean": round(statistics.mean(
                    x["json_valid"] for x in langs), 3),
                "rho_mean": round(statistics.mean(
                    x["rho"] for x in langs if x["rho"] is not None), 3),
                "separation_mean": round(statistics.mean(
                    (x["mean_relevant"] or 0) - (x["mean_irrelevant"] or 0)
                    for x in langs), 3),
            }
    md += ["", "Pass checks from the test plan: JSON validity >= 0.95 per "
           "language; Spearman rho >= 0.5 per language for the candidate. "
           "Language adherence was not automatically assessed (the rubric is "
           "pointwise, so there is no pairwise position-bias test); inspect a "
           "sample of rationales before making a language-quality claim."]
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "per_language"}
                      for k, v in report["judges"].items()}, indent=2))


if __name__ == "__main__":
    main()
