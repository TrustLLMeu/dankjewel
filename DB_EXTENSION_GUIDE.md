# DB Extension Guide — Increasing Wikidata Coverage

## Failure-mode diagnosis (oracle DB, 300 claims, pre-extension)

| Mode | Count | Share |
|------|-------|-------|
| Subject entity not in DB | 155 | 56% |
| No triples extracted (complex syntax) | 37 | 13% |
| Predicate not mapped to Wikidata property | 38 | 14% |
| Property mapped but empty in DB | 4 | 1% |
| Other (value mismatch / copula) | 42 | 15% |

Coverage before: **24/300 (8.0%)**

---

## What was implemented (offline, zero network calls)

### 1. Compound-NP entity lookup (`src/resources/wikidata_offline.py`)

`lookup_entity()` now decomposes complex extracted NPs before giving up:

- **Possessives** — `"Sensitive Skin's first series"` → tries `"Sensitive Skin"`
- **"X of Y" patterns** — `"The area of Muş Province"` → tries `"Muş Province"`
- **"a [type] called [Name]"** — `"a movie called Jackie"` → tries `"Jackie"`
- **Trailing-word fallback** — progressively drops leading words

This converted ~60 of the 155 "subject not found" failures into resolvable lookups.

### 2. New predicate mappings (`src/resources/wikidata_offline.py`)

Added 30+ new entries to `PREDICATE_TO_PROPERTY`:

| Predicate (spaCy lemma form) | Property | Notes |
|------------------------------|----------|-------|
| `host`, `hosted` | P276 | location |
| `win`, `won` | P166 | award received |
| `debut`, `debuted`, `premier`, `premiered` | P577 | publication date |
| `publish`, `published`, `release`, `released` | P577 | publication date |
| `compete in`, `competed in` | P1344 | participant in |
| `headquartered`, `is headquarter` | P159 | seat of government |
| `establish`, `established` | P571 | inception |
| `was broadcast` | P449 | original broadcaster |
| `was include`, `include in` | P361 | part of |
| `known as`, `know as`, `go by` | P1449 | nickname |
| `is call` | P1476 | title |

### 3. Additional properties in build script (`scripts/build_fever_wikidata.py`)

Added to the PROPERTIES fetch list:
- `P577` — publication date (covers debut/release claims)
- `P155`, `P156` — follows / followed by (succession claims)
- `P1449` — nickname
- `P1476` — title

**Coverage after offline changes: 32/300 (10.7%)** — a 33% relative improvement with no network calls.

---

## To increase coverage further (requires internet access)

### Option A — Extend the existing oracle DB with claim-text entities

This is the highest-impact next step. The new `extend_wikidata_db.py` script
extracts named entities from claim text (via spaCy NER + ClaimExtractor) and
fetches them from Wikidata, adding them to the existing DB.

```bash
# Dry-run first to see what would be fetched
python scripts/extend_wikidata_db.py \
    --claims  data/fever2_oracle_sample.jsonl \
    --db-path data/wikidata_fever.db \
    --dry-run

# Actually extend (will take several minutes due to API rate limiting)
python scripts/extend_wikidata_db.py \
    --claims  data/fever2_oracle_sample.jsonl \
    --db-path data/wikidata_fever.db

# Then re-run the eval
python scripts/eval_fever2.py \
    --db-path data/wikidata_fever.db \
    --sample-path data/fever2_oracle_sample.jsonl \
    --output-suffix oracle
```

**Expected impact:** ~871 additional entity names to resolve. Even if 20–30%
resolve successfully, that could push coverage from 10.7% to 20–30%.

### Option B — Rebuild with `--extend-from-claims` flag (combined pipeline)

```bash
python scripts/build_fever_wikidata.py \
    --n-per-class 100 \
    --extend-from-claims data/fever2_oracle_sample.jsonl
```

This rebuilds the oracle DB from evidence pages AND immediately runs the
claim-text extension pass in one command.

### Option C — Use the full FEVER2 dataset (more evidence entities)

```bash
python scripts/build_fever_wikidata.py --n-per-class 0   # all 1174 claims
```

### Option D — SPARQL bulk download

`scripts/build_wikidata_db.py` has a Phase 2 placeholder for bulk SPARQL
queries that would yield ~200k entities. This would require implementing the
SPARQL endpoint queries (see the TODO comment in that file).

---

## Remaining bottlenecks after the online extension

Even with entity coverage improved, several structural gaps remain:

1. **Complex sentence structures** (37 claims with 0 triples) — require
   improved ClaimExtractor: better handling of negation (`There is no X`),
   coordination (`Neither X nor Y`), and comparative claims.

2. **Multi-hop claims** — `"Henry III was succeeded by the first French
   emperor of the House of Bourbon"` requires two lookup steps; the current
   single-triple verifier cannot handle these.

3. **Comparative/superlative claims** — `"area of X is larger than area of Y"`
   requires numerical comparison, not string matching.

4. **Temporal manipulation** — FEVER fixers introduce deliberate date offsets
   (e.g., `"4 years before 1987"`) which require arithmetic reasoning.

These are extractor/verifier improvements, not DB improvements.

---

## Verifier precision fix (2026-07-09) — AUC was worse than chance

After extending the DB, coverage rose (24→38/300) but **Binary AUC dropped
to 0.486 and Conditional AUC to 0.476** — worse than chance. Root cause:
weak/generic verification paths were confidently CONFIRMING REFUTES claims
whose only falsified detail was a small qualifier embedded in an otherwise-
true sentence — exactly what FEVER 2.0's REFUTES mutations look like:

- `"A View to a Kill is the **third** James Bond film directed by John
  Glen"` — real ordinal is *second*; the verifier matched the generic
  "instance of: film" (P31) and never looked at "third".
- `"There exists **no** Spanish city called Melilla"` — spaCy attaches
  `no` as a noun determiner, not a verb `neg`, so `_detect_negation()`
  silently dropped the negation and the (true) fact "Melilla is a Spanish
  city" was confirmed without inversion.
- `"Uganda ... was not a protectorate"` — object `"a protectorate"`
  resolved to a generic Wikidata concept entity (Q164142) with no location
  data, but the old check treated *any* resolvable object as "looks like a
  place" and issued a false denial.

### Fixes applied

1. **`src/extraction/claim_extractor.py`** — existential negation now also
   checks for a `no` determiner inside the subject NP (`det` dependency),
   not just a `neg` child of the root verb.
2. **`src/resources/wikidata_offline.py`** — new `_apply_qualifier_gate()`
   guards every *weak* verification path (copula-inferred property match,
   `_try_fuzzy_property_match`, superlative auto-confirm, location
   containment):
   - Explicit role clauses (`directed by X`, `written by X`, `composed by
     X`, `produced by X`, `created by X`, `performed by X`) are checked
     against the real Wikidata property; a genuine mismatch → **DENIED**;
     no data to check → **abstain (UNKNOWN)**.
   - Ordinal + series-type-noun combinations (`"the third ... film"`,
     `"first ... single"`) can't be verified against our flat claims
     schema (no per-entity series-ordinal data) → **abstain**.
   - Relative/ranged temporal qualifiers (`"before 1990"`, `"between X and
     Y"`) require arithmetic date reasoning we don't have → **abstain**.
   - `_try_location_verification`'s "looks like a place" check was
     tightened: the object must resolve to an entity that itself carries a
     geographic property (P17/P131/P30/P36) or an instance-of a
     place-type — not just any resolvable QID.

### Result (300-claim oracle eval)

| Metric | Before fix | After fix |
|---|---|---|
| Coverage | 38/300 (12.7%) | 26/300 (8.7%) |
| Binary AUC | 0.486 | **0.538** |
| Conditional AUC (covered only) | 0.476 | **0.682** |
| REFUTES precision (covered) | 7/19 (37%) | 8/11 (73%) |

Coverage dropped because several previously-wrong CONFIRMED verdicts now
correctly abstain (UNKNOWN) rather than guess — a deliberate precision-over-
recall tradeoff. Both AUC metrics are now clearly better than chance.

Remaining false positives are genuine structural gaps (documented above):
multi-hop geography ("PacSun ... in a city in Orange County" requires
knowing Anaheim ⊂ Orange County), embedded negated relative clauses that
the single-triple extractor drops entirely (`"a movie ... which is not
directed by X"`), and dropped temporal-comparison clauses ("before his
daughter was born"). Fixing these requires deeper extractor/schema work,
not verifier gating.


