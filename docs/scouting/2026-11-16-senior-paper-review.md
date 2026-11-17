# Senior PC Review — Dankjewel Demo Paper (2026-11-16)

**Reviewer role:** Senior PC member, EMNLP-style demo track. Read-only; no edits to `new_demosubmission.tex`. **Sources read:** `new_demosubmission.tex` + `.bib` (670 lines, ACL preprint, 6a4f9916e0e62f75cd7f6e5d), `review.txt` (EMNLP 2026 reject: V55p 5/10, YE7H 6/10, wXze 3/10, AC reject), `docs/improvement-plan.md` (D7.5 v2, Phases 1–6), `docs/CLAIM_ADMISSION.md`, `docs/MULTILINGUAL_JUDGE.md`, `docs/LEXICON_VALIDATION.md`, `docs/EXTERNAL_EVALS.md`, `docs/scouting/2026-11-16-competitive-landscape.md`, `2026-11-14-inspiration.md`, `2026-11-14-claim-extraction.md`, `2026-11-16-whole-project-ideas.md`, `README.md` (latency/robustness/benchmark tables), `evaluation_results/` (latency_baseline, interactive_path_latency, robustness, scifact, verifier_eval, multilingual_judge, admission_ablation).

---

## 0. Verdict

**Weak Accept at the demo track (leans Accept; Accept after the two blockers are fixed).**

The revision turns a packaging paper into an honest instrument paper. The 2026-11-14 → 2026-11-16 delta closes every concrete YE7H/wXze/V55p complaint that could be closed without participants: latency is now measured on named CPU hardware (warm 672 ms baseline, 1,008 ms all-tracks, `/generate-and-evaluate` 974 ms warm; sequential throughput 93/min), robustness/failure modes are exercised, Prong 1 naming is reconciled (embeddings default, 0.5B judge as dual-output track), the honesty contract (`scored | unknown | error`, unknown never enters aggregates) is load-bearing in code, UI and paper, claim admission is a documented, ablated precision layer (76 → 8 on the teaching-prose export, 46 → 2 junk, all five intended lies survive), and the factuality story is reported as a lower bound with an identified bottleneck rather than hidden (FEVER coverage 0.3% / AUC 0.497 over 4/1,174 on the 122-entity seed; verifier component independently validated on SciFact dev AUC 0.835). The evidence-first interface (anatomy bar, coverage ribbon, claim strip, signal matrix, track dumbbells, iteration timeline with deltas) is the strongest demo contribution and is Selenium-verified.

What keeps this at Weak Accept rather than a clean Accept is: (a) the paper still has no tested research claim — wXze's core objection is answered with honesty rather than evidence, which is legitimate for a demo but leaves the paper one small human-rated ablation away from a durable contribution; and (b) two framing blockers remain fixable without new experiments (see §6). Fix those, and this is a demo-track Accept I would defend in discussion. Strong paper status requires the human-rated prong ablation (see §5, §7).

A reviewer who re-reads only the abstract will remember an evidence-first dashboard with admission gates and measured CPU latency. A reviewer who reads the limitations will remember a 0.3% factuality path and unvalidated lexicons — which is the right memory, and the revision earns it.

---

## 1. Research contribution — system description with an honest-measurement contribution, not yet a finding

**Is it a finding, or a system description?** Today it is a system description that contributes a measurement-and-honesty design: the honest-abstention semantics, the deterministic admission-gate taxonomy with an ablation, the five-way verification schema with a guarded entity lookup, the evidence-first interface that makes coverage and track agreement visible, and the measured latency/robustness artefacts on CPU hardware. None of V55p/wXze's requested findings has been run: the four-prong combination has never been tested against human usefulness ratings, and the aggregation presets remain explicitly unvalidated exploration aids.

**Strongest falsifiable claim the current evidence supports.** Narrow, but real:

> On the exported teaching-prose fixture (`dj_result_2026-11-15T19-56-34.json`, 4,740 chars of markdown, `docs/CLAIM_ADMISSION.md`), deterministic admission gates reduce extraction candidates from 76 to 8 (28 after markdown cleaning, 17 after sentence gates) with the hand-labelled non-claims falling from 46 to 2, while retaining all five intended false-claim examples that survive every stage.

This is reproducible (`evaluation_results/admission_ablation.json`, `scripts/eval_admission_ablation.py`), scoped to one fixture, and the paper frames it as a case study — correctly. It is not a general precision claim, and the paper does not pretend it is.

Two adjacent claims are supported at component level:

- The MiniCheck verifier ranks SciFact SUPPORT vs CONTRADICT pairs at AUC 0.835 (dev, n=338) / 0.790 (train, n=957) with mean latency ~258 ms (dev) — a verifier-component validation, not a KB-path validation, and the paper separates the two explicitly (§Evaluation/SciFact vs §Evaluation/FEVER).
- The multilingual judge agreement exists as an internal artefact (`evaluation_results/multilingual_judge.json`, 210 items × 7 languages) but the paper buries its headline: the shipped 0.5B judge fails Icelandic (ρ = 0.30) and the 1.5B passes all seven (lowest ρ = 0.874). That gap is a finding-quality result that the paper under-uses (see §2, §4).

**What experiment would create a research finding.** The one wXze named, scoped to a demo track:

> The four-prong combination predicts a small human "useful for revising this output" rating better than any single prong (or than a cheap baseline such as embeddings-only).

Design: 150 items (50 factual QA / 50 safety-sensitive / 50 fluency-form), two annotators, Krippendorff's α, Spearman per prong and combined, ablation deltas with bootstrap CIs, weight-sensitivity. The harness already exists (FEVER/SciFact/multilingual/robustness scripts plus the `evidence_sources`/`coverage`/`claim_details` contract); the cost is annotation, not engineering. Pre-register the hypothesis, metric and decision rule before running it. Either outcome is publishable if reported with CIs; a negative result ("combination does not beat best single prong on this task") is more valuable than no experiment. The whole-project ideas brief ranks this #1 for good reason — it is the single change that would move this paper from Weak Accept to a strong demo and from a system description to a paper with a finding. Effort: M (days of harness + weeks of recruitment). No new models needed; ≤ 1.7B cap respected.

---

## 2. Evidence — headline by headline

### The evidence-first view

**Claim:** Score anatomy, coverage ribbon, claim strip, signal matrix, track comparison and iteration timeline answer six questions without opening the JSON, and make the `scored | unknown | error` contract visible.

**Evidence:** Sufficient and well-framed. The interface is implemented (`frontend/index.html`), the contract is enforced in the pipeline and aggregator, and the stages A–F are Selenium-verified including at 390 px (`docs/commit-index.md`, `docs/EXTENSIBILITY.md`). The paper's §The Evidence View is the most memorable section and correctly claims novelty in the tooling niche (no competitor in the competitive-landscape sweep shows score anatomy or per-claim evidence at the signal-matrix granularity). The "what the interface refuses to claim" paragraph is the right move for a demo track.

**Flag:** None on substance. The interface legend duplication (`% duplicates the interface legend; consider shortening to one sentence.` at l. 359) is a writing fix — see §6.

**Under-used evidence:** The signal matrix already exports the inputs a human-validation study needs; the paper names that once in Limitations and should name it in §The Evidence View as the study-enabling export (one sentence, no new experiment).

### Claim admission (76 → 8)

**Claim:** Deterministic admission gates (markdown, heading, question, imperative, meta, pronoun, malformed, definition, demonstrative, duplicate) separate proposed candidates from admitted claims with a discard-reason histogram; on the teaching-prose fixture this cuts 76 raw candidates to 8 (9 after the use-mention pass) while retaining all five intended lies and dropping junk from 46 to 2.

**Evidence:** Sufficient for a case study, correctly scoped, and traceable. Artefacts: `evaluation_results/admission_ablation.json/.md`, `docs/CLAIM_ADMISSION.md` (41 tests, live-fixture histogram `{meta 15, definition 1, pronoun 6, demonstrative 2, question 7}`, limits and accepted leaks documented), `ASSUMPTIONS.md` §A5 (unquoted reported speech still needs the LLM track). The lookup guard that prevented `I`/`it` → Italy (Q38) and its verifier mirror are documented and tested — a concrete wXze closure.

**Over-claim risk:** The paper mostly avoids it, but the abstract's "discard markdown fragments, headings, meta-discourse, pronouns without a resolved referent, and encyclopedic definitions before anything is scored" can be read as a general precision claim. The paper's §Claim admission and Limitations correctly re-scope to one fixture; the abstract should carry a one-clause scope hedge ("on an exported teaching-prose run") — blocker B1.

**Under-used evidence:** Two high-value additions that need no new experiment: (a) name the two accepted leaks and the stage that would catch unquoted reported speech (one sentence, already in `docs/CLAIM_ADMISSION.md`); (b) add a one-line ablation footnote with the five stage counts (76 → 28 → 17 → 8 → 9) so a skimming reviewer sees the gate taxonomy is measured, not asserted.

### Judge agreement

**Claim:** 0.5B judge is adequate for English but fails Icelandic (ρ = 0.30); 1.5B passes all seven languages (mean ρ = 0.973, lowest 0.874); Qwen3-1.7B passes but trails 1.5B and is ~1.4× slower, so not adopted; 8B calibration reaches 0.996 (from improvement plan; the paper's Implementation §Prong 1).

**Evidence:** Sufficient internally, under-framed in the paper. The fixture (210 authored pointwise items, 7 UI languages × 30, Faroese omitted with disclosure) and results (`evaluation_results/multilingual_judge.json/.md`, `docs/MULTILINGUAL_JUDGE.md`) are real, rerunnable (`scripts/eval_multilingual_judge.py`, ~16 min), and already carry pass checks (JSON validity ≥ 0.95 per language, ρ ≥ 0.5 per language). This is the paper's strongest multilingual result and it is buried in one paragraph of §Prong 1.

**Over-claim risk:** None — the paper correctly says 0.5B fails Icelandic and recommends 1.5B for non-English, and the lexicon claim is correctly scoped to "unvalidated translations" (see §Prong 2, Limitations, and `docs/LEXICON_VALIDATION.md`).

**Under-used evidence:** Two moves that require no new experiment: (a) elevate the judge-agreement table to §Evaluation (even a three-row summary: 0.5B / 1.5B / 1.7B with mean ρ and lowest ρ), because a future reviewer will otherwise miss that this Prong is the only one with per-language measurement; (b) disclose the fixture's "easy authored pairs" caveat in the paper body, not only in the docs — `docs/MULTILINGUAL_JUDGE.md` already does, so this is a one-sentence import.

### Verifier benchmarks (SciFact + FEVER)

**Claim:** SciFact validates the verifier component (dev AUC 0.835, n=338); FEVER (1,174 claims from FEVER 1.0 dev, after FEVER 2.0 fixers became unretrievable) measures the KB path as a lower bound (coverage 0.3% = 4/1,174, binary AUC 0.497, conditional estimate unstable).

**Evidence:** SciFact — sufficient and correctly framed as component validation, not KB-path validation. Artefacts: `evaluation_results/scifact.json/.md` (dev 0.601 acc @0.5 / 0.835 AUC / 258 ms mean; train 0.555 / 0.790 / 232 ms), `scripts/eval_scifact.py` with provenance. The paper correctly notes the 0.8/0.2 bands are calibration-sensitive and conservative on scientific text.

FEVER — sufficient as a lower-bound report, insufficient as a factuality evaluation; the paper knows this and says so ("reported as a lower bound and not presented as operational fact-checking accuracy"). That honesty is load-bearing for a demo track. The substitution (FEVER 1.0 for 2.0, LLM-AggreFact blocked on one account click) is disclosed rather than silently reused, which answers wXze's reproducibility concern.

**Over-claim risk:** Low after the revision, but the paper carries two residual hazards:

- The "two benchmarks" framing (abstract, Contributions, Evaluation) can imply two validations of the same factuality path. The paper mostly separates "verifier component" from "KB path" — make that separation unmissable in the abstract (one clause: "SciFact validates the verifier; FEVER lower-bounds the seed-KB path").
- The `% consider dropping the repeated number and keeping only the calibration point.` comment at line ~448 hints at a numbers hygiene issue: the paper reports both AUC and accuracy and could be tightened to one ranking signal plus the calibration note. Not a blocker, but a should-fix for clarity.

**Under-used evidence:** The paper has a five-way schema (confirmed/denied/partially supported/conflated/unknown) with a justified fifth label (`Conflated` when the object is another entity's value of the same property) — a neat design choice that gets one paragraph and no illustration. One chip-strip example with a conflation would make the schema memorable.

### Latency

**Claim:** CPU-only, measured per track in fresh processes (1 cold + 5 warm): baseline 9.2 s cold / 672 ms warm median (684 ms p95); +0.5B judge 770 ms; +1.5B claims 908 ms; all three 1,008 ms; verifier engaged 827 ms; `/generate-and-evaluate` (llama.cpp Qwen2.5-1.5B Q4_K_M, 32 tokens) cold 1,049 ms / warm 974 ms.

**Evidence:** Sufficient and a major improvement over the rejected version (which reported zero numbers). Artefacts: `evaluation_results/latency_baseline.json/.md`, `evaluation_results/interactive_path_latency.md`, `scripts/measure_latency.py` with hardware fingerprint (Xeon Gold 6132, 56 cores, 755 GB RAM, CUDA false, Python 3.12, PyTorch 2.15). Direct per-model medians (judge 76 ms, claims 211 ms, verifier 196 ms) explain why the optional tracks are usable interactively.

**Over-claim risk:** None if the hardware is kept in the table caption or first sentence of §Latency — which the paper does (Table caption + §Hardware and protocol). Do not compress to "real-time" without the number (the competitive brief's rule).

**Under-used evidence:** The cold cost is dominated by embedding/toxicity/spaCy loads (~9 s) that every track pays; MiniCheck adds 6.4 s only when engaged (verifier-engaged row: 11.1 s cold). The paper states this once; a one-sentence "cold cost is deploy-time, not per-request" signpost helps a reviewer who skims to the warm numbers.

### Robustness

**Claim:** Empty input (10/19 scored, rest unknown), ~21k-char input (dedupes to one claim), Dutch input, dead-port judge/claims servers (degrade to unknown with baseline kept plus error counts), plus test-suite coverage of verifier-load failure, malformed JSON, per-call timeouts; sequential throughput 93/min baseline (645 ms mean), 76/min all-tracks (787 ms mean).

**Evidence:** Sufficient for a demo. Artefacts: `evaluation_results/robustness.json/.md`, `scripts/eval_robustness.py` (2026-11-16). The honest-abstention semantics are exercised, not just asserted.

**Gap disclosed:** Concurrent throughput, long generations and hosted generators not measured — correctly listed in Limitations rather than hidden. No over-claim.

---

## 3. Novelty vs the tooling landscape

Reading the 2026-11-16 competitive sweep (15 players + academic pipelines) alongside the paper's §Related Work:

**What is genuinely new.** Three things, and the sweep confirms none of the 15 competitors has them together:

1. **Online, during-generation scoring at ~1 s warm** on CPU with no cloud judge in the loop. Every commercial platform's "online evals" run asynchronously on ingested traces; every OSS harness (DeepEval, Ragas, TruLens, Opik, promptfoo) is offline/batch/CI-oriented. The sweep's §3.1 is correct: this is the paper's sharpest differentiator and it is now measured.
2. **Evidence-first UI with honest unknown semantics.** Score anatomy (hatched unknown share), coverage ribbon, per-claim evidence strip with provenance chips, signal matrix, track-agreement dumbbells and iteration timeline with deltas — none of the 15 competitors exposes why a score is what it is at claim level; DeepEval's best case is a one-line judge reason, and Phoenix/Opik/Langfuse show scores on traces, not evidence grounded in a KB. The `scored | unknown | error` contract with unknown excluded from aggregates is rare enough to be a contribution (the inspiration brief's OmniProv/OpenTools convergence). This is demo-worthy novelty.
3. **A fully specified KB-verification path reported as a lower bound with per-claim evidence,** now including the admission-gate taxonomy and the five-way relation. Competitors either have no KB path or hide model dependence; academic pipelines (FActScore, VeriScore, Claimify, MiniCheck) are offline batch systems with no dashboard. The paper's honesty about 0.3% coverage is stronger than a higher number hidden behind an unreported denominator.

**What is not new, and the paper mostly does not pretend it is.** The individual metrics (MiniLM cosine, toxic-bert, Flesch family, VADER, lexicon cue counts, top-k perplexity/entropy) are assembled components — wXze's point stands and the paper now concedes it by calling the interface and the honesty layer the contributions, not the metrics. The four-prong protocol itself is TrustLLM D7.5, cited as such. The 86-line worked example (`docs/EXTENSIBILITY.md`, Lexical Diversity) is a real recipe but not yet a bake-off against Ragas/lm-eval-harness/HF Evaluate — the sweep flags this and the paper correctly does not claim to have run that comparison.

**What is still easy to misread as novelty.** Two claims to handle carefully:

- "Multilingual" — the paper now correctly says "interface ships with nine languages; lexicons are unvalidated translations" and recommends the 1.5B judge for non-English after the 0.5B fails Icelandic. That is honest. Do not upgrade to "multilingual evaluation validated" without native-speaker review (see §5, §7).
- "122-entity KB" — the paper labels it a seed and reports 0.3% coverage as a lower bound. Do not let the abstract's "offline Wikidata fact-checking" imply a Wikidata-scale deployment; the current abstract avoids this but could be tighter (blocker B1).

**Blunt summary.** The paper is not a new metric, not a new verifier, and not a trace-observability platform. It is a small, Apache-2.0, CPU-runnable, evidence-first instrument that maps a public protocol to an interface where every score carries its provenance and every missing signal is visible. That is a defensible demo-track contribution if the paper keeps claiming it and stops claiming the adjacent categories (§6.4 "What NOT to claim" in the competitive brief is good guidance).

---

## 4. Clarity and structure — what a demo reviewer will remember, what is buried

**A reviewer will remember:**

- The car-dashboard metaphor and the honesty contract — both land in the first two pages and are the right framing for a demo track.
- The evidence view (§The Evidence View, six sub-paragraphs) — the paper's best section and the clearest answer to the first 2026 critique ("showed scores without evidence").
- The 76 → 8 admission case study with the discard histogram — concrete, visual, and scoped to one fixture, which is why it sticks.
- The 0.3% FEVER number — because it is surprising and the paper reports it plainly. A reviewer will remember the honesty even if they forget the AUC.

**What is buried and should not be:**

- **The multilingual judge result.** The paper's strongest per-language measurement (0.5B ρ = 0.30 on is vs 1.5B lowest 0.874) is one paragraph in Implementation. A reviewer who skims to Evaluation will miss that any Prong has per-language evidence. Move a three-row summary to Evaluation or a dedicated Multilingual paragraph.
- **The verifier-component validation.** SciFact AUC 0.835 is the only evidence that any factuality component works; it sits after the FEVER lower bound, so a skimming reviewer reads 0.3% → 0.497 before 0.835. Order matters: component validation first, system lower bound second — or at least a forward pointer.
- **The interactive path measurement.** `/generate-and-evaluate` 974 ms warm with logprobs present is the paper's best answer to "real-time is unmeasured" and is one sentence at the end of the latency table's notes. Give it its own line in the table (it already has one) and a one-sentence call-out in the text.
- **The extensibility recipe.** 86 changed lines to add a dimension is a credible answer to wXze's "no worked example" and lives in one paragraph of Prong 2. A reviewer who cares about resource contributions will look for it in Related Work or a dedicated Extensibility paragraph — currently they have to find it.

**Structural notes:**

- The paper is long for a demo (8 pages + references); the six evidence-view sub-paragraphs plus the admission gate table plus two benchmark subsections will strain a 4-page demo limit. For EMNLP demo, the evidence view can stay and the Prong 1/2/4 implementation detail can compress — the demo is the interface, not the Flesch coefficients.
- The draft comments left in the tex (`% duplicates the interface legend; consider shortening to one sentence.` and `% consider dropping the repeated number and keeping only the calibration point.`) should be resolved before submission — they are reviewer-visible hesitation.
- The Limitations section is unusually good for a demo — it lists human validation, KB scale, small optional models, quoted claims, multilingual coverage, robustness/throughput and benchmark availability, each with a pointer to docs or a next step. Keep it; it is the reason a senior reviewer trusts the rest.

---

## 5. What would make it acceptable, and what would make it strong

### Acceptable at an EMNLP-style demo track (no new experiments required)

The paper is already close. Two framing fixes are load-bearing; the rest is should-fix polish (§6).

**Acceptable means:** A reviewer can describe the system accurately from the paper, reproduce the headline numbers from the artefacts, and not be misled about what is validated. The current draft meets this except for blocker B1 (abstract scope) and blocker B2 (paper-trail traceability for the numbers a reviewer will cite). Fix those and I would accept this as a demo.

**What would make it strong (not just a demo)** is one tested claim plus one unblocked benchmark:

1. **Prong ablation with CIs on a small human-rated set** (see §1, §7 E-rank 1). This is the only change that answers wXze's "no research finding" at the level of a finding. Without it the paper remains a system description with honest lower bounds — acceptable for a demo, forgettable as a research contribution. With it the paper has a sentence of the form "on a 150-item human-rated set (2 annotators, α = X), the four-prong combination correlates ρ = Y with usefulness, Z points above the best single prong (CI [...])" — or the honest negative, which is still a finding.
2. **LLM-AggreFact row** (one account click + `scripts/eval_aggrefact.py`; §7 E-rank 2). The paper currently has one KB-path benchmark (FEVER) that is a lower bound and one component benchmark (SciFact) that validates the verifier. AggreFact is the second KB-path benchmark the paper already promises and the harness is ready.
3. **Faroese inclusion + 1.5B non-English routing measurement** (see §2 Judge agreement, §7 M-rank 1–2). Turns the multilingual story from "0.5B fails is, 1.5B would pass" into "non-English routed to 1.5B, lowest ρ = 0.874, 210 → 240 items".

All three respect the ≤ 1.7B cap and CPU-first constraints.

---

## 6. Ranked revision list — executable without new experiments

Severity: **Blocker** = a reviewer can justifiably reject or misquote the paper without it. **Should-fix** = a real improvement a writer can do in an editing pass. **Note** = polish.

### Blockers (fix before resubmission)

**B1. Scope the abstract's two most quotable claims.** The abstract currently says "the extraction-based prong had no precision layer" (past) and "claim extraction now runs through deterministic admission gates that discard ..." (present) without a scope hedge, and "we report measured latency on CPU hardware, a case study in which claim admission reduces 76 candidates to 8 claims ... and two benchmarks: SciFact ... and a 1,174-claim FEVER evaluation" without naming that FEVER is a lower bound on a 122-entity seed. Add two clauses to the abstract: (a) "on an exported teaching-prose run" for 76 → 8, and (b) "SciFact validates the verifier component (AUC 0.835 dev); FEVER lower-bounds the seed-KB path (0.3% coverage)" — the paper already does this in §Evaluation, so this is a one-sentence import, not a rewrite.

**B2. Make every table number traceable to an artefact.** The paper's latency, robustness, SciFact and admission numbers are all reproducible, but the paper cites them without artefact paths. Add a one-line "Artefacts" footnote or end-of-§Evaluation paragraph listing the four `evaluation_results/*.json` files and the hardware line, and cite them in each table caption (e.g. "Source: `evaluation_results/latency_baseline.json` (2026-11-16, Xeon Gold 6132, CUDA false)"). The improvement plan's Phase 4 exit criterion was "README has real numbers" — the paper should have the same traceability, because wXze praised the FEVER script's candour and this is how you keep that trust.

### Should-fix (editing pass, no new data collection)

**S1. Elevate the multilingual judge result from Implementation to Evaluation.** Add a 3–4 row summary (0.5B / 1.5B / 1.7B / 8B with mean ρ, lowest ρ, slowest language) to §Evaluation, with a one-sentence caveat ("210 authored pointwise items; easy pairs; language adherence not automatically assessed; disclosure in `docs/MULTILINGUAL_JUDGE.md`"). This is a copy-paste from `docs/MULTILINGUAL_JUDGE.md` and `evaluation_results/multilingual_judge.md` — no new run needed.

**S2. Make the verifier-vs-KB-path separation unmissable in the abstract and Contributions.** The paper does this correctly in §Evaluation ("This validates the verifier component; it does not validate the seed-KB path") — lift that sentence to the abstract and to the Contributions bullet that currently says "Measured latency ... and two benchmarks that separate the verifier component from the knowledge-base path" (good) but could be crisper: "SciFact (AUC 0.835 dev) for the verifier; FEVER (0.3% coverage) as a lower bound for the seed-KB path."

**S3. Resolve the two draft comments in the tex.** L. ~359 `% duplicates the interface legend; consider shortening to one sentence.` — shorten. L. ~448 `% consider dropping the repeated number and keeping only the calibration point.` — keep the ranking signal (AUC) and the calibration note, drop the redundant accuracy restatement if the table already carries it.

**S4. Give `/generate-and-evaluate` a call-out sentence.** The latency table already has the row (cold 1,049 ms, warm 974 ms, p95 980 ms, llama.cpp Qwen2.5-1.5B Q4_K_M, 32 tokens, all four Prong 4 dimensions scored). Add one sentence in the text: "The interactive path including generation is 974 ms warm median on the same CPU host" — so a reviewer who skims to "real-time" finds the number.

**S5. Name the admission limits in one sentence.** The paper lists the two accepted leaks in `docs/CLAIM_ADMISSION.md` ("smoking is that bad" fragment, "Critical thinking is your best defense ..." advice) and the unquoted-reported-speech gap (ASSUMPTIONS.md §A5). Import one sentence to §Claim admission: "Two non-claims survive all gates; unquoted mid-sentence reported speech still needs the 1.5B track."

**S6. Add a reproducibility appendix or footnote.** List every `scripts/eval_*.py` invocation, expected artefact, and verification command so a reviewer can re-measure the paper's tables. `docs/CLAIM_ADMISSION.md` §Verification, `docs/MULTILINGUAL_JUDGE.md` §How to rerun and `docs/EXTERNAL_EVALS.md` already contain the recipe — this is assembly, not authoring. Addresses YE7H's reproducibility concern.

**S7. Tighten Related Work citations.** Add access dates to the tool URLs footnote and keep the competitive brief's "What NOT to claim" discipline: cite Phoenix ELv2, Langfuse MIT-core, etc. with licences as of 2026-11-16, and mark any marketing-page-only claims as such in internal notes (already done in the sweep). This is a citation pass, not a research task.

**S8. Compress Prong 2 implementation detail.** Flesch coefficients, lexicon file counts and Faroese/Icelandic proxy backends are important for honesty but take space a demo track needs for the evidence view. Compress to two sentences plus a pointer to `docs/LEXICON_VALIDATION.md`; the audit result ("key parity, no empty/duplicate lists, only `lol`/`hey` shared verbatim") is one sentence.

### Notes (polish, if space allows)

**N1.** Keep the Limitations section — it is the paper's trust anchor. Consider adding one sentence on the weight-preset limitation ("presets have not been correlated with human judgments; a deployment should derive weights from failure costs") — already in §Aggregation and Limitations, so this is a cross-reference.

**N2.** The five-way relation's `Conflated` label deserves one illustrative chip-strip example (e.g. a capital that belongs to another country's property) — memorable and costs one sentence.

**N3.** The paper's `% Ablation numbers: evaluation_results/admission_ablation.{json,md} (scripts/eval_admission_ablation.py), measured 2026-11-16.` comment is useful provenance — promote from comment to caption footnote.

**N4.** Check demo-track page limits early — the current draft is ~8 pages. The evidence view and admission case study should survive compression; the Prong 1/2/4 metric detail can shrink.

---

## 7. Revisions that need new experiments (with effort)

All respect the ≤ 1.7B cap and CPU-first constraints. Ordered by reviewer impact.

| Rank | Revision | What to do | Effort | Why it matters |
|------|----------|------------|--------|----------------|
| 1 | **Prong ablation with CIs on a human-rated set** | 150 items (50/50/50 factual QA / safety / fluency), two annotators, Krippendorff's α, Spearman per prong and combined, ablation deltas with bootstrap CIs, weight-sensitivity. Pre-register hypothesis/metric/decision rule. Harness reuses existing `evidence_sources`/`coverage` contract. | **M** — days of harness + 1–2 weeks recruitment/annotation | The only path to a tested research claim; closes wXze/V55p core; turns presets into measured guidance. |
| 2 | **LLM-AggreFact unblock** | One account click at `huggingface.co/datasets/lytang/LLM-AggreFact`, then `scripts/eval_aggrefact.py --split dev`; add AggreFact row to README/EXTERNAL_EVALS/paper. | **S** — hours after the click | Second KB-path benchmark the paper promises; harness ready; `docs/EXTERNAL_EVALS.md` already documents it. |
| 3 | **1.5B non-English judge routing + Faroese fixture** | Keep 0.5B default for English, route is/nn/fo/da/de/nl/sv to 1.5B via `lang→judge` config; label which judge ran in `metadata`. Add 30 Faroese items (210 → 240). Rerun `scripts/eval_multilingual_judge.py`. | **S** — env/config + 30 items + one rerun | Closes the documented Icelandic failure with no new model; uses the already-running claims server; paper's multilingual story becomes measured. |
| 4 | **English-pivot for is/fo claim verification** | `[PIVOT]` task on the 1.5B claims model translates is/fo claims to English, verifies against English KB, projects verdicts back; report pivot vs direct coverage on the multilingual fixture. Fidelity check via back-translation or human spot-check. | **M** — one extra LLM task + English-only verifier + evaluation harness | Biggest coverage lever for the two languages with no KB content; avoids building an is/fo Wikidata slice; publishable low-resource finding. |
| 5 | **Concurrent serving benchmark** | Extend `scripts/measure_latency.py` with N concurrent clients (2/4/8); report throughput vs latency under contention. | **S** — small harness addition | Reviewer-relevant: sequential throughput is measured but concurrent is "not measured" (Limitations) — closing this is cheap credibility. |
| 6 | **Distil 8B reference into 1.5B runtime judge** | Sample 1k multilingual items, collect 8B soft labels, LoRA/DPO on the 1.5B judge, held-out rho lift per language. | **L** — training slice + LoRA harness + sweep + held-out eval | Turns the 8B calibration model into a training signal under the cap; "small judge closes X% of the gap to 8B" claim. |
| 7 | **Staged extraction (select → disambiguate → decompose)** | Claimify-style three-stage prompt on the 1.5B claims track; abstain on pronouns/embedded details; report coverage and FEVER conditional AUC lift. | **M** — 2–3 calls per paragraph + abstention handling | Attacks the extraction-recall bottleneck more directly than self-training; the claim-extraction brief ranked this #1. |
| 8 | **AVeriTeC knowledge-store slice** | Download multi-GB store, index a 500-claim dev slice, score with existing `NliVerifier`, report label accuracy. | **L** — download + indexing + retrieval + mapping | Harder, more realistic third benchmark (NEI/Conflicting); dedicated slice, not a quick run. |
| 9 | **Native-speaker lexicon validation** | One speaker per non-English language reviews the 6-cue YAML; report agreement/precision per language (at least nn vs nb split). | **L** — recruitment | Upgrades lexicons from "unvalidated translations" to measured; wXze lexicon concern. |
| 10 | **User study — evidence panels change revision decisions** | Show users text + scores with vs without the evidence view; measure whether revision choices change (not just satisfaction). | **M–L** — participants + task design | YE7H user-study gap; should measure decision change, not usefulness ratings alone. |

---

## 8. Appendix — traceability for this review

| Paper claim | Artefact | Status |
|-------------|----------|--------|
| 76 → 8 admission (46 → 2 junk, five lies survive) | `evaluation_results/admission_ablation.json/.md`, `docs/CLAIM_ADMISSION.md`, `scripts/eval_admission_ablation.py` | Verified on teaching-prose export |
| Lookup guard (`I` → Italy fix, 3-char + word-boundary) | `docs/CLAIM_ADMISSION.md` §The lookup guard, commit `f49c1db` | Reproduced against `data/wikidata_seed.db` |
| SciFact verifier AUC 0.835 dev / 0.790 train | `evaluation_results/scifact.json/.md`, `scripts/eval_scifact.py` | Verified |
| FEVER 0.3% / AUC 0.497 (seed), conditional n/a | `README.md` Benchmarking, `evaluation_results/evaluation_results.json` | Re-measured 2026-11-14 on 122-entity seed |
| Latency warm 672 ms baseline / 1,008 ms all-tracks / 974 ms interactive | `evaluation_results/latency_baseline.json/.md`, `evaluation_results/interactive_path_latency.md`, `scripts/measure_latency.py` | Xeon Gold 6132, CUDA false, 2026-11-14/16 |
| Robustness + throughput 93/min / 76/min all-tracks | `evaluation_results/robustness.json/.md`, `scripts/eval_robustness.py` | 2026-11-16 |
| Multilingual judge 0.5B ρ 0.865 mean / 0.30 is fail; 1.5B 0.973 / 0.874 pass | `evaluation_results/multilingual_judge.json/.md`, `docs/MULTILINGUAL_JUDGE.md` | 210 items × 7 langs |
| Lexicon audit (key parity, `lol`/`hey` only) | `docs/LEXICON_VALIDATION.md` | Mechanical pass, native review pending |
| Extensibility 86-line recipe | `docs/EXTENSIBILITY.md` | Performed, measured |
| Blocked LLM-AggreFact | `docs/EXTERNAL_EVALS.md`, `scripts/eval_aggrefact.py` | Ready, one click from unblocked |

---

*Scout is idle. This file is unstaged, as briefed. No paper edits, no commits.*
