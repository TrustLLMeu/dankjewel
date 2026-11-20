# Wikidata slice for the USA-93 fact-verification set

Built 2026-11-19 for `data/usa_true_false_clean.json` (93 statements: 50 false, 43 true).

## Files

| File | Contents |
|---|---|
| `data/wikidata_usa_93.db` | Seed DB copy plus 63 fetched entities; 1,406 entities, 2,234 claims, 602 aliases (~434 KB) |
| `data/wikidata_usa_93_manifest.json` | Name -> QID map, property list, rank filters, counts |
| `scripts/fetch_usa_93_kb.py` | Reproducible fetch; reuses `scripts/extend_wikidata_db.py` |
| `data/wikidata_cache/` | Raw API responses (Wikipedia/Wikidata), reused on rebuild |

The shipped `data/wikidata_seed.db` is unchanged and remains the default for the pipeline. This slice is used only when a caller passes it explicitly:

```python
from src.resources.wikidata_offline import OfflineWikidata
wd = OfflineWikidata(db_path="data/wikidata_usa_93.db")

from src.prongs.prong3_extraction import Prong3Extraction
prong = Prong3Extraction(wikidata_db_path="data/wikidata_usa_93.db")
```

or set `src.config.WIKIDATA_DB_PATH = "data/wikidata_usa_93.db"` before constructing `EvaluationPipeline`.

## What was fetched

63 curated entities resolved through Wikipedia pageprops (0 unresolved). 48 were new; 15 seed entities were refreshed (the USA, Congress, the Senate, the House, the Constitution, Washington, D.C., ...). 1,446 claims were written.

Properties beyond the FEVER list: `P1082` population, `P1128` employees, `P150` contains administrative territory, `P194` legislative body, `P1342` number of seats, `P463` member of, `P6` head of government, `P35` head of state, `P85` anthem, `P421` time zone, `P625` coordinates, `P163` flag.

## Quality filters

- Deprecated claims are dropped.
- Current-state properties (`P36`, `P30`, `P1082`, `P6`, `P35`, `P31`) keep the preferred Wikidata value only. This removes the historical capitals (New York City, Philadelphia), historical populations (56 census values), and past presidents.
- Current-relation properties (`P36`, `P1376`, `P30`, `P1082`, `P6`, `P35`, `P31`, `P463`) drop claims with a past `P582` end time. This removes New York City's 1785-1790 "capital of the United States" and ended memberships such as the G8.
- Future-dated `P571` values are dropped.
- Seed claims are merged, never deleted, so curated facts Wikidata lacks (for example `Q30 P37 = English`) survive.

Resulting key values: capital `Washington, D.C.` (P36), continent `North America` (P30), population `340,110,988` (P1082), head of government/state `Donald Trump` (P6/P35), type `sovereign state`/`country` (P31), anthem `The Star-Spangled Banner` (P85), 51 current memberships (P463, including the UN and UNSC), Senate seats 100, House seats 435, Congress 535.

## Measured effect (same 93 items)

`evaluation_results/usa_true_false_eval_extended_kb.json`:

| Method | Decided | Accuracy on decided | False detected | True accepted | True denied |
|---|---|---|---|---|---|
| Seed KB, rules | 7/93 | 85.7% | 3/50 | 3/43 | 1/43 |
| USA-93 KB, rules, pre-router | 22/93 | 59.1% | 7/50 | 6/43 | 3/43 |
| USA-93 KB + claim router | 17/93 | 100% | 10/50 | 7/43 | 0/43 |

The router (possessive decomposition, quantity comparison, superlative abstention, location-claim guard, word-boundary value matching) turns the nine pre-router errors into abstentions or corrected verdicts. Coverage settles at 18.3% with no wrong verdicts on this set.

The pre-router false confirmations and false denials traced to:

- **Superlative-blind property matching**: "largest country by land area" confirms via `P2046` area because the object mentions area; "most populous country" and "smallest country" confirm via `P31 = country` because the object mentions country.
- **Substring value matching**: "located in Africa" confirms via `P463 = African Development Bank`.
- **Location fallback misfire**: "Chicago is the USA's capital" confirms via `P17 = United States` (Chicago is in the USA), ignoring the capital relation.
- **Default-property denial**: "The USA has a Department of the Treasury" denies via `P17`, because `have` falls back to a country comparison.
- **Compound subjects**: "The currency of the USA is the US dollar" denies via `P17`; the owner resolves but the head noun (currency) never selects `P38`.
- **Extraction fragment**: "God / save / the King" resolves `God` to the anthem `God Save the King` and confirms via `P17 = United Kingdom`.

## Known data issues

- `Q11698` (US Constitution) currently carries `P571 = 2026-09-17` on Wikidata, two months before this build. The future-date filter keeps it because it is no longer in the future; it should be treated as bad data.
- Some referenced labels are unresolved QIDs (for example `Q816` in the USA's `P150` list).
- The fetch hit HTTP 429 rate limits during label resolution; retries succeeded. Rebuilds use the cache.

## Reproduce

```bash
cd /work/larsbun/git-projects/dankjewel
PYTHONPATH=. .venv/bin/python scripts/fetch_usa_93_kb.py
```

The script copies the seed when the target is absent. Delete `data/wikidata_usa_93.db` first for a clean rebuild.

## Status

The claim-type router is implemented in `src/resources/wikidata_offline.py`:
possessive decomposition (`The USA's currency` / `the currency of the USA`),
population quantity comparison, superlative abstention, a location-claim
guard, normalized word-boundary value matching, and single-token prefix
hardening. Fifteen router tests pin the behavior in `tests/test_five_way.py`.

Remaining gaps on this set:

- Count claims still abstain: "50 states", "100 senators", "435 voting members". They need a count/seat comparator (`P1342` for the chambers; `P150` counts include territories).
- One weak fuzzy confirmation survives: "Baseball is referred to as the national pastime" confirms through Baseball's country relation. It is true but not grounded in a pastime property.
- One malformed extraction ("million / be / The USA's population") denies correctly by accident; the admission gate should reject it.
- `P163` flag and `P2046` area are deliberately excluded from possessive decomposition: their values are an entity and a number, so descriptive claims abstain rather than deny without evidence.

The slice remains experimental; `data/wikidata_seed.db` stays the default until the router is wired into the default path and the count claims are handled.
