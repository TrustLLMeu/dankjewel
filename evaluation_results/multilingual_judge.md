# Multilingual judge agreement

Authored fixture: 15 prompts per language, each with one relevant and one irrelevant response (30 judgments per language). Faroese omitted: no aligned small model covers it. Judges were prompted in English with the product's relevance rubric; Qwen3 judges ran with `/no_think`.

| Judge | Language | n | JSON valid | mean relevant | mean irrelevant | rho |
|---|---|---|---|---|---|---|
| Qwen2.5-1.5B (incumbent) | nb | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen2.5-1.5B (incumbent) | nn | 30 | 1.0 | 0.933 | 0.0 | 0.935 |
| Qwen2.5-1.5B (incumbent) | da | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen2.5-1.5B (incumbent) | sv | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen2.5-1.5B (incumbent) | de | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen2.5-1.5B (incumbent) | nl | 30 | 1.0 | 1.0 | 0.0 | 1.0 |
| Qwen2.5-1.5B (incumbent) | is | 30 | 1.0 | 0.867 | 0.0 | 0.874 |
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

Pass checks from the test plan: JSON validity >= 0.95 per language; Spearman rho >= 0.5 per language for the candidate. Language adherence was not automatically assessed (the rubric is pointwise, so there is no pairwise position-bias test); inspect a sample of rationales before making a language-quality claim.
