# Scouting brief — competitive landscape for the Instant Evaluator

Date: 2026-11-16. Scout → Captain. Read-only; no code edits, no commits.
Sources: vendor sites/docs fetched 2026-11-16 (URLs inline); GitHub API
metadata (license, stars) fetched 2026-11-16 via api.github.com;
academic items cite the two earlier briefs in this directory
(`2026-11-14-inspiration.md`, `2026-11-14-claim-extraction.md`), which
carry anthology IDs. Anything I could not verify today is marked
**unverified**. Note: `web_search` was unavailable (quota); facts were
verified by direct page fetches instead.

Inputs read: `README.md`, `review.txt`, `docs/EXTERNAL_EVALS.md`,
`.grok/agents/scout.md`, `.grok/HERDR.md`.

---

## 1. Comparison table

Deployment: ☁ = SaaS, ⬇ = self-hostable, 💻 = local library/CLI.
"Factuality handling" = whether the product grounds a score in evidence
(sources, per-claim verdicts) or emits opaque scores.

| # | Player | Owner | What it measures | Deployment / license | Model dependency | Factuality / evidence | Multilingual | Strengths / weaknesses |
|---|--------|-------|------------------|----------------------|------------------|----------------------|--------------|------------------------|
| 1 | LangSmith | LangChain (raised $300M Series C @ $3B — site banner) | Agent tracing, monitoring, online evals ("online LLM-as-judge and code evals" — langchain.com/langsmith), datasets/experiments | ☁ (+ self-hosted enterprise tier — **unverified**) | Proprietary; cloud-LLM judges | Judge scores on traces; no per-claim KB grounding shown in public docs | SDKs for major langs; evaluator language coverage **unverified** | Distribution + agent-ops breadth; scores are opaque judge outputs, cloud-metered, evidence-free |
| 2 | Langfuse | ClickHouse (LICENSE header: "Copyright ClickHouse, Inc.") | OTel tracing, prompt mgmt, datasets, LLM-as-judge evals, dashboards (langfuse.com/pricing) | ☁ or ⬇ self-host; MIT core + proprietary `ee/` dirs (LICENSE verified) | BYO models; judge prompts user-defined | Scores attached to traces; no claim-level evidence or KB | EU/US/JP data regions; i18n of UI **unverified** | Strongest open self-hosted observability + evals; still trace-centric, no evidence-first scoring anatomy |
| 3 | Braintrust | Braintrust (YC) | Trace observability, evals (LLM/code/human scorers), "patterns" discovery, Loop agent (braintrust.dev) | ☁; Enterprise offers "on-prem or hosted deployment" (pricing page verified) | Proprietary platform, metered ($0 / $249 / custom) | Scores + "evidence-backed pattern discovery" over traces; no KB grounding | **Unverified** | Polished loop from traces→datasets→evals; SaaS metering, no local-only mode, no factuality evidence |
| 4 | Arize Phoenix | Arize AI | Tracing (OTel/OpenInference), LLM-as-a-judge evals, datasets/experiments (arize.com/docs/phoenix) | ⬇ self-host + ☁ (Arize AX managed); **Elastic License 2.0** (LICENSE verified — relicensed from its earlier Apache era) | BYO; eval models user-configured | Judge/classifier scores per span; hallucination evals exist; no per-claim source attribution | **Unverified** | Best-positioned open eval UI; ELv2 restricts hosted resale; no online-during-generation mode |
| 5 | Galileo | → Splunk (galileo.ai now redirects into Splunk "Agent Observability" — acquisition) | Agent observability, Luna judge evaluators (**unverified**, pre-acquisition) | ☁ / Enterprise (per Splunk pages) | Proprietary | Judge scores; **unverified** post-acquisition | **Unverified** | Enterprise muscle via Splunk; product identity in flux |
| 6 | Patronus AI | Patronus | Pivoted: now "a behavioral research lab for AI" — benchmarks (TRAIL, GlobeBench), agent training data (patronus.ai homepage) | Previously Evaluators API ☁; current platform status **unverified** | Proprietary judges | Judge APIs; no KB evidence | **Unverified** | Strong eval research; the standalone eval platform pitch has receded |
| 7 | Fiddler | → CrowdStrike (acquisition banner on fiddler.ai) | "AI Control Plane": continuous evaluations, agentic observability, policy guardrails, ML monitoring | ☁ / enterprise | Proprietary | Continuous eval scores + policy enforcement; no per-claim KB evidence | **Unverified** | Governance/guardrail depth for enterprises; heavy, closed, priced accordingly |
| 8 | W&B Weave | Weights & Biases | Tracing, evaluations, guardrails, playground inside W&B platform | ☁ + self-managed W&B server (**unverified** details) | Proprietary | Scorer-based; no claim-level grounding | **Unverified** | MLOps incumbency; eval is a feature of a broad platform |
| 9 | DeepEval / Confident AI | Confident AI | Pytest-style LLM evals: G-Eval, RAG, agent, safety, multi-turn metrics; "local backend storage" (deepeval.com docs nav) | 💻 open source Apache-2.0 (19.5k★) + ☁ Confident platform (proprietary) | Cloud-LLM judges by default (G-Eval); BYO possible | Metric scores with *reasons* from the judge; no KB/evidence citations | Language adaptation **unverified** | Easiest OSS on-ramp; offline-capable metrics; but scores remain judge-asserted, not evidence-grounded |
| 10 | Ragas | VibrantLabs (repo moved to `vibrantlabsai/ragas`) | RAG metrics: faithfulness, context precision/recall, agent metrics (docs.ragas.io nav) | 💻 Apache-2.0 (16.3k★) | Cloud-LLM judges for most metrics | "Faithfulness" = claim-decomposition vs retrieved contexts — closest OSS analogue to Prong 3, but needs retrieved contexts and a cloud judge | Docs include "Adapt Metrics to Languages" | The reference factuality-metric library; RAG-frame only, offline batch, no dashboard, no KB mode |
| 11 | TruLens | TruEra → Snowflake lineage (**unverified**); OSS under `truera/trulens` | Feedback functions (RAG triad: groundedness, context relevance, answer relevance), experiment tracking (trulens.org) | 💻 MIT (3.7k★) | Cloud-LLM judges for feedback | Groundedness feedback = judge-asserted; no evidence surfaces | **Unverified** | Conceptual ancestor of "evidence for RAG"; batch-oriented, notebook-first |
| 12 | Opik | Comet (comet-ml/opik) | Tracing, automated evaluations, production dashboards | ⬇ self-host + ☁; Apache-2.0 (23.4k★) | BYO + LLM-judge heuristics | Judge scores; no KB grounding | **Unverified** | Full-featured OSS alternative to Langfuse; same trace-centric gap |
| 13 | promptfoo | promptfoo (promptfoo/promptfoo) | Declarative eval of prompts/models/RAGs, red teaming, guardrails (promptfoo.dev/docs) | 💻 MIT (27.2k★), CI-friendly | Any provider incl. local; cloud judges optional | Assertions incl. factuality checks via judges; matrix views of outputs | Provider-agnostic; language claims **unverified** | Best OSS matrix/CI eval; config-driven, offline-batch; no online streaming eval or evidence UI |
| 14 | OpenAI Evals | OpenAI (openai/evals) | Benchmark registry + harness for model-level evals | 💻 open source (19.7k★) | OpenAI-centric | Dataset scores; no runtime evaluation | **Unverified** | Useful registry; stale relative to the 2025–26 wave; offline only |
| 15 | HF Evaluate | Hugging Face (huggingface/evaluate) | Classic ML metrics (BLEU/ROUGE/etc.) + comparison/visualisation | 💻 Apache-2.0 (2.5k★) | None (metric library) | None | Metric-specific | Standard metrics toolbox; no LLM-era factuality, no UI |
| — | Guardrails AI / NeMo Guardrails | guardrails-ai / NVIDIA-NeMo/Guardrails (7.6k★ / 7.5k★) | Runtime input/output validators & conversational rails (adjacent) | 💻 Apache-2.0 | Varies | Validators can block; evaluation is a side effect | Varies | Overlap only where "score" becomes "enforce"; out of our category |

Academic/demo systems (detailed in the two earlier briefs): MiniCheck
(EMNLP 2024, 2024.emnlp-main.499), FActScore (EMNLP 2023,
2023.emnlp-main.741), FacTool (arXiv 2307.13528), VeriScore (Findings
EMNLP 2024, 2024.findings-emnlp.552), Claimify (arXiv 2502.10855),
AVeriTeC/FEVER shared tasks (2024.fever-1.1, 2025.fever-1.15),
ClaimBuster (`utaresearch/claimbuster-spotter`, GPL-3.0, check-worthy
claim spotting), Full Fact (UK charity; open automation tools, limited
public repo surface — **unverified**). None of these ships an
interactive *evidence-first online dashboard*; they are batch
pipelines, datasets, or verifier models. OmniProv (EMNLP 2026, rejected)
had a claim-level verdict matrix in an agent chat UI but against tool
traces, and did not survive review (see `omniprov.txt`).

---

## 2. The 3–5 closest competitors

1. **DeepEval (Confident AI)** — closest open-source framework: local
   pytest-based evals, broad metric families, Apache-2.0. Gap it
   exposes: DeepEval's metrics are judge-asserted scores with reasons;
   there is no per-claim evidence, no KB mode, no online
   during-generation evaluation, no unknown-vs-scored semantics.
2. **Ragas** — closest factuality methodology: faithfulness by claim
   decomposition against contexts. Gap: RAG-frame only (needs retrieved
   contexts), offline batch, no UI, cloud-judge dependent; now under a
   new org (`vibrantlabsai/ragas`).
3. **Arize Phoenix** — closest self-hostable *dashboard*: eval scores
   on traces with an open UI. Gap: ELv2 license, trace-centric,
   offline-judge evals; nothing computed online or grounded in a KB.
4. **TruLens** — closest conceptual kin (feedback functions =
   multi-signal scoring; RAG triad). Gap: notebook/batch oriented,
   judge-asserted, no streaming or evidence panels.
5. **promptfoo** — closest local/CI harness with matrix output
   comparison. Gap: config-driven batch testing; no live evaluation,
   no KB, no evidence-first UI.

Commercial platforms (LangSmith, Braintrust, Fiddler, Galileo/Splunk,
Weave) are in an adjacent category — trace observability with judge
scores — and none of the public materials reviewed shows per-claim
evidence or an offline/local-only evaluation mode.

## 3. What Dankjewel offers that they do not

1. **Online, during-generation evaluation.** Scores computed in
   seconds on streaming output (`/generate-and-evaluate`, measured warm
   p95 ≈ 1.0 s with all tracks on — README latency table, 2026-11-14).
   Every competitor's evaluation is batch/experiment-oriented; the
   commercial "online evals" run asynchronously on ingested traces.
2. **Evidence-first UI.** Score anatomy, coverage meters, per-claim
   evidence, the signal matrix, track comparison (dual-output
   embedding-vs-tiny-judge). No reviewed competitor shows *why* a score
   is what it is at claim level; they show a judge's number and at best
   a one-line reason (DeepEval).
3. **Honest unknown semantics.** `scored | unknown | error` with
   unknown excluded from aggregates — the reviewed competitors either
   emit a number or fail silently. This is rare enough to be a
   *contribution*, per the inspiration brief's OmniProv/OpenTools
   convergence finding.
4. **Local-first, cloud-optional.** Prongs 1–3 on CPU with fixed small
   models (0.5B judge, 1.5B claims, 770M MiniCheck verifier); no
   metered cloud judges, no data egress. The commercial stack is
   SaaS-first and metered; even the OSS frameworks lean on cloud LLM
   judges for their headline metrics (DeepEval G-Eval, Ragas
   faithfulness, TruLens feedback, Phoenix judges).
5. **A published protocol.** Evaluation structure follows TrustLLM
   D7.5 — a citable, versioned protocol rather than a vendor's metric
   list. None of the competitors names a protocol.
6. **Fully specified KB-verification path** with honest lower-bound
   reporting (seed 122 entities, FEVER coverage 0.3%, SciFact verifier
   AUC 0.835 — README/EXTERNAL_EVALS.md). Competitors either have no
   KB path at all or hide model dependence.

## 4. What NOT to claim

1. **"First evaluation dashboard."** Phoenix, Opik, Langfuse and
   commercial platforms ship dashboards. Claim the *specific* niche:
   online + evidence-first + local, and cite them as the contrast set.
2. **"Better factuality than X."** Our seed-KB coverage is 0.3% on
   FEVER; Ragas/MiniCheck-style groundedness on retrieved contexts is
   stronger in their frame. We benchmark and report; we do not win
   head-to-head (this is also the wvR3 fairness lesson from
   `omniprov.txt`).
3. **"Nine languages."** English validated; eight Germanic lexicons are
   unvalidated translations (README says so; keep saying so).
4. **"Real-time" without the number.** Any real-time claim must cite
   `measure_latency.py` output and hardware, or a reviewer will write
   wXze's paragraph again.
5. **Novelty of individual metrics.** Flesch, VADER, MiniLM, MiniCheck
   are assembled components (wXze). Novelty claims belong to the
   online-evidence framing, the unknown-semantics design, and the
   protocol mapping.
6. **Agent/provenance claims.** Multi-tool provenance is OmniProv's
   frame (rejected); ours is generated text vs KB. Do not blur them.
7. **"Open-source alternative to LangSmith"** as a headline. The trace
   observability market has >$3B-funded incumbents and consolidators;
   we are not in that race and should not imply it.

## 5. Positioning and citation advice for the paper's related work

**Angle 1 — the missing middle.** Between (a) academic
decompose-then-verify pipelines that are offline and batch (FActScore,
VeriScore, Claimify, MiniCheck — cite with anthology IDs from the
claim-extraction brief) and (b) commercial observability platforms
whose evaluation is SaaS, metered, and opaque (LangSmith, Braintrust,
Fiddler — cite URLs), Dankjewel is an *online, evidence-first,
local-first instrument*. One sentence of the form: "Existing open
frameworks (Ragas, DeepEval, TruLens, Phoenix) evaluate offline against
datasets or traces; commercial platforms add observability but depend
on cloud LLM judges; neither computes evidence-grounded, multi-prong
scores during generation."

**Angle 2 — consolidation as opportunity.** The 2025–26 landscape
consolidated around agent observability (LangChain $300M raise;
Galileo→Splunk; Fiddler→CrowdStrike; Patronus pivot; Langfuse→ClickHouse)
and licence churn (Phoenix→ELv2). A small, Apache-2.0, CPU-runnable,
offline-capable evaluator aligned to a public protocol fills the gap
this consolidation created — this is a *context* argument for the demo
paper, made in one short related-work paragraph, not a market analysis.

**Citation practice.** Cite competitors by what they do, with URLs and
access dates (2026-11-16); avoid disparagement; mark items checked only
via marketing pages as such in any internal notes. For OSS frameworks
cite the repos (stars/licence as of 2026-11-16: DeepEval 19.5k,
promptfoo 27.2k, Opik 23.4k, Phoenix 12.3k ELv2, Langfuse 37.5k MIT+ee,
Ragas 16.3k, TruLens 3.7k MIT). Do not cite star counts in the paper.

**Scout's caveats.** Galileo's post-acquisition feature set, Patronus's
platform status, W&B Weave specifics, LangSmith self-hosting tiers, and
Braintrust SDK licensing are marked unverified above; if the paper
names any of them in a table, someone should re-check those five before
submission.

---

## Addendum (2026-11-16, second dispatch) — multilingual LLM-as-judge candidates

Task from the Captain: candidate judges for **multilingual** LLM-as-judge
evaluation under the runtime cap (~≤1.5B; calibration may use larger
models). Facts below verified 2026-11-16 via the Hugging Face API
(`api.github.com`-equivalent metadata: license, gated status, downloads),
model-card READMEs (`huggingface.co/<id>/raw/main/README.md`), the arXiv
export API (export.arxiv.org), and the GitHub API. Gemma and Llama model
cards are access-gated, so their language counts remain as briefed and
are marked **unverified**.

### 1. Runtime tier (≤1.5B)

| Candidate | Size | Languages | License / access | Context | Alignment | Judge suitability |
|---|---|---|---|---|---|---|
| **Qwen2.5-1.5B-Instruct** (in-stack already) | 1.5B | "over 29 languages" (card verified; list is CN/EU-centric; Nordic unclear) | Apache-2.0, open | card says family "up to 128K"; 1.5B-specific 32K **unverified** | Instruct, JSON-strong (card: "generating structured outputs especially JSON" — verified) | Proven in this repo (claims track, warm 211 ms). Best JSON obedience of the tier; Nordic coverage is the open question |
| **Gemma-3-1B-IT** | 1.0B | 140+ claimed — **unverified** (card gated) | Gemma Terms, gated=manual (verified) | ~32K **unverified** | Instruct (weak reasoning at 1B) | Broader claimed multilinguality; 1B instruction-following is the risk; license acceptance step required |
| **Qwen3-1.7B** | 1.7B (**13% over cap**) | "100+ languages and dialects" + multilingual instruction following (card verified) | Apache-2.0, open | 32,768 (card verified) | Instruct, hybrid thinking mode | Strongest multilingual + instruction-following candidate; needs a user decision to raise the cap to 1.7B |
| **EuroLLM-1.7B** | 1.7B (over cap) | 35 verified in card (all EU languages + 11 more incl. Norwegian; Danish, Dutch, Swedish present; **no Icelandic/Faroese**) | Apache-2.0, open | RoPE, card gives no single figure | Base model (pretrained incl. parallel/MT data — card verified); **not instruction-aligned**; instruct variant **unverified** | Designed for exactly our language set; would need an SFT/prompting pass before it can judge |
| **Llama-3.2-1B/3B-Instruct** | 1B/3B | 8 official languages — **unverified** (card gated) | Llama 3.2 community, gated=manual (verified) | 128K **unverified** | Instruct | The 8 official languages include no Nordic language — wrong tool for TrustLLM's nine |
| **Salamandra-2B** (+ `-instruct`) | 2B (over cap) | 35 European languages, 12.9T tokens (card verified) | Apache-2.0, open | 8,192 (card verified) | Base verified; instruct exists (**unverified** strength) | Same EU-35 story as EuroLLM; 8K context is tight but fine for paragraph judging; over cap |

### 2. Calibration / reference tier

| Candidate | Size | License / access | Note |
|---|---|---|---|
| **Qwen3-8B** | 8B | Apache-2.0, open (verified) | Recommended local calibration judge: same family as runtime judge (limits family bias as a *known* confound), huge adoption (6.1M downloads), 100+ language claim per Qwen3 family card (**unverified** for 8B specifically) |
| Qwen3-4B | 4B | Apache-2.0 (verified) | Cheaper calibration fallback |
| Gemma-3-4B/12B/27B-IT | 4–27B | Gemma Terms, gated=manual (verified) | Strong multilingual line; gating + license terms |
| EuroLLM-9B | 9B | Apache-2.0, gated=auto (verified) | Best-matched language set for calibration; accept terms once |
| Salamandra-7B-instruct | 7B | Apache-2.0 (verified) | EU-35 calibration option |
| Aya-Expanse-8B | 8B | **CC-BY-NC-4.0** (verified) | Non-commercial — calibration/eval-only, never runtime |
| Mistral-Nemo-Instruct-2407 / Mistral-Small-24B-Instruct-2501 | 12B / 24B | Apache-2.0 (verified) | General-purpose calibration options |
| Command R7B (c4ai-command-r7b-12-2024) | 7B | **CC-BY-NC-4.0** (verified), gated=auto | Same NC restriction |
| GPT-SW3 (AI-Sweden-Models, up to 40B) | 0.1–40B | "other" license, gated=manual (verified) | Historical Nordic reference; access friction |
| Proprietary reference judges (GPT-5.x / Claude / Gemini) | — | API | Reference only; per `omniprov.txt`, LLM-generated gold labels without IRR is a review-killing pattern — any proprietary judge scores must be treated as reference, never as truth |

### 3. Nordic specialists (nb/nn/sv/da/is/fo)

| Model | Size | Nordic coverage (verified from cards unless noted) | License | Judge suitability |
|---|---|---|---|---|
| **Viking-7B / 13B** (LumiOpen) | 7B/13B | English, Finnish, Swedish, Danish, Norwegian, Icelandic + code (card verified). **No Faroese.** Bokmål/nynorsk split unspecified | Apache-2.0 (verified) | Best open Nordic coverage incl. Icelandic; base-model alignment state thin; calibration tier |
| **NorMistral-7b-warm / -warm-instruct** (ltg/norallm) | 7B | Norwegian (card tags `norwegian`; nb+nn per card text — verified) | Apache-2.0 (verified; instruct card: SFT only, no preference optimisation, 4,096 ctx) | Norwegian-judge specialist; **brief said "NorMistral-11B" — correct ID is 7B** (verified via HF search) |
| GPT-SW3 | up to 40B | Nordic focus (Scandinavian) | custom/"other", gated | Reference only |
| **NorwAI-Magistral-24B-reasoning** | 24B | NTNU's own Norwegian model (crew's Nordic Linguist pane per HERDR.md); HF listing verified, card gated | **unverified** (manual gate) | The natural Norwegian calibration judge given existing NTNU access |

Faroese (fo) and Icelandic (is) remain the weak point across every
candidate except Viking (is only, no fo) — there is no aligned small
model covering Faroese. Any fo judge claim stays out of scope.

### 4. Benchmarks for judge quality (names/dates verified via arXiv export API)

- **JudgeBench** — "JudgeBench: A Benchmark for Evaluating LLM-based
  Judges", arXiv, published 2024-10-16 (arXiv 2410.12784). Judge-quality
  benchmark on hard reasoning claims; English.
- **M-RewardBench** — "M-RewardBench: Evaluating Reward Models in
  Multilingual Settings", arXiv, published 2024-10-20. The multilingual
  reward/judge benchmark to cite for language-fairness context.
- **MT-Bench-101** — "MT-Bench-101: A Fine-Grained Benchmark for
  Evaluating Large Language Models in Multi-Turn Dialogues", arXiv,
  published 2024-02-22. Multi-turn; adjacent (our judge scores single
  outputs).
- **MT-Bench** (original) — "Judging LLM-as-a-Judge with MT-Bench and
  Chatbot Arena", arXiv, published 2023-06-09. The position-bias
  methodology source.
- **EuroEval** — `EuroEval/EuroEval`, MIT, 204★ ("The robust European
  language model benchmark"; GitHub API verified 2026-11-16). The
  European-language harness to borrow dataset tasks from; ScandEval
  successor (**successor claim unverified**).
- Bonus find (arXiv, published 2026-08-23): **"Rank Reversal in
  Multilingual LLM Judges: A Label-Free Double-Centering Calibrator"** —
  recent evidence that multilingual judges suffer rank reversal across
  languages, with a label-free correction. Cite in the test plan's
  rationale; the double-centering idea is a candidate Phase-6
  calibration trick.

### 5. Recommendation

- **Runtime judge:** stay with **Qwen2.5-1.5B-Instruct** for the v2 PoC
  (already in-stack, JSON-proven, Apache-2.0, 29+ languages) and extend
  it multilingually behind the existing dual-output flag. **Ask the
  user** whether the ≤1.5B cap can stretch to 1.7B for
  **Qwen3-1.7B** — it is the materially better multilingual judge
  (100+ languages verified, stronger instruction following) at a 13%
  overage. If Nordic quality at runtime proves weak, the escalation
  path is EuroLLM-1.7B/Salamandra-2B (35 EU languages, Apache-2.0) —
  both over cap, both need a user decision, EuroLLM needs alignment.
- **Calibration judge:** **Qwen3-8B** locally (Apache-2.0), plus one
  proprietary reference judge for correlation only, plus
  **NorwAI-Magistral-24B** for Norwegian rows (NTNU access exists).
  Never ship calibration scores as product output.

### 6. 30-item × 9-language judge-agreement test plan

Languages: da, de, en, fo, is, nb, nn, nl, sv (the repo's lexicon set).
Items: 30 per language = 270 judgments per judge. Reuse the FEVER-style
fixture discipline: 10 supported, 10 contradicted, 10 unverifiable
claims, each rendered as a one-paragraph output with a prompt.

| Check | Method | Pass signal |
|---|---|---|
| JSON validity | Judge must emit `{score: 0-1, rationale}`; strict parse, 3 retries off | ≥95% valid on en/de/nl; report per-language drops; fo/is expected weakest |
| Spearman vs reference | Per language, ρ between runtime judge and Qwen3-8B (calibration) on the 30 items | ρ ≥ 0.5 per language; report all nine, no averaging that hides a language |
| Position bias | Each item judged twice with option order / pair order swapped (MT-Bench method) | ≤10% verdict flips; use the 2026 double-centering calibrator if worse |
| Language adherence | Rationales must be in the item's language (or explicitly English-by-config) | Leak rate reported per language; nynorsk must not collapse into Bokmål |
| Reference-vs-proprietary drift | Same 270 items to the proprietary reference judge once | Report ρ and disagreement list; treat as calibration, never as gold (OmniProv lesson: no IRR, no claim) |

Cost: 270 × ~4 calls ≈ 1.1k judge calls per judge per full run —
minutes on vLLM, well inside the online/curl budget; fo/is items need
native-speaker eyeballing before any claim (Nordic Linguist).

Scout is idle. Nothing committed; this file is unstaged.
