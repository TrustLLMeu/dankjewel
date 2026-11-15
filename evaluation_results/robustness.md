# Robustness and throughput

Host: x86_64, 56 CPUs, Python 3.12.3, CPU-only.

## Robustness matrix

| Case | HTTP | Observed | Extra |
|---|---|---|---|
| empty input | 200 | evaluated without crash | scored_dims=10/19, ms=5705.1 |
| very long input (~21k chars) | 200 | evaluated | claims=1, ms=7951.0 |
| non-English input (Dutch) | 200 | evaluated | relevance=0.864, ms=863.1 |
| judge server down | - | judge_status=unknown | baseline_kept=True |
| claims server down | - | claims=1 errors=1 | spacy_track_kept=True |

Not re-run live; covered by the tests:
- verifier model load failure -> VerifierUnavailableError, status error (tests/test_nli_verifier.py)
- malformed model JSON -> ClaimsParseError / judge parse path, status error (tests/test_llm_claim_extractor.py, tests/test_tiny_judge.py)
- per-call timeouts -> unknown/error without blocking (same tests, MockTransport)

## Throughput (sequential, in-process)

| Configuration | n | Mean | p95 | Evals/min |
|---|---|---|---|---|
| default (all optional tracks off) | 10 | 645.4 ms | 659.9 ms | 93.0 |
| all tracks on (judge + claims + verifier) | 5 | 787.4 ms | 1262.5 ms | 76.2 |

Sequential measurements: the API runs one evaluation at a time per process. Concurrent throughput would need multiple workers and is not measured here.
