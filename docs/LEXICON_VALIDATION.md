# Lexicon validation status

**Audit date:** 2026-11-16. **Scope:** the nine lexicons in
`src/resources/lexicons/` (da, de, en, fo, is, nl, nb, nn, sv).

**Method (mechanical):** key parity against `en.yaml`, list lengths, exact
duplicates, and verbatim English cues left in non-English files. **Translation
quality was not assessed**: that requires a native speaker per language. The
Nordic Linguist pane was briefed for this pass but returned no usable output
(the Grok weekly limit was exhausted), so this document records the verifiable
mechanical part and the native-review checklist.

## Results

| Language | Keys complete | Mechanical issues | Validation status |
|----------|---------------|-------------------|-------------------|
| en (English) | — (reference) | none | validated in-house, used in the project's own tests |
| da (Danish) | yes | none | unvalidated translation |
| de (German) | yes | none | unvalidated translation |
| fo (Faroese) | yes | none | unvalidated translation; Norwegian Nynorsk backend used as proxy |
| is (Icelandic) | yes | none | unvalidated translation; Norwegian Nynorsk backend used as proxy |
| nl (Dutch) | yes | none | unvalidated translation; Dutch-specific Flesch backend |
| nb (Norwegian Bokmål) | yes | none | unvalidated translation |
| nn (Norwegian Nynorsk) | yes | none | unvalidated translation |
| sv (Swedish) | yes | none | unvalidated translation |

- All nine files share the same six cue keys and have no empty or short lists.
- No duplicate cue entries were found.
- The only cues shared verbatim with English are `lol` and `hey`; both are
  legitimate informal loanwords in these languages, not untranslated leftovers.

## What a native-speaker review must still check

1. **Register and politeness:** the polite/rude cue lists carry culture-specific
   weight (e.g. German `Sie`/`du`, Dutch `u`/`jij`, Norwegian `De`/`du`).
2. **False friends and near-misses:** e.g. German `eventuell`, Dutch `bellen`,
   Danish/Norwegian `rar`.
3. **Bokmål vs Nynorsk:** the two Norwegian files must differ where the written
   standards differ; a shared translation would hide that.
4. **Faroese and Icelandic:** vocabulary coverage for informal cues and the
   appropriateness of the Nynorsk readability proxy.
5. **Coverage:** whether the cue lists capture the informal, aggressive and
   hedging language the dimensions claim to score, or only a formal subset.

## Wording for the nine-language claim

Use: “The interface ships with nine languages; the English lexicons are
validated, and the eight non-English lexicons are unvalidated translations.
Scores for those languages should be read as indicative.”
Do not claim multilingual validation until a native speaker has reviewed each
file; cite this document as the status record.
