# Plan: a better Instant Evaluator (D7.5 v2)

Branch: `feature/d75-v2`. Crew: `.grok/HERDR.md`. This plan is what
the crew will execute **after** the user approves the agentic setup.

The target is a system that (a) implements D7.5 more faithfully, (b)
closes the concrete holes in `review.txt`, and (c) stays a proof of
concept: tiny judges, English first, no 200k Wikidata dump.

---

## What we have

A FastAPI dashboard with four prongs:

| Prong | D7.5 knowledge source | Current realisation | Review problem |
|-------|----------------------|---------------------|----------------|
| 1 | LLM-as-judge | MiniLM cosine + toxic-bert. **No LLM.** | Name is misleading (wXze). |
| 2 | Rule-based | Flesch + unvalidated lexicons + VADER | Fluency ≠ Flesch; nine-language claim oversold. |
| 3 | Extraction | spaCy triples vs ~86-entity Wikidata | Coverage <10%, AUC ≈ chance. |
| 4 | Intrinsic | top-k logprobs from generator | Unmeasured; remote backends often have no logprobs. |

Plus: equal weights with no guidance; 0.5 used as a silent fallback
for “unknown”; no radar plot; no latency numbers; no example of adding
a dimension; only Prong 3 has any external benchmark.

D7.5 itself is a **protocol**, not a claim that these particular
heuristics are SOTA. The paper was rejected for packaging them without
honesty, measurement, or a research question. v2 first makes the
instrument honest and measurable. A user study / “combination beats
single prong” experiment is a later phase.

---

## Non-goals for this PoC

- Judges larger than 1.5B.
- Fine-tuning / LoRA.
- Full Wikidata.
- Native-speaker lexicon campaign.
- Pushing to `origin/master`.
- Claiming nine production languages.

---

## Scout and git (standing, not a numbered phase)

D7.5 is a year old. Before each phase, **Scout** reads current systems
(RAGAS, DeepEval, G-Eval, Prometheus, FActScore/SAFE/Claimify, semantic
entropy follow-ons, ScandEval/MMTEB) and returns steal/adapt/skip
briefs in `docs/scouting/`. Protocol Steward drops anything that
breaks D7.5 or the ≤1.5B cap. Implementer only sees ideas that survived
both.

**Git Historian** is the only pane that commits on `feature/d75-v2`.
The human-readable history is `docs/commit-index.md` (table + newest-
first sections). No push to `origin/master`.

### Inspiration from peer EMNLP 2026 demos (`inspiration.txt`)

Scout + Protocol (2026-11-14). Full brief:
`docs/scouting/2026-11-14-inspiration.md`. Slot into existing phases:

- Phase 1: Idea 2 — `scored | unknown | error` (OmniProv gate + OpenTools states).
- Phase 3: Idea 1 — five-way NLI verdicts; Idea 4 — documented atomic claims.
- Phase 4: Idea 5 — dimension registry (user still to choose YAML vs keep hard-coded); Idea 8 — per-prong JSONL + latency chips (TraceForge-as-telemetry).
- Phase 6 seed: Idea 10 — prong ablation with CIs (Edge-RAG method, not its RAG stack).

Skipped: OmniProv co-training/provenance, OpenTools MCP marketplace,
TraceForge frozen DAGs, Edge-RAG pipeline.

---

## Phase 1 — Honesty (unblocks everything else)

Goal: a reader of the UI and README cannot be misled the way wXze was.

1. **Prong 1 naming.** Keep embeddings as the default fast path. Add
   an optional tiny generative judge (Phase 2). In UI, README, and API:
   family name “LLM-as-judge (Prong 1)” with a subtitle that states
   the active backend (`embeddings` | `tiny-llm`). If the LLM path is
   off, do not let the panel imply a generative judge ran.
2. **Unknown vs 0.5.** Introduce an explicit coverage/availability
   flag on `DimensionScore` (e.g. `status: scored | unknown | error`).
   Aggregator skips `unknown`. UI paints unknown as a dashed / grey
   mark, not a half-full bar. Applies to Wikidata misses, missing
   logprobs, missing prompt for relevance, missing tiny judge.
3. **Weight presets.** Ship four named presets that sum to 1, each
   with a one-line rationale:
   - Equal (explore)
   - Factual QA (upweight Prongs 3 and 1 relevance)
   - Safety (upweight toxicity + politeness)
   - Fluency / form (upweight Prong 2 + coherence)
   Default stays Equal; the UI must show *which* preset is active.
4. **Multilingual copy.** README, UI, locales: English prototype plus
   unvalidated lexicon mechanism. Nordic Linguist signs off.
5. **Reproducibility.** Align README / CONTRIBUTING / Quickstart on
   package name (`dankjewel`), Python 3.12, `requirements-minimal.txt`
   vs vLLM, and how to run tests without a GPU.

Exit: Reviewer can no longer quote the README as contradicting the
code on Prong 1, language support, or “Complete” vs skeleton.

## Phase 2 — Tiny LLM-as-judge (makes the name true)

Goal: Prong 1 can actually call an LLM, still in near-real-time.

1. Shared OpenAI-compatible client to a **local**
   `Qwen/Qwen2.5-0.5B-Instruct` (vLLM on Malvik). One process, task
   prefixes. Cap: 0.5B, fallback 1.5B only if 0.5B cannot emit
   parseable scores.
2. Dimensions (dual output, embeddings remain default):
   - Relevance, Semantic Coherence, Reliability — tiny judge JSON
     `{score: 0-1, rationale: ≤40 words}`.
   - Toxicity — keep toxic-bert; optional tiny-judge second opinion.
   - Sentiment/Emotion — D7.5 lists this under Prong 1; add as
     `aggregate=False` descriptive axis (tiny judge + existing VADER
     from Prong 2 as baseline).
3. Latency budget: judge call must be timed; if it exceeds the
   remaining online budget, return `unknown` and keep the embedding
   score.
4. Tests with a fake backend (no network in unit tests). One live
   smoke test marked optional.

Exit: toggling “tiny LLM judge” in the UI changes Prong 1 scores and
shows both tracks. Reviewer item “Prong 1 does not use an LLM” is
closed when the option is on, and honest when it is off.

## Phase 3 — Prong 3 salvage (still a lower bound, but useful)

Goal: extraction recall is the documented bottleneck; attack that
with the same 0.5B instance, and stop the seed DB from being the
whole story.

1. `src/extraction/llm_claim_extractor.py` — atomic claims, same
   `Claim` dataclass as spaCy. Dual output.
2. Modest seed expansion: entities that appear in
   `data/benchmark_claims.json` and a short hand list of TrustLLM-
   relevant Nordic entities. Still a seed, still labelled as such.
   No SPARQL dump.
3. FEVER script: keep operational vs oracle; add an
   `llm-extract + seed` condition; report coverage, binary AUC,
   conditional AUC, and n. Frame as lower bound.
4. UI: claims table already exists; add extractor source (spaCy /
   LLM) and coverage meter.

Exit: coverage is reported honestly; LLM extractor is comparable to
spaCy on the tiny English set; nobody can think 86 entities are
“Wikidata”.

## Phase 4 — Measurement and extensibility

Goal: YE7H / wXze “real-time is unmeasured” and “not shown to be
extensible”.

1. `scripts/measure_latency.py` — n warm + n timed runs of
   `/evaluate` and `/generate-and-evaluate` (tiny prompt), per prong,
   with hardware fingerprint. Write JSON + a markdown table the
   README can include.
2. Dual-output quality/latency table as in `TODO.md`.
3. Worked example in `CONTRIBUTING.md`: add a fifth (toy) dimension
   in < N lines, and add a tenth language lexicon file. Captain
   actually performs the toy dimension once so the example is real.
4. Failure cases: empty text, non-English under English models,
   generator without logprobs, Wikidata miss — documented and tested.

Exit: README has real numbers. A new dimension has a recipe.

## Phase 5 — Dashboard as instrument panel

Goal: D7.5 visualisation + the honesty flags from Phase 1, in the
browser.

1. Radar plot of the active aggregate dimensions.
2. Preset weights + custom sliders.
3. Unknown marks, coverage meter, latency chips, dual-score
   disclosure.
4. Verify generate → stream → evaluate end-to-end in the browser
   (desktop and ~390px).

Depends on Phases 1–4 for data; can start layout in parallel.

## Phase 6 — Research claim (after the PoC works)

Not in the first crew pass. Candidate falsifiable claims, pick one
later:

- Four-prong combination predicts a small human “useful for revising
  this output” rating better than any single prong.
- Surfacing Prong 4 uncertainty changes whether users regenerate.

Needs annotators. Do not pretend dual-output tables answer this.

---

## Suggested first slices (once approved)

Inspiration pass is done (`docs/scouting/2026-11-14-inspiration.md`).
Attack order below. One NTNU pane at a time. Eval/Git on Malvik Qwen
while Saturday/evening; NTNU Qwen in the weekday 08–18 window.

0. **Land the charter.** Git Historian commits `.grok/`, `docs/`, and
   `.gitignore` on `feature/d75-v2`. Never commit `inspiration.txt`,
   `review.txt`, or `deliverable/` (tex/txt inspiration stays local).
   No push to master.
1. **Measure the current system** (Eval, Malvik). `pytest`;
   `scripts/measure_latency.py` on `/evaluate` with a short English
   prompt; hardware fingerprint. Numbers before we change scores.
2. **Honesty core** (Implementer). `DimensionScore.status`:
   `scored | unknown | error`. Aggregator skips `unknown`. Tests for
   Wikidata miss, missing logprobs, missing prompt. README/API: Prong 1
   backend labelled `embeddings`; nine languages scoped.
3. **Instrument panel** (Dashboard, then Nordic on copy). Unknown
   marks, coverage meter, four weight presets (Equal / Factual QA /
   Safety / Fluency). Browser-check evaluate path.
4. **Review + land.** Reviewer vs `review.txt`. Git Historian commits.
5. **Tiny judge, one dimension** (Implementer + Eval). Shared local
   0.5B vLLM, `[JUDGE]` prefix, Relevance only, dual output. Stop and
   report if JSON is unusable.
6. **Prong 3** (later slice). Documented atomic claims + five-way
   relation labels on the same 0.5B instance.

YAML dimension registry (inspiration Idea 5) waits on a user decision.

---

## Risks

- 0.5B judge may be too weak for coherent JSON. Mitigation: strict
  schema, few-shot, then 1.5B, then stop and report.
- NTNU API rate window: Mon–Fri 08:00–18:00 Europe/Oslo, **one job
  at a time**. Crew must queue NTNU panes; no parallel NTNU fan-out
  in that window. Qwen panes use NTNU `Qwen/Qwen3.8-27B-FP8` then,
  Malvik `Qwen/Qwen3.8-27B` outside it (see `.grok/HERDR.md`).
- HPC courtesy for heavy batch (evenings/weekends) still applies to
  large offline jobs. The product 0.5B judge stays on Malvik.
- Two writers on `src/api.py` / `frontend/index.html`. Captain
  serialises those files.
