# Scouting brief — stronger claim extraction for Prong 3

Date: 2026-11-14 (Saturday, Europe/Oslo — NTNU rate window off). Scout
dispatch from the Captain. One NTNU job (this pass); no further NTNU
calls spawned. Read-only; only this brief written. No product code, no
commits.

## OmniProv is not enough — recap

1. `omniprov.txt` (full OpenReview dump) shows OmniProv was itself
   **rejected** (meta-review Av3z, 20 Aug 2026): gold labels mostly
   GPT-5.4 with partial expert checking, no IRR, no correction rates.
2. Its best source+relation accuracy is 0.478; verdict accuracy 0.665
   ("one in three verdicts wrong", Reviewer K7hh); 94.5% of test claims
   are single-tool (K7hh); the Docker was uninstallable (Reviewer 7ek4).
3. Its frame is MCP-agent **provenance against tool traces** — it
   verifies each claim against the exact tool output it should come
   from. D7.5 Prong 3 (`deliverable/protocol.tex`) is **open-domain
   generated text verified against an offline KB**. Different evidence
   source, different failure modes.
4. The inspiration brief (`docs/scouting/2026-11-14-inspiration.md`)
   already adapted its two transferable *mechanisms*: five-way relation
   labels (Idea 1) and documented atomic decomposition (Idea 4). The
   co-trained DeBERTa was correctly skipped (Idea 3).
5. What OmniProv does **not** give us: a decomposition pipeline that
   handles pronouns/context, a verifier that works under a 1.5B cap, a
   verifiable-claim filter, or a validated benchmark beyond its own
   LLM-labelled 254-claim set.
6. TODO.md already names the direction: "Prompt-based atomic-fact
   decomposition (à la SAFE / FActScore)" for
   `src/extraction/llm_claim_extractor.py`.
7. This brief grounds that line in the published literature, per the
   Captain's dispatch: ACL Anthology first, then NeurIPS/ICML/ICLR.
8. The dominant paradigm since FActScore (2023) is **decompose-then-
   verify**: split text into atomic claims, retrieve/consult evidence,
   judge support per claim. Our spaCy triples are a degenerate extractor
   in that paradigm; the literature shows exactly which stages lift
   coverage and verdict quality.
9. Known spaCy failure modes (TODO.md lines 31–34): no coreference,
   implicit/multi-sentence claims missed, English-only, syntactic
   triples miss paraphrase. The 2024–2025 literature attacks the first
   three directly (disambiguation, decontextualization, staged prompts).
10. Two 2025 papers show decomposition quality itself is a measured
    variable (DecompScore, verifier-preferred atomicity) — useful for
    our dual-output spaCy-vs-LLM comparison.
11. Verification under a small-model cap is solved in published work:
    AlignScore (RoBERTa ≤355M) and MiniCheck-FT5 (Flan-T5-large 770M)
    both run locally and have released models/benchmarks.
12. Filter note: search-API-dependent systems (SAFE, FacTool, FaStFact
    retrieval legs, VeriScore's Serper leg) are adapted for their
    **prompting stages only**; the search legs are skipped per filter 5.
13. D7.5 constraint found while grounding: `protocol.tex` Prong 3 says
    "Claimify is only considered for benchmarking and calibration
    during development" — see Idea 2 for how this is handled.
14. Eight ideas below, all ≤1.5B at runtime, none adds a prong; the two
    eval-only ideas cost CPU and no runtime model change.
15. Closing table ranks by expected coverage/AUC lift under the 0.5B cap.

---

## Idea 1 — Atomic-fact decomposition prompt (FActScore) · **adapt**

- **Source:** Min et al., *FActScore: Fine-grained Atomic Evaluation of
  Factual Precision in Long Form Text Generation*, EMNLP 2023,
  https://aclanthology.org/2023.emnlp-main.741/ (arXiv 2305.14251).
  Few-shot prompt turns a generation into short self-contained atomic
  facts; code `pip install factscore`.
- **Surface:** extractor (`llm_claim_extractor.py`).
- **Verdict vs current + OmniProv:** the direct grounding of TODO.md's
  "à la SAFE / FActScore" line. Atomic facts are prose statements, so
  they keep context that spaCy triples destroy ("He won in 2020" →
  fact names the referent). OmniProv gave us decomposition-as-mechanism;
  FActScore gives the published prompt format and the decontextualized
  fact convention.
- **Implement:** `src/extraction/llm_claim_extractor.py` maps atomic
  facts onto the existing `Claim` dataclass (subject/predicate/object
  parsed by a cheap second pass or kept as `predicate='atomic_fact'`,
  object=the fact — Protocol Steward should bless the mapping). Same
  `ExtractionResult` timing fields.
- **Cost:** tiny vLLM (0.5B, `[CLAIMS]` prefix). Few-shot prompt ≈ 300
  tokens; seconds for a paragraph.
- **Closes:** wXze coverage <10% (recall, not precision, is the
  bottleneck); the spaCy "paraphrased/embedded facts" TODO gap.

## Idea 2 — Staged extraction: selection → disambiguation → decomposition (Claimify) · **adapt, flag for Captain**

- **Source:** Metropolitansky & Larson, *Towards Effective Extraction
  and Evaluation of Factual Claims* (Claimify), ACL 2025 long,
  https://aclanthology.org/2025.acl-long.348/ (arXiv 2502.10855).
  Blog: https://www.microsoft.com/en-us/research/blog/claimify-extracting-high-quality-claims-from-language-model-outputs/.
  D7.5 itself cites it (`protocol.tex`,
  `metropolitansky2025effectiveextractionevaluationfactual`).
  Supported by Wanner et al., *DnDScore*, EMNLP 2025,
  https://aclanthology.org/2025.emnlp-main.1205/ (decontextualization
  and decomposition interact; both affect verification scores).
- **Surface:** extractor + coverage accounting.
- **Verdict vs current + OmniProv:** Claimify's three stages attack our
  exact failure modes: **selection** drops opinion/speculation sentences
  (spaCy triples them anyway); **disambiguation** resolves pronouns or
  refuses ("Cannot be disambiguated" — maps 1:1 to our
  `scored|unknown|error` status flag, Phase 1 item 2); **decomposition**
  emits bracket-annotated standalone claims. OmniProv decomposes but
  never explains how; Claimify is the documented, evaluated version.
  **Flag:** D7.5 `protocol.tex` explicitly reserves Claimify for
  "benchmarking and calibration during development". Running the
  *staged-prompt mechanism* on our own 0.5B is arguably a different
  realisation (Claimify the system used GPT-4o), but runtime use of a
  named calibration-only method needs an explicit Captain+user decision
  per working rule 3.
- **Implement:** same file as Idea 1; stages as sequential prompt calls
  with the local context window (preceding sentence + prompt) — no
  retrieval. Claim gains an `ambiguity_skipped` flag for the UI.
- **Cost:** tiny vLLM; 2–3 prompt calls per paragraph, still seconds.
  English-first; staged prompts are language-portable but untested.
- **Closes:** wXze coverage <10% and V55p's "no discriminative signal"
  (bad extractions propagate into false verdicts); gives the claims
  table honest `unknown` rows.

## Idea 3 — Claim-Split + partially-supported labels (WiCE) · **adapt**

- **Source:** Kamoi et al., *WiCE: Real-World Entailment for Claims in
  Wikipedia*, EMNLP 2023, https://aclanthology.org/2023.emnlp-main.470/
  (arXiv 2303.01432). Claim-Split: few-shot GPT-3.5 decomposition of a
  claim into ~3 subclaims, human-verified 92.3% complete / 97.7%
  correct; labels supported / partially_supported / not_supported;
  dataset + prompts on GitHub (`ryokamoi/wice`).
- **Surface:** extractor + verifier labels.
- **Verdict vs current + OmniProv:** a second, independently published
  decomposition prompt we can run few-shot on the 0.5B (Claim-Split
  worked with a much weaker 2022-era model than GPT-4o). Its
  `partially_supported` grade is the same insight as OmniProv's
  five-way relation (our Idea 1 there) but with a *dataset behind it* —
  WiCE subclaims give us labelled examples to few-shot and to sanity-
  check our verdicts against, which OmniProv's LLM-labelled set cannot.
- **Implement:** verdict-label mapping in
  `src/dimensions/prong3_dimensions.py`; Claim-Split prompt as an
  alternative `[CLAIMS]` template; WiCE dev subset copied under
  `data/` for a small extractor/verifier eval.
- **Cost:** tiny vLLM (prompts); CPU for the WiCE data. English-only.
- **Closes:** wXze AUC≈chance (better granularity of verdicts);
  strengthens OmniProv Idea 1 with real labels instead of a schema.

## Idea 4 — Verifiable-claim filtering (VeriScore) · **adapt**

- **Source:** Song, Kim & Iyyer, *VeriScore: Evaluating the factuality
  of verifiable claims in long-form text generation*, Findings of EMNLP
  2024, https://aclanthology.org/2024.findings-emnlp.552/ (code:
  `Yixiao-Song/VeriScore`; follow-up VeriFastScore, EMNLP 2025 Findings,
  https://aclanthology.org/2025.findings-emnlp.491/).
- **Surface:** extractor (pre-filter) + coverage meter + aggregator.
- **Verdict vs current + OmniProv:** FActScore/SAFE-style pipelines
  (and our spaCy triples) treat every extracted unit as verifiable, so
  opinions/hypotheticals become guaranteed misses that drag coverage
  and AUC. VeriScore extracts *only* verifiable claims using a
  sliding-window prompt with surrounding context (no separate revision
  step). Neither OmniProv nor our current pipeline has this filter;
  for an online dashboard it is the difference between "coverage 10%"
  and "coverage 10% of verifiable claims" — the honest denominator
  V55p asked about.
- **Implement:** filter stage in `llm_claim_extractor.py` (one extra
  `[CLAIMS]` call or a combined prompt); `Claim` gains
  `verifiable: bool`; aggregator counts coverage over verifiable
  claims only, and unverifiable ones show as `unknown`/excluded, never
  as failures.
- **Cost:** tiny vLLM (prompt-only adaptation; their fine-tuned Mistral
  extractor is 7B-class and stays "calibration only").
- **Closes:** V55p (neutral fallback / discriminative signal — removes
  structurally-unverifiable noise from the scored set); wXze coverage.

## Idea 5 — Local NLI verifier: AlignScore · **adapt**

- **Source:** Zha et al., *AlignScore: Evaluating Factual Consistency
  with A Unified Alignment Function*, ACL 2023,
  https://aclanthology.org/2023.acl-long.634/ (DOI
  10.18653/v1/2023.acl-long.634; code `yuh-zha/AlignScore`).
  RoBERTa-base 125M / 355M alignment function trained on 4.7M examples
  from 15 datasets; released checkpoints.
- **Surface:** verifier (the scoring half of Prong 3).
- **Verdict vs current + OmniProv:** our verifier is seed-Wikidata
  triple matching over ~86 entities; even on covered claims it is at
  chance. D7.5 Prong 3 explicitly says extraction "and subsequently
  evaluate them with Natural Language Inference" — an NLI-style
  verifier is in-protocol. AlignScore scores a claim against any
  context, so it can score a claim against the *sentence-formatted
  Wikidata fact* (or its own source sentence for internal-consistency
  checks) without entity lookup. Runs on CPU, far under the cap, and
  never hallucinates a verdict.
- **Implement:** new `src/prongs/prong3_verifier_alignscore.py`;
  verification becomes: KB hit → triple match (current) else →
  AlignScore(claim, formatted fact) if the entity resolves; report
  both tracks (dual output).
- **Cost:** CPU-only inference (125M base model), seconds per claim
  batch.
- **Closes:** wXze + V55p (discriminative signal on covered claims);
  partially mitigates the 86-entity seed (soft-match instead of exact
  triple match).

## Idea 6 — Small specialised fact-checker: MiniCheck-FT5 + LLM-AggreFact · **adapt**

- **Source:** Tang, Laban & Durrett, *MiniCheck: Efficient Fact-Checking
  of LLMs on Grounding Documents*, EMNLP 2024,
  https://aclanthology.org/2024.emnlp-main.499/ (code
  `Liyan06/MiniCheck`; models on HF; benchmark `lytang/LLM-AggreFact`).
  MiniCheck-FT5 = Flan-T5-large 770M, GPT-4-level grounding accuracy at
  ~400× lower cost; no explicit decomposition needed at inference;
  vLLM prefix caching supported. Bespoke-MiniCheck-7B exists —
  **calibration only** (above cap).
- **Surface:** verifier + external validation harness.
- **Verdict vs current + OmniProv:** same niche as Idea 5, stronger and
  newer (trained on LLM-claim-style errors via C2D/D2C synthesis —
  closer to our input distribution than generic NLI). Choose ONE of
  Ideas 5/6 for the PoC (I lean MiniCheck-FT5 if the 770M fits our
  Malvik memory envelope alongside the 0.5B judge; AlignScore-125M if
  we want pure CPU). Either way, LLM-AggreFact unifies ~11 labelled
  sentence-level datasets — an off-the-shelf validation set for Prong 3
  that is not FEVER.
- **Implement:** same slot as Idea 5 (feature-flag the backend);
  `scripts/` eval harness scores our extractor+verifier on a slice of
  LLM-AggreFact.
- **Cost:** tiny vLLM or CPU (770M); benchmark run is offline CPU.
- **Closes:** wXze ("entire empirical content is one near-chance FEVER
  benchmark") — a second, published, human-labelled evaluation.

## Idea 7 — AVeriTeC 2025 discipline as our second benchmark · **adapt (eval-only)**

- **Source:** Schlichtkrull et al., *The AVeriTeC Shared Task*, FEVER
  2024, https://aclanthology.org/2024.fever-1.1/; Akhtar et al., *The
  2nd AVeriTeC Shared Task: Open-weights, Reproducible and Efficient
  Systems*, https://aclanthology.org/2025.fever-1.15/. Data:
  fever.ai/dataset/averitec.html.
- **Surface:** evaluation harness + reporting (no runtime change).
- **Verdict vs current + OmniProv:** AVeriTeC 2025's rules read like
  our charter: open-weights only, single 23GB GPU, ≤1 minute per claim,
  pre-retrieved knowledge store instead of live search. That is the
  published proof that KB-store verification is feasible online without
  SaaS judges — exactly the defence of our design. Its claim set
  (real-world ClaimReview claims + the NEI/Conflicting labels) is a
  *harder, more realistic* second benchmark than FEVER 2.0 fixers.
- **Implement:** `scripts/eval_averitec.py` — score spaCy-extract +
  Idea 5/6 verifier on an AVeriTeC dev slice via the provided knowledge
  store; report AVeriTeC-style label accuracy alongside FEVER coverage/
  AUC. Calibration only; nothing runtime.
- **Cost:** CPU, offline; knowledge-store download is a one-off.
- **Closes:** wXze (single-benchmark empirical content) and V55p (three
  prongs unvalidated — Prong 3 gets a second instrument).

## Idea 8 — Measure decomposition quality: DecompScore + verifier-preferred atomicity · **adapt (eval-only)**

- **Sources:** Wanner et al., *A Closer Look at Claim Decomposition*,
  \*SEM 2024, https://aclanthology.org/2024.starsem-1.13/ (DecompScore;
  FActScore is sensitive to the decomposition method); Lu et al.,
  *Optimizing Decomposition for Optimal Claim Verification*, ACL 2025,
  https://aclanthology.org/2025.acl-long.254/ (decomposition policy
  should match the downstream verifier; "atomicity" as information
  density; RL-tuned policy is out of PoC scope).
- **Surface:** extractor evaluation + claims-table honesty.
- **Verdict vs current + OmniProv:** our Phase 3 plan compares spaCy vs
  LLM extraction by downstream coverage/AUC only. These papers show
  that conflates extractor error with verifier error. DecompScore lets
  us report *decomposition quality per se* for both extractors, and the
  atomicity lesson says our 0.5B prompt should aim at
  Wikidata-verifiable granularity (subject–property–value sized
  claims), not maximal atomisation — a concrete prompt-design rule.
  Also pre-empts the OmniProv reviewer complaint that the atomic
  decomposition was "only briefly explained": we would have a measured,
  reported decomposition step.
- **Implement:** extend `scripts/eval_averitec.py`/FEVER harness with a
  DecompScore-style table (entailed / covered / decontextualised per
  extractor); document the granularity rule in the extractor prompt.
  RL-based dynamic decomposition: **skip** (training, non-goal).
- **Cost:** CPU, offline.
- **Closes:** wXze (comparative justification of the specific choice —
  we can show *why* our extraction granularity is what it is); Phase 3
  exit criterion "LLM extractor comparable to spaCy" becomes measurable.

---

## Skipped, with reasons

- **SAFE** (Wei et al., NeurIPS 2024,
  https://openreview.net/forum?id=4M9f8VMt2C): search-leg needs Google
  Search; its self-contained-fact revision step is covered by Ideas
  1–2. Adapted conceptually, skipped as a system.
- **FacTool** (Chern et al., arXiv 2307.13528; cf. FactSearch, ACL 2026
  demo, https://aclanthology.org/2026.acl-demo.36/): tool-augmented
  pipeline around strong LLMs + search APIs; SaaS deps; too heavy.
- **FaStFact** (Wan et al., Findings of EMNLP 2025,
  https://aclanthology.org/2025.findings-emnlp.1295/): strong efficiency
  ideas (chunk-level extraction, confidence pre-verification skipping
  retrieval), but its pre-verification leg scores claims from the
  judge's internal knowledge, which blurs the Prong 3/Prong 1 boundary
  and biases coverage; revisit only if KB latency becomes the problem.
- **Factcheck-GPT / OpenFactCheck** (Findings EMNLP 2024,
  https://aclanthology.org/2024.findings-emnlp.830/; EMNLP 2024 demo,
  https://aclanthology.org/2024.emnlp-demo.23/): full frameworks, not
  components; useful as related-work cover, wrong granularity to import.
- **FactReasoner** (Findings EMNLP 2025,
  https://aclanthology.org/2025.findings-emnlp.785/): probabilistic
  evidence aggregation over retrieval; interesting for Phase 6, too
  much machinery for the PoC.
- **FEVEROUS** (Aly et al., 2021, https://aclanthology.org/2021.fever-1.1/):
  structured+unstructured evidence implies a much larger KB; adjacent
  to the 200k-dump non-goal.
- **Dynamic decomposition (RL)** inside Idea 8's ACL 2025 source:
  training loop, PoC non-goal.
- **Multilingual:** Sheikhi et al., NoDaLiDa 2023,
  https://aclanthology.org/2023.nodalida-1.1/ — NorBERT2/NB-BERT claim
  discard/uphold for Norwegian fact-checkers shows the Nordic path is
  real but model-based (fine-tuned, and Norwegian-only). Flag for the
  Nordic Linguist + a later phase; nothing runtime in this PoC. LREC
  and EAMT sweeps found no extraction method we would import (LREC
  2026 has a Japanese claim-decomposition dataset,
  https://aclanthology.org/2026.lrec-1.186/ — resource, not method;
  EAMT's factuality work is MT-error taxonomies).

## Closing table — ranked by expected coverage/AUC lift under the 0.5B cap

| Rank | Idea | Prong 3 surface | Verdict | PoC-sized? | Main weakness closed |
|---|---|---|---|---|---|
| 1 | Claimify-style staged extraction (select→disambiguate→decompose) | extractor + coverage | adapt (Captain flag: D7.5 names Claimify calibration-only) | Yes — 0.5B, 2–3 calls/¶ | coverage <10% (wXze), bad-extraction noise (V55p) |
| 2 | WiCE Claim-Split + partial-support labels | extractor + verdict labels | adapt | Yes — 0.5B few-shot + dataset | AUC≈chance (wXze) |
| 3 | FActScore atomic-fact prompt | extractor | adapt | Yes — 0.5B, 1 call/¶ | coverage; TODO.md seed grounded |
| 4 | VeriScore verifiable-claim filter | extractor + coverage meter + aggregator | adapt | Yes — 0.5B prompt | neutral fallback / honest coverage (V55p) |
| 5 | MiniCheck-FT5 verifier (770M) + LLM-AggreFact eval | verifier + eval harness | adapt | Yes — small vLLM/CPU | no signal on covered claims (wXze, V55p); single-benchmark paper (wXze) |
| 6 | AlignScore verifier (125–355M RoBERTa) | verifier | adapt (alternate to #5) | Yes — CPU | same as #5 |
| 7 | AVeriTeC 2025 benchmark via knowledge store | eval harness only | adapt | Yes — offline CPU | single-benchmark paper (wXze) |
| 8 | DecompScore + atomicity-granularity rule | extractor evaluation | adapt | Yes — offline CPU | comparative justification (wXze) |

Runtime footprint if #1–#5 all land: one 0.5B vLLM (existing, shared)
+ one 770M (or 125M) verifier model. Still ≤1.5B per generative
component; total GPU memory is a Dashboard/Eval-Scientist sizing
question, not a cap violation. Eval-only items (#7, #8) change nothing
at runtime.

Scout is now idle. Nothing implemented, nothing committed.

---

## Captain addenda — 2026-11-14 (Anthology pages re-opened this turn)

The eight-idea table above stands. A second Anthology sweep found four
papers the first ranking under-weighted. Pages opened this turn before
citing: Claimify [2025.acl-long.348](https://aclanthology.org/2025.acl-long.348/),
FActScore [2023.emnlp-main.741](https://aclanthology.org/2023.emnlp-main.741/),
MiniCheck [2024.emnlp-main.499](https://aclanthology.org/2024.emnlp-main.499/),
VeriScore [2024.findings-emnlp.552](https://aclanthology.org/2024.findings-emnlp.552/),
WiCE [2023.emnlp-main.470](https://aclanthology.org/2023.emnlp-main.470/),
DecompScore [2024.starsem-1.13](https://aclanthology.org/2024.starsem-1.13/),
Lu et al. [2025.acl-long.254](https://aclanthology.org/2025.acl-long.254/),
Core [2025.findings-acl.1018](https://aclanthology.org/2025.findings-acl.1018/),
Hu et al. [2025.naacl-long.320](https://aclanthology.org/2025.naacl-long.320/),
AlignScore [2023.acl-long.634](https://aclanthology.org/2023.acl-long.634/),
AVeriTeC 2025 [2025.fever-1.15](https://aclanthology.org/2025.fever-1.15/),
VeriFastScore [2025.findings-emnlp.491](https://aclanthology.org/2025.findings-emnlp.491/),
DnDScore [2025.emnlp-main.1205](https://aclanthology.org/2025.emnlp-main.1205/),
JEDI [2025.emnlp-main.1615](https://aclanthology.org/2025.emnlp-main.1615/),
MPropositionneur-V2 [2026.kallm-1.14](https://aclanthology.org/2026.kallm-1.14/).

### A — Atomic propositions as a front-end to spaCy (MPropositionneur-V2) · **adapt, displaces WiCE in the runtime stack**

- **Source:** Pommeret et al., *LLM-based Atomic Propositions Help Weak
  Extractors*, KG-LLM @ LREC 2026,
  https://aclanthology.org/2026.kallm-1.14/. Distills Qwen3-32B →
  Qwen3-0.6B; six European languages; atomic propositions raise
  relation recall for GLiREL / CoreNLP / 0.6B extractors. Stronger
  LLMs keep a fallback combination.
- **Why stronger than OmniProv Idea 4 and than WiCE as a first move:**
  Dankjewel already has a weak extractor (spaCy nsubj/dobj) and a
  planned dual spaCy+LLM output. This paper is the published proof
  that *propositions help the weak extractor rather than replacing it*.
  WiCE's Claim-Split is a second decomposition prompt; this is the
  architecture that keeps our existing triples.
- **Implement:** `llm_claim_extractor.py` emits decontextualized
  propositions; spaCy runs on those propositions as well as on the
  raw text; UI shows both tracks. Do not import their 0.6B weights
  unless Eval Scientist confirms they load under the cap (they do
  size-wise).
- **Cost:** tiny vLLM 0.5B, same slot as Idea 1. Multilingual cost
  is honest: their six languages are a Nordic-later win, English-first
  for the PoC.

### B — Core uniqueness/informativeness filter · **adapt**

- **Source:** Jiang et al., *Core: Robust Factual Precision with
  Informative Sub-Claim Identification*, Findings of ACL 2025,
  https://aclanthology.org/2025.findings-acl.1018/. FActScore-style
  metrics can be inflated by obvious or repetitive subclaims; Core
  is a plug-and-play filter on uniqueness and informativeness.
- **Why it belongs in the runtime stack:** a 0.5B decomposer will
  over-produce tautologies ("X is a person"). Those would pad
  coverage and flatten AUC — the exact wXze / V55p failure. Core
  is the published fix, cheaper than a second generative call if
  implemented as lexical/embedding uniqueness plus an
  "uninformative" heuristic.
- **Implement:** post-filter in `llm_claim_extractor.py` before
  the aggregator; dropped claims listed as `unknown` with reason
  `uninformative`, never as scored misses.

### C — Hu decomposition-error fixtures · **adapt (eval-only)**

- **Source:** Hu, Long & Wang, *Decomposition Dilemmas*, NAACL 2025,
  https://aclanthology.org/2025.naacl-long.320/. Decomposition can
  raise or *lower* fact-checking accuracy; they categorise the
  error types (over-split, missing context, fabricated atoms).
- **Implement:** turn their error categories into FEVER/AVeriTeC
  fixtures so spaCy-vs-LLM comparison reports *how* decomposition
  fails, not only coverage/AUC. Complements Idea 8 (DecompScore).

### D — JEDI encoder-only extractive decomposition · **skip for PoC, flag later**

- **Source:** Popovič & Färber, *Extractive Fact Decomposition for
  Interpretable NLI in one Forward Pass* (JEDI), EMNLP 2025,
  https://aclanthology.org/2025.emnlp-main.1615/. Encoder-only,
  no generative model at inference, one forward pass.
- **Skip now:** needs their trained encoder and synthetic-rationale
  corpus; a training loop is a PoC non-goal. Revisit if the 0.5B
  generative extractor is too slow online.

### Re-rank for slice 6 (when the user says go)

| Order | What | Verdict | Notes |
|---|---|---|---|
| 1 | Claimify stages on 0.5B (select → disambiguate → decompose); abstain → `unknown` | adapt (Captain+user flag: D7.5 names Claimify calibration-only; we run the *mechanism* on our 0.5B, not their GPT-4o system) | coverage + honest unknown |
| 2 | Dual output: propositions → spaCy triples (MPropositionneur pattern) | adapt | keeps current extractor |
| 3 | VeriScore verifiability gate | adapt | honest denominator |
| 4 | Core uniqueness filter | adapt | stops tautology padding |
| 5 | MiniCheck-FT5 770M vs formatted KB facts (AlignScore 125–355M as CPU fallback) | adapt, pick one | discriminative signal |
| 6 | WiCE partial-support labels | adapt (schema; already in OmniProv five-way) | verdict granularity |
| 7 | DecompScore + Hu error fixtures | adapt, eval-only | extractor vs verifier error |
| 8 | AVeriTeC 2025 knowledge-store slice | adapt, eval-only | second benchmark |

Still skipped as runtime: SAFE/FacTool search, VeriFastScore Llama-3.1-8B (over cap, Google Search), JEDI training, SegmentFact retrieval reuse, multimodal MICE, ClaimFlow (scientific claims, wrong domain).

Claimify citation in Idea 2 above is now the Anthology landing page, opened this turn.
