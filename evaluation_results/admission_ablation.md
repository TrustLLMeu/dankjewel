# Admission ablation (teacher-prose fixture)

Each row adds one layer to the pipeline above it. `expected_of_5` counts the five intended false-claim examples that survive; `known_nonclaims` counts the hand-labelled junk (markdown/pronoun fragments, the smoking fragment, the advice sentence).

| Stage | Claims | Expected of 5 | Known non-claims |
|---|---|---|---|
| A raw | 76 | 5 | 46 |
| B +markdown | 28 | 5 | 15 |
| C +sentence | 17 | 5 | 8 |
| D +triple | 8 | 5 | 2 |
| E +dedupe | 8 | 5 | 2 |
| F +use-mention | 9 | 5 | 2 |
