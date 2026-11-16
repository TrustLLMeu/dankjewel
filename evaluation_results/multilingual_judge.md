# Multilingual judge agreement

Authored fixture: 15 prompts per language, each with one relevant and one irrelevant response (30 judgments per language). Faroese omitted: no aligned small model covers it. Judges were prompted in English with the product's relevance rubric; Qwen3 judges ran with `/no_think`.

| Judge | Language | n | JSON valid | mean relevant | mean irrelevant | rho |
|---|---|---|---|---|---|---|
| Qwen2.5-0.5B (shipped default) | nb | 30 | 1.0 | 1.0 | 0.1 | 0.962 |
| Qwen2.5-0.5B (shipped default) | nn | 30 | 1.0 | 1.0 | 0.1 | 0.923 |
| Qwen2.5-0.5B (shipped default) | da | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen2.5-0.5B (shipped default) | sv | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen2.5-0.5B (shipped default) | de | 30 | 1.0 | 0.933 | 0.0 | 0.935 |
| Qwen2.5-0.5B (shipped default) | nl | 30 | 1.0 | 0.933 | 0.0 | 0.935 |
| Qwen2.5-0.5B (shipped default) | is | 30 | 1.0 | 0.8 | 0.533 | 0.3 |
| Qwen3-1.7B (candidate) | nb | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen3-1.7B (candidate) | nn | 30 | 1.0 | 0.8 | 0.0 | 0.816 |
| Qwen3-1.7B (candidate) | da | 30 | 1.0 | 0.933 | 0.0 | 0.935 |
| Qwen3-1.7B (candidate) | sv | 30 | 1.0 | 0.933 | 0.0 | 0.935 |
| Qwen3-1.7B (candidate) | de | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen3-1.7B (candidate) | nl | 30 | 1.0 | 0.867 | 0.0 | 0.874 |
| Qwen3-1.7B (candidate) | is | 30 | 1.0 | 0.533 | 0.0 | 0.603 |
| Qwen3-8B (reference) | nb | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen3-8B (reference) | nn | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen3-8B (reference) | da | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen3-8B (reference) | sv | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen3-8B (reference) | de | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen3-8B (reference) | nl | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen3-8B (reference) | is | 30 | 1.0 | 0.933 | 0.0 | 0.972 |

Per-judge means:

| Judge | JSON valid | mean rho | separation |
|---|---|---|---|
| Qwen2.5-0.5B (shipped default) | 1.0 | 0.865 | 0.848 |
| Qwen3-1.7B (candidate) | 1.0 | 0.88 | 0.867 |
| Qwen3-8B (reference) | 1.0 | 0.996 | 0.99 |

Pass checks: JSON validity >= 0.95 per language; Spearman rho >= 0.5 per language for the candidate. Language adherence was not automatically assessed (pointwise rubric, no pairwise position-bias test); inspect rationales before any language-quality claim.
