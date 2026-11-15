# Extending Dankjewel

This guide shows how to add a dimension and a language, with the size of the
change measured on a real example (the `Lexical Diversity` dimension, added
2026-11-15 on `feature/d75-v2`).

## Add a dimension

The complete worked example is `LexicalDiversity` in
`src/dimensions/prong2_dimensions.py`. The change was **34 lines in the
dimension module (including one import), 4 lines in the prong registration,
32 lines of tests, and a 16-line snapshot update** — 86 changed lines in total.

1. **Subclass `ScorableDimension`** in the module of the prong that owns it
   (`src/dimensions/prong2_dimensions.py` for rule-based axes). Give it a name
   and implement `evaluate(text, **kwargs) -> DimensionScore`.

2. **Return scores through `create_score()`**. That helper attaches the name,
   status (`scored` / `unknown` / `error`) and timing. Follow the house rules:

   - Values are in `[0, 1]`; pass `raw_value` when the natural scale differs.
   - Descriptive axes with no universal "better" direction pass
     `aggregate=False`; they are reported but excluded from prong averages.
   - No evidence means `status="unknown"`; a failed computation means
     `status="error"`. Never return a numeric value for either.
   - Record provenance in `metadata.evidence_sources` with the shared helper
     `from src.evidence import source`:
     `evidence_sources={'rules': source(score, 'scored', n_items)}`.
     The dashboard's signal matrix, coverage ribbon and claim strip read from
     this contract.

3. **Register it** in the prong's `_init_dimensions()`
   (`src/prongs/prong2_rule_based.py`): `self.register_dimension(LexicalDiversity())`.
   The registry is keyed by dimension name.

4. **Add a test** in the prong's test file: one scored case with pinned numbers,
   one no-evidence case that must be `unknown`, and a registration assertion
   (`"Lexical Diversity" in prong.dimensions`). If the dimension changes the
   flags-off response, regenerate `tests/evidence_flags_off_snapshot.json`
   deliberately (the additive-guarantee test will fail until you do), using the
   same input, `indent=1` and `sort_keys=True`, with timing keys and
   `evidence_sources` stripped.

5. **Document it**: add a row to the prong table in `README.md`.

That is the whole contract. The dashboard needs no change: dimensions render
from the API payload, and `evidence_sources` feeds the evidence panels
automatically.

## Add a language

1. Copy `src/resources/lexicons/en.yaml` to `<lang>.yaml` and translate the cue
   lists (keys must match `REQUIRED_KEYS` in `src/resources/lexicon_manager.py`;
   the test `test_lexicon_all_languages` enforces completeness).
2. Add the language code to `LANGUAGE_CODES` in `src/config.py` and to the
   frontend language selector (`frontend/index.html` + a
   `frontend/locales/<lang>.json` file, falling back to English for missing
   keys).
3. Mark the lexicon as validated only after a native speaker has reviewed it;
   the README currently labels the eight non-English lexicons as unvalidated
   translations, and that label must match the evidence.

## What this does not cover

- A fifth **prong** (new evaluator + API wiring + aggregation weight) is larger
  than a dimension; follow `src/prongs/prong2_rule_based.py` and add the prong
  to `src/pipeline.py`.
- New model-backed tracks should reuse `src/llm_judge_client.py` (task prefix,
  timeout, never fabricate a score) and default to off, as the judge, claims and
  verifier tracks do.
