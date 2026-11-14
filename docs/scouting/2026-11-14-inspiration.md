# Scouting brief — inspiration pass: OmniProv, OpenTools, TraceForge, Edge-RAG

Date: 2026-11-14. Scout → Captain. Read-only; no product code touched.

**Source.** User-supplied EMNLP 2026 System Demonstration reviews in
`inspiration.txt` (four submissions; reviews dated ≈ Aug 2026, "~3 months
ago"). The reviewed papers themselves were not available — only the
reviews — so each idea below cites the review text it came from.
Filters applied per `.grok/agents/scout.md`: fits a D7.5 prong
(`deliverable/protocol.tex`) or a D7.5 visualisation/aggregation/latency
surface (`deliverable/onlineeval.tex`); runs online (seconds); generative
judges ≤ 1.5B (`docs/improvement-plan.md` non-goals); no new prongs.

**Frame.** Dankjewel is an *online multi-prong evaluator of generated
text*. OmniProv is a claim verifier with provenance; OpenTools is a tool
marketplace; TraceForge is an agentic-workflow hardener; Edge-RAG is a
CPU RAG QA system. None of them is our system. Only their mechanisms
transfer, and only where they map onto Prong 1–4 or the dashboard.

**Prong map (one line per system).**

| System | Maps onto | Does not map onto |
|---|---|---|
| OmniProv | Prong 3 (verdict labels, decision gate, atomic claims), Prong 1 calibration framing | Provenance head, co-trained model (no source corpus, fine-tuning out of scope) |
| OpenTools | Cross-cutting metric schema/registry, explicit evaluation states (dashboard) | Tool schemas, MCP/agentic integration, community gatekeeping |
| TraceForge | Dashboard telemetry: run log, per-prong timings | Workflow DAG mining, OpenTelemetry infra, frozen-path reuse |
| Edge-RAG | Evaluation methodology: per-component ablation, honest negatives | The RAG pipeline itself (Planner/Navigator/Verifier), its DB stack |

---

## OmniProv — co-trained claim + source verification

Source: `inspiration.txt`, Submission 122, Reviewer 7ek4 (Aug 2026).
Multi-head DeBERTa: head 1 emits a five-way relation
(entailment / neutral / contradiction / partial / conflation), head 2
predicts source correctness; a decision gate green-lights a
(source, claim) pair only on entailment above threshold.

### Idea 1 — Five-way relation verdicts in Prong 3 · **adapt**

- **Prong:** 3 (Factual Accuracy / Factual Consistency; D7.5
  `description.tex` Prong 3 table).
- **Why:** Dankjewel's verification verdict is binary SUPPORTS/REFUTES,
  which is one reason covered claims show no discriminative signal.
  OmniProv's relation scheme captures *partial* support and *conflation*
  (two facts merged — exactly D7.5's internal-contradiction example,
  "Tromsø … Stockholm archipelago"). Realisable without training: the
  labels can be emitted by the 0.5B judge under a `[JUDGE]` task prefix,
  or by a small zero-shot NLI encoder; the conflation/partial cases can
  also be seeded by rule (spaCy detected multiple subjects/objects).
- **Files:** `src/prongs/prong3_extraction.py`,
  `src/dimensions/prong3_dimensions.py`, FEVER script under `scripts/`.
- **Cost:** CPU (0.5B vLLM or small NLI encoder); online.
- **Closes:** V55p ("fact-verification prong carries no discriminative
  signal even on the claims it covers"); wXze (Prong 3 AUC ≈ chance).
  Keep dual output: binary AUC stays comparable, relation labels are the
  upgraded track.

### Idea 2 — Decision gate → explicit scored/unknown status (with OpenTools Idea 4) · **adapt**

- **Prong/surface:** Prong 3 + aggregator + dashboard.
- **Why:** OmniProv green-lights only above threshold and rejects
  otherwise. That is precisely improvement-plan Phase 1 item 2 (status
  `scored | unknown | error` instead of the silent 0.5 fallback). Two
  independent reviewed systems converge on "explicit states, no
  half-answer", which strengthens the case. (Merged with OpenTools below
  to save a slot.)
- **Files:** `src/base.py` (DimensionScore), `src/aggregation/aggregator.py`,
  `src/api.py`, `frontend/index.html`.
- **Cost:** CPU (pure bookkeeping).
- **Closes:** V55p ("dashboard's handling of the pervasive neutral
  fallback score is never discussed").

### Idea 3 — Provenance head, co-trained multi-head model · **skip**

- **Why:** The provenance head needs a source corpus and retrieval;
  D7.5 Prong 3 verifies against a KB, it does not attribute sources.
  Co-training means fine-tuning, an improvement-plan non-goal for this
  PoC. Listing as "calibration only" (compare our Prong 3 against
  OmniProv-style labels later) is possible in Phase 6.
- Also: the review notes OmniProv's atomic-claim step is "only briefly
  explained" and its Docker was uninstallable — a cautionary tale for
  our Phase 4 reproducibility work, not an idea to import.

### Idea 4 — Atomic claim decomposition, documented · **adapt**

- **Prong:** 3 (extraction recall — the documented bottleneck).
- **Why:** OmniProv decomposes claims into atomic bits before the two
  heads; Edge-RAG's Planner decomposes questions into sub-parts. Our
  Phase 3 `llm_claim_extractor.py` already plans this; the scout note is
  (a) the decomposition spec must be *documented with examples* (the
  OmniProv reviewer penalised its absence), and (b) decomposition feeds
  the relation labels of Idea 1 (per-atomic-claim verdicts).
- **Files:** `src/extraction/llm_claim_extractor.py` (new, Phase 3),
  `src/extraction/claim_extractor.py`, docs.
- **Cost:** 0.5B vLLM (shared instance, `[CLAIMS]` prefix); online,
  latency-budgeted per Phase 2 item 3.
- **Closes:** Prong 3 coverage <10% (V55p, wXze) — the one honest lever
  we have short of a KB dump.

## OpenTools — community tool framework with non-executing inspection

Source: `inspiration.txt`, Submission 121, Reviewer Typm (Aug 2026).
Standardized tool schemas/wrappers, non-executing risk inspection,
explicit evaluation states, human gatekeeper, MCP server.

### Idea 5 — Declarative dimension/prong schema + registry · **adapt**

- **Prong/surface:** cross-cutting (all prongs) + dashboard.
- **Why:** OpenTools' core contribution is a standardized schema so new
  tools plug in without touching the pipeline. wXze's structural
  criticism is the exact analogue: no worked example of adding a fifth
  prong or tenth language, and RAGAS/lm-eval-harness/HF evaluate are
  held up as the bar. A declarative dimension spec (Pydantic/YAML:
  name, prong, backend, aggregate flag, weights-eligibility) plus a
  registry gives the Phase 4 "toy dimension in < N lines" example teeth,
  and makes the tenth-language case (`src/resources/lexicons/*.yaml`)
  demonstrable.
- **Files:** `src/base.py`, `src/dimensions/base_dimension.py`,
  `src/pipeline.py`, `docs/CONTRIBUTING.md`.
- **Cost:** CPU (refactor only).
- **Closes:** wXze ("does not yet demonstrate the configurability");
  supports YE7H's extensibility note.

### Idea 6 — Explicit evaluation states · **adapt** (merged into Idea 2)

- OpenTools evaluates tools through named states without execution; we
  surface per-dimension `scored | unknown | error` without pretending a
  score exists. Same implementation as Idea 2; credited to both systems.

### Idea 7 — Tool schemas, MCP server, community gatekeeping · **skip**

- **Why:** Dankjewel evaluates generated text; tools and agentic
  workflows are another field. MCP exposure of the evaluator could be a
  future integration story, but it adds no D7.5 prong and no
  `review.txt` fix. Non-executing risk inspection has no analogue on
  running text.

## TraceForge — hardening workflows from OpenTelemetry traces

Source: `inspiration.txt`, Submission 120, Reviewer 28F3 (Aug 2026).
Retains successful traces as immutable workflows via a Control Plane
with a human-in-the-loop reuse threshold.

### Idea 8 — First-class per-prong telemetry: timings + run log · **adapt**

- **Surface:** dashboard + eval scientist (D7.5 `onlineeval.tex`
  "Efficiency Requirements" and "Visualization").
- **Why:** TraceForge's whole premise is that execution traces are the
  valuable artifact. For us the analogue is the evaluation event: emit
  per-prong wall-clock timings and the dimension scores of every run as
  structured records (JSONL or SQLite), append-only. In-request timings
  surface as UI latency chips; the run log gives history/comparison
  across prompt iterations — the "steer prompting" workflow D7.5's radar
  plot implies. It also makes the Phase 4 latency harness measure the
  real thing rather than an instrumented copy. No OpenTelemetry
  dependency: the *idea* (immutable event log, per-stage spans), not the
  tech.
- **Files:** `src/pipeline.py` (timing hooks), `src/api.py`,
  `frontend/index.html`, new `scripts/`/storage for the run log,
  `scripts/measure_latency.py` consumes it.
- **Cost:** CPU (append-only log); online overhead ≈ a timestamp.
- **Closes:** YE7H ("no latency, throughput, scalability"); wXze
  ("real-time framing is unmeasured"); partially the YE7H user-workflow
  point (history is a usability feature, not a user study — that
  remains Phase 6).

### Idea 9 — Frozen workflow reuse / Control Plane / human hardening threshold · **skip**

- **Why:** Agentic-path reuse is outside the evaluate-generated-text
  frame. The human-in-the-loop *persist your preset* gesture is already
  covered by Phase 1 item 3 (weight presets) + Idea 8's run log.

## Edge-RAG — CPU-only RAG, ablated component-wise

Source: `inspiration.txt`, Submission 34, Reviewer zREo (Aug 2026).
Planner/Navigator/Verifier on Qwen-1.5B, <16 GB RAM CPU; careful
ablations with CIs, negative results reported honestly.

### Idea 10 — Per-component prong ablation protocol · **adapt**

- **Surface:** evaluation methodology (Eval Scientist; Phase 6 seed).
- **Why:** Edge-RAG's credited contribution is the ablation ("the
  Navigator matters; the Verifier hurts on 2Wiki"), exactly the
  evidence class wXze demands ("no comparison showing the combination
  helps") and V55p ("three of the four prongs are not validated").
  Adapt as: small labelled set (start from the FEVER dev split already
  in-repo + a tiny human-usefulness set later), score with each prong
  alone and combined, report per-prong and ablated deltas with CIs.
  Offline batch — D7.5's online requirement does not apply to the
  validation harness itself.
- **Files:** `scripts/` (new ablation script reusing the FEVER
  machinery), `src/aggregation/` for weight variants, docs/tables.
- **Cost:** CPU offline; no new runtime models.
- **Closes:** wXze (no falsifiable claim / no comparative justification);
  V55p (unvalidated prongs) — this is the cheapest path to the Phase 6
  research claim.

### Idea 11 — The RAG pipeline itself (Planner/Navigator/Verifier, LanceDB, REBEL/KuzuDB) · **skip**

- **Why:** QA system, wrong frame. Edge-RAG's own reviewer found the
  absolute performance weak. Keep only the honesty style and the
  ablation method (Idea 10); their <16 GB CPU envelope matches our
  constraints and is moral support, not a mechanism.

---

## Closing table

| # | Idea | Prong / surface | Verdict | PoC-sized? |
|---|------|-----------------|---------|-----------|
| 1 | Five-way relation verdicts (entail/neutral/contradict/partial/conflation) | Prong 3 | adapt | Yes — CPU, 0.5B judge or NLI encoder, online |
| 2 | Decision gate → explicit `scored/unknown/error` states (OmniProv + OpenTools) | Prong 3 + aggregator + UI | adapt | Yes — CPU, bookkeeping only |
| 4 | Documented atomic claim decomposition feeding per-claim verdicts | Prong 3 | adapt | Yes — 0.5B vLLM, latency-budgeted |
| 5 | Declarative dimension/prong schema + registry | All prongs + extensibility | adapt | Yes — refactor, CPU |
| 8 | Per-prong telemetry: latency spans + immutable run log | Dashboard + Eval Scientist | adapt | Yes — CPU, JSONL/SQLite |
| 10 | Per-component prong ablation protocol with CIs | Eval methodology (Phase 6 seed) | adapt | Yes — CPU, offline batch |
| 3 | Provenance head / co-trained multi-head model | Prong 3 | skip | No — needs source corpus + fine-tuning (non-goal) |
| 7 | Tool schemas, MCP server, community gatekeeping | — | skip | Out of frame (text evaluator) |
| 9 | Frozen workflow DAGs, Control Plane, hardening threshold | — | skip | Out of frame (agentic workflows) |
| 11 | Edge-RAG pipeline (Planner/Navigator/Verifier, RAG stack) | — | skip | Wrong system type (RAG QA); weak results per its own review |

Six steal-or-adapt items, all inside the ≤1.5B cap, none adds a prong.
Items 2, 4, 5, 8 land in existing improvement-plan phases (1, 3, 4, 5);
items 1 and 10 are new candidates the Captain may slot into Phase 3 and
Phase 6 respectively.

---

## Protocol Steward filter (dj-protocol, 2026-11-14)

| # | Verdict | D7.5 / test |
|---|---------|-------------|
| 1 Five-way relation | **IN PROTOCOL** | Prong 3 evaluates claims with NLI. Test: Prong 3 emits SUPPORTS / REFUTES / PARTIAL / CONFLATION / NEUTRAL / UNKNOWN and maps to 0–1. |
| 2 scored/unknown/error | **IN PROTOCOL** | Explicit states required for the dashboard. Test: each dimension has a status flag; UI never paints unknown as a silent 0.5. |
| 4 Atomic claims, documented | **IN PROTOCOL** | Extraction prong must extract atomic claims before evaluation. Test: `llm_claim_extractor.py` JSON list + documented examples. |
| 5 Schema + registry | **NEEDS USER DECISION** | Protocol allows configurability; does not prescribe YAML vs hard-coded. |
| 8 Per-prong telemetry | **IN PROTOCOL** | Efficiency + visualisation. Test: JSONL per prong + latency chips. |
| 10 Prong ablation + CIs | **IN PROTOCOL** | Comparative evidence that each prong adds value. Test: `scripts/` ablation on FEVER, AUC + CIs. |
| 3, 7, 9, 11 | **SKIP confirmed** | Provenance/fine-tune, tool marketplace, frozen DAGs, RAG QA — outside D7.5. |

Honesty: none of the ADAPT items re-opens nine-language, LLM-as-judge naming, or 0.5-as-quality overclaims.

Open question left for the user: standardise a declarative dimension schema now, or keep hard-coded config until Phase 4.
