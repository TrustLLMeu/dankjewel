# SciFact verifier benchmark

Source: `https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz` (downloaded 2026-11-14); model: `lytang/MiniCheck-Flan-T5-Large` via `src/resources/nli_verifier.py`.

Pairs: evidence-annotated (SUPPORT/CONTRADICT; REFUTE in older releases) claim–sentence pairs; NOT_ENOUGH_INFO claims excluded. This validates the verifier component, not the seed-KB path.

| Split | n | Accuracy @0.5 | AUC | Mean latency | p95 latency |
|---|---|---|---|---|---|
| dev | 338 | 0.6006 | 0.835 | 257.5 ms | 367.3 ms |
| train | 957 | 0.5549 | 0.7897 | 231.7 ms | 339.5 ms |

Both splits use the same thresholds as the product (p >= 0.5 counts as supported).
