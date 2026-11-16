# LLM-AggreFact verifier benchmark (dev)

Dataset: `lytang/LLM-AggreFact` (dev); model: `lytang/MiniCheck-Flan-T5-Large` via `src/resources/nli_verifier.py`. This validates the verifier component, not the seed-KB path.

| Dataset | n | Accuracy @0.5 | AUC | Mean latency | p95 latency |
|---|---|---|---|---|---|
| AggreFact-CNN | 150 | 0.9333 | 0.7473 | 795.3 ms | 1264.0 ms |
| AggreFact-XSum | 150 | 0.6333 | 0.7607 | 583.6 ms | 761.9 ms |
| ClaimVerify | 150 | 0.4867 | 0.5658 | 1332.0 ms | 1628.1 ms |
| ExpertQA | 150 | 0.5 | 0.6353 | 452.8 ms | 1402.1 ms |
| FactCheck-GPT | 150 | 0.8333 | 0.8821 | 313.7 ms | 381.1 ms |
| Lfqa | 150 | 0.8267 | 0.8833 | 500.7 ms | 626.2 ms |
| RAGTruth | 150 | 0.5267 | 0.667 | 949.1 ms | 1537.8 ms |
| Reveal | 150 | 0.8933 | 0.9426 | 294.9 ms | 398.9 ms |
| TofuEval-MediaS | 150 | 0.5067 | 0.4148 | 1544.3 ms | 1634.9 ms |
| TofuEval-MeetB | 150 | 0.6067 | 0.7103 | 1194.9 ms | 1558.6 ms |
| Wice | 150 | 0.6667 | 0.657 | 1316.7 ms | 1582.0 ms |
| **pooled** | 1650 | 0.6739 | 0.7685 | 843.5 ms | 1589.9 ms |
