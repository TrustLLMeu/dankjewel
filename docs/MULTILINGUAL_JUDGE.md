# Multilingual Judge Agreement

The runtime LLM judge must work in all nine of the product's UI languages
(`frontend/locales/`: en, nb, nn, da, sv, is, fo, de, nl). This test measures
judge agreement — how well each candidate separates relevant from irrelevant
responses, and how its scores correlate with the authored labels — on an
authored fixture.

## Fixture

`data/multilingual_judge_items.json` — 210 authored items: 7 UI languages
(nb, nn, da, sv, de, nl, is) × 30 judgments (15 prompts, each with one
relevant and one irrelevant response). Faroese is omitted because no aligned
small model covers it; the omission is reported, not hidden.

## Judges and setup

| Role | Model | Endpoint | Notes |
|---|---|---|---|
| shipped default | `Qwen/Qwen2.5-0.5B-Instruct` | `http://127.0.0.1:18092/v1` | the judge the product uses today |
| claims-size comparator | `Qwen/Qwen2.5-1.5B-Instruct` | `http://127.0.0.1:18093/v1` | the claims server's model, run as a judge |
| candidate | `Qwen/Qwen3-1.7B` | `http://127.0.0.1:18096/v1` | `/no_think` |
| reference | `Qwen/Qwen3-8B` | `http://127.0.0.1:18095/v1` | `/no_think`, calibration only |

All three are local llama.cpp servers on Malvik. Every judgment is pointwise
under the product's relevance rubric (English system prompt: 0 = irrelevant,
0.5 = partially relevant, 1 = directly answers; JSON-only reply with a
rationale of at most 40 words), `temperature` 0, `max_tokens` 160.

## Results

Artifacts: `evaluation_results/multilingual_judge.json` and `.md`.
Per-judge means over the seven languages:

| Judge | JSON valid | mean Spearman rho | separation |
|---|---|---|---|
| Qwen2.5-0.5B (shipped default) | 1.000 | 0.865 | 0.848 |
| Qwen2.5-1.5B (claims-size comparator) | 1.000 | 0.973 | 0.971 |
| Qwen3-1.7B (candidate) | 1.000 | 0.880 | 0.867 |
| Qwen3-8B (reference) | 1.000 | 0.996 | 0.990 |

Separation is mean relevant minus mean irrelevant per language. All
mean-irrelevant values are 0.000 for every judge.

Lowest per-language cells (mean relevant / rho, same column order):

| Language | 0.5B shipped | 1.5B comparator | 1.7B candidate | 8B reference |
|---|---|---|---|---|
| Icelandic (is) | 0.800 / **0.300** | 0.867 / 0.874 | 0.533 / 0.603 | 0.933 / 0.972 |
| Nynorsk (nn) | 1.000 / 0.923 | 0.933 / 0.935 | 0.800 / 0.816 | 1.000 / 1.000 |
| Dutch (nl) | 0.933 / 0.935 | 1.000 / 1.000 | 0.867 / 0.874 | 1.000 / 1.000 |

Pass checks from the test plan: JSON validity ≥ 0.95 per language holds for
every judge (all cells 1.000). The rho ≥ 0.5 per language check **fails for the
shipped 0.5B judge on Icelandic (0.300)** and passes for the 1.5B (lowest 0.874),
the 1.7B candidate (lowest 0.603) and the 8B reference (lowest 0.972).

Per-call latency (mean ms, lowest to highest language): incumbent
620.7–843.2 ms (~0.62–0.84 s, de … is), candidate 931.9–1096.1 ms
(~0.93–1.10 s, da … is), reference 2611.2–3150.7 ms (~2.6–3.2 s, nl … is).

## Decision

The shipped 0.5B judge is adequate for English but **fails the multilingual
pass check on Icelandic (rho 0.300)**. The smallest model that passes all seven
languages is `Qwen/Qwen2.5-1.5B-Instruct` (mean rho 0.973, lowest 0.874),
already running locally as the claims server; it is the recommended judge
configuration for non-English use (point the judge env at `:18093` with
`Qwen/Qwen2.5-1.5B-Instruct`). `Qwen/Qwen3-1.7B` is not adopted: it passes the
checks but is worse than the 1.5B (mean rho 0.880 vs 0.973, separation 0.867 vs
0.971) and ~1.4x slower (mean 997 ms vs 701 ms). The cap increase to <= 1.7B
stands for future candidates; `Qwen/Qwen3-8B` remains calibration/reference only
and is never a product judge.

Caveats: the items are easy, authored pointwise pairs, so a real deployment
with graded, in-between relevance will be harder; language adherence was not
automatically assessed (inspect a sample of rationales before any
language-quality claim); the rubric is pointwise, so there is no pairwise
position-bias test; and the Icelandic weakness is not specific to the
candidate — it affects every small model, including the 8B reference.

## How to rerun

From the repo root, with `DANKJEWEL_JUDGE_API_KEY` set (the same local key
the product judges use) and the three local servers up on :18093, :18096,
:18095:

```
.venv/bin/python scripts/eval_multilingual_judge.py
```

Expected runtime ~16 minutes: 630 sequential calls (210 per judge), derived
from the artifact per-call means, 210 × ~0.70 s + 210 × ~1.00 s +
210 × ~2.85 s ≈ 955 s. The script rewrites
`evaluation_results/multilingual_judge.json` and
`evaluation_results/multilingual_judge.md` and prints the table.
