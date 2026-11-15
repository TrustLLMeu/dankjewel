# Dankjewel herdr — crew charter (draft for review)

Captain: this Grok session (`grok-4.6`). Subagents use **only** NTNU LLM API
(`https://llm.hpc.ntnu.no/v1`) or Malvik-local OpenAI-compatible servers.
No cloud-only third-party APIs (OpenAI, Anthropic, Gemini) for crew roles.

This file is the proposed setup. **Do not spawn the crew or implement
`docs/improvement-plan.md` until the user approves it.**

---

## Why a crew

The deliverable is TrustLLM D7.5 (`deliverable/`): an online, modular,
multilingual four-prong metric, first dated April 2025. `review.txt`
is the EMNLP 2026 System Demonstration rejection of an early
dashboard. Closing that gap is too wide for a single context window:
protocol fidelity, four prongs, UI, measurement, Nordic languages,
post-2025 methods, and a clean git history need parallel specialists.

The captain talks to the user, splits work, merges worktrees, and
refuses work that violates D7.5, this charter, or the small-eval-model
constraint.

---

## Roles

| Pane | Agent file | Model | Isolation | Writes code? |
|------|------------|-------|-----------|--------------|
| Captain | this session | `grok-4.6` | shared | glue only, after user gate |
| Scout | `scout.md` | `zai-org/GLM-5.3-Flash` | none (read-only) | scouting briefs only |
| Protocol Steward | `protocol-steward.md` | `openai/gpt-oss-120b` | none (read-only) | no |
| Implementer | `implementer.md` | `Inferact/GLM-5.3-NVFP4` | worktree | yes |
| Dashboard | `dashboard.md` | `mistralai/Mistral-Medium-3.5-128B` | worktree | frontend only |
| Eval Scientist | `eval-scientist.md` | `Qwen/Qwen3.8-27B-FP8` | worktree | eval scripts/tests |
| Reviewer | `reviewer.md` | `moonshotai/Kimi-K2.6` | none (read-only) | no |
| Nordic Linguist | `nordic-linguist.md` | `NorwAI/NorwAI-Magistral-24B-reasoning` | none (read-only) | lexicons only if asked |
| Git Historian | `git-historian.md` | `Qwen/Qwen3.8-27B-FP8` | none | commits + `docs/commit-index.md` |
| Docs Keeper | `docs-keeper.md` | `Qwen/Qwen3.8-27B` (Malvik) | worktree | docs only (`*.md`) |
| Paper Writer | `paper-writer.md` | `Qwen/Qwen3.8-27B` (Malvik) | worktree | `paper/` only |
| Paper Reviewer | `paper-reviewer.md` | `moonshotai/Kimi-K2.6` (NTNU) | none (read-only) | no |

Panes and tabs (workspace `w0`, short tab labels in brackets):
Captain t1 [Cap], Scout t3 [Scout], Protocol t4 [Proto], Implementer
t5 [Impl], Dashboard t6 [Dash], Eval t7 [Eval], Reviewer t8 [Rev],
Nordic t9 [Nord], Git tA [Git], Docs tB [Docs], Paper tC [Paper],
Paper review tD [PRev]. The shell tab t2 is labelled [sh].

New-role boundaries:

- **Docs Keeper** owns every user- and method-facing doc (`README.md`,
  `QUICKSTART.md`, `CONTRIBUTING.md`, `docs/*.md`, `DB_EXTENSION_GUIDE.md`,
  `ASSUMPTIONS.md`, `TODO.md`). It never edits code, tests, data, the
  commit index, `review.txt`, or `inspiration.txt`. Documentation of a
  method lands with the method's slice or immediately after.
- **Paper Writer** owns `paper/` and writes from repo artifacts only.
  Every number is traced to `evaluation_results/` or the commit index;
  gaps are written as "not measured". It never edits code or data.
- **Paper Reviewer** is read-only and adversarial: it checks every
  number against an artifact, tests the paper's answers against
  `review.txt`, and returns a verdict with ranked findings. It holds
  the single NTNU slot while it runs; Docs and Paper writers run on
  Malvik and serialise with the other Malvik Qwen panes.

Qwen host is **not** a free choice. See [NTNU rate window](#ntnu-rate-window).

Fallback if a host is down (still obey the one-job NTNU cap):

- NTNU GLM-5.3-NVFP4 down → Malvik `Qwen/Qwen3.8-27B` (`http://127.0.0.1:18091/v1`). Do not take a second NTNU model during the rate window.
- Qwen roles during the rate window: NTNU `Qwen/Qwen3.8-27B-FP8`; if that is down → Malvik `Qwen/Qwen3.8-27B`.
- Qwen roles outside the rate window: Malvik `Qwen/Qwen3.8-27B`; if that is down → NTNU `Qwen/Qwen3.8-27B-FP8`.
- Kimi-K2.6 down → `zai-org/GLM-5.3-Flash` (counts as the one NTNU job in the rate window).
- GLM-5.3-Flash down (Scout) → `moonshotai/Kimi-K2.6-instant`.
- Magistral down → `NbAiLab/borealis-27b`.

Cheap/fast twins (`*-instant`) are for smoke checks, not for architecture
or review verdicts.

`Cloudflare/clef-flash` (9B router) is **not** a standing pane. Captain
may use it later as a dispatcher if the crew grows; skip it for v2.

---

## Model rationale

- **`openai/gpt-oss-120b`** — NTNU analysis workhorse. Protocol mapping
  and “does this still satisfy D7.5?” checks.
- **`Inferact/GLM-5.3-NVFP4`** — strongest coding model on the NTNU menu.
- **`mistralai/Mistral-Medium-3.5-128B`** — multimodal; can look at
  dashboard screenshots. Matches the existing `design-expert` choice.
- **`Qwen/Qwen3.8-27B-FP8` (NTNU)** and **`Qwen/Qwen3.8-27B` (Malvik,
  `:18091`)** — Eval Scientist and Git Historian. NTNU Qwen during
  the weekday rate window; Malvik Qwen outside it. See
  [NTNU rate window](#ntnu-rate-window).
- **`moonshotai/Kimi-K2.6`** — long-context reasoning for adversarial
  review against `review.txt`.
- **`NorwAI/NorwAI-Magistral-24B-reasoning`** — NTNU’s own Norwegian
  model; lexicon and Germanic-language claims.
- **`zai-org/GLM-5.3-Flash`** — 1M context, fast. Scout reads long
  READMEs, papers, and other eval-system docs in one pass.
- **Git Historian** uses the same Qwen pair as Eval Scientist.
  Serialise those two panes with each other always. Instant twin
  (`Qwen/Qwen3.8-27B-FP8-instant`) is allowed for index-only updates
  and still counts as the one NTNU job in the rate window.

Captain stays on `grok-4.6` because this session already holds user
context. Switching the captain mid-herd would drop that. If the user
wants the captain on an NTNU model too, say so.

---

## NTNU rate window

Timezone: **Europe/Oslo**. Captain checks `TZ=Europe/Oslo date` before
every NTNU spawn. This rule is part of the crew workflow; the future
`.grok/workflows/d75-slice.rhai` must encode the same gate.

**Mon–Fri 08:00–18:00** — NTNU API is rate-limited.

- At most **one** NTNU job in flight. No parallel Scout + Implementer
  + Reviewer on NTNU. Captain queues panes and runs them one after
  another.
- `*-instant` twins, GLM-OCR, and clef-flash all count as that one job.
- Captain (grok-4.6) and Malvik-local servers do **not** count.
- Qwen panes (Eval Scientist, Git Historian): spawn
  **`Qwen/Qwen3.8-27B-FP8` on NTNU**. That spawn *is* the one job.
  If NTNU Qwen is down, use Malvik Qwen rather than a different NTNU
  model.

Observed 2026-11-14 (Saturday 09:12 CET): the gateway still returned
`max_parallel_requests: 1` (`throttling_error`). Until we see Remaining
> 0 on a weekend, **treat one NTNU job at a time as always-on**, even
outside Mon–Fri 08–18.

**Evenings (18:00–08:00), nights, weekends** — the *documented* one-job
cap is off; still serialise NTNU if the live error is
`max_parallel_requests`.

- Parallel NTNU fan-out is allowed when tasks do not share files
  (working rule 1).
- Qwen panes: spawn **`Qwen/Qwen3.8-27B` on Malvik**
  (`http://127.0.0.1:18091/v1`). If Malvik Qwen is down, NTNU
  `Qwen/Qwen3.8-27B-FP8` is the fallback.

HPC courtesy for *heavy batch* (evenings/weekends) still applies to
large offline jobs. Crew coding is interactive API use; the product
0.5B judge stays on Malvik always.

| Clock (Europe/Oslo) | NTNU API | Eval / Git Qwen |
|---------------------|----------|-----------------|
| Mon–Fri 08:00–18:00 | one job | NTNU `Qwen/Qwen3.8-27B-FP8` |
| otherwise | parallel OK | Malvik `Qwen/Qwen3.8-27B` |

---

## Working rules

1. Captain proposes a task, names the pane, and waits for that pane’s
   report. Parallel fan-out is allowed when tasks do not share files
   **and** the NTNU rate window is off. During Mon–Fri 08:00–18:00,
   NTNU panes run strictly one at a time (see
   [NTNU rate window](#ntnu-rate-window)).
2. Implementer and Dashboard **always** run in `isolation: worktree`.
   Captain inspects the worktree, Reviewer reads it, then Captain merges
   only after the user (or an explicit standing order) accepts.
3. Protocol Steward reviews every prong change against
   `deliverable/*.tex` before merge. A dimension that is not in D7.5
   needs an explicit user decision.
4. Reviewer scores work against `review.txt` (reviewer wXze first, then
   V55p and YE7H). A change that does not move a listed weakness is
   out of scope unless the user asked for it.
5. Eval Scientist owns latency numbers, dual-output tables, and the
   tiny-judge model list. No pane may introduce a judge larger than
   the cap in [Eval models](#eval-models-inside-the-product).
6. Nordic Linguist is consulted before any multilingual claim in
   README, abstract, or UI. Default public claim: *prototype language
   configuration, validated for English; eight further Germanic
   lexicons are unvalidated translations.*
7. Panes do not talk to the user. Captain does.
8. One implementer at a time on a given package (`src/prongs/`,
   `src/extraction/`, `frontend/`, `scripts/`).
9. Scout runs at the start of each phase and when Protocol Steward
   says D7.5 is silent. Ideas that need a new prong or a judge above
   the cap go to the Captain, not to the Implementer.
10. Git Historian is the only pane that runs `git commit` on
    `feature/d75-v2`. Implementer worktrees stay uncommitted until
    Captain asks the Historian to land a slice. No pane pushes to
    `origin/master`. The browsable log is `docs/commit-index.md`.

---

## Eval models (inside the product)

Crew models (above) write and review code. **They are not the judges
the Instant Evaluator calls at runtime.**

Runtime LLM-as-judge / claim-extraction models for the PoC:

| Role in product | Model | Size | Host |
|-----------------|-------|------|------|
| Embeddings (Prong 1 baseline) | `sentence-transformers/all-MiniLM-L6-v2` | ~22M | local CPU |
| Toxicity (Prong 1) | `unitary/toxic-bert` or DistilBERT-class | ~66–110M | local CPU |
| Generative judge (Prong 1 option) | `Qwen/Qwen2.5-0.5B-Instruct` | 0.5B | local vLLM on Malvik |
| Claim extraction (Prong 3 option) | `Qwen/Qwen2.5-0.5B-Instruct` (same instance) | 0.5B | local vLLM |
| Readability LLM (Prong 2 option, later) | same 0.5B instance, task prefix | 0.5B | local vLLM |

Hard cap for this PoC: **≤ 1.5B parameters** for any generative judge.
If 0.5B is unusable, step to `Qwen/Qwen2.5-1.5B-Instruct`. Do not step
to 7B+ until the user lifts the cap.

Rule-based and intrinsic prongs stay model-free at runtime (lexicons,
spaCy `en_core_web_sm`, generating-model logprobs).

The 0.5B/1.5B instance is **shared** (one vLLM, task prefixes
`[JUDGE]`, `[CLAIMS]`, `[READABILITY]`), matching `TODO.md`. Dual
output: baseline score and LLM score on every upgraded dimension.

---

## Dispatch pattern

Typical slice of work after approval. **Outside** the rate window,
independent NTNU panes may run in parallel. **Inside** Mon–Fri
08:00–18:00, the same graph is a queue (one NTNU job at a time). Qwen
host follows the rate-window table.

```
Captain
  ├─ Scout (NTNU GLM-Flash) → steal-adapt-skip briefs
  ├─ Protocol Steward (NTNU gpt-oss) → acceptance criteria
  ├─ Implementer (NTNU GLM) → code + tests
  ├─ Eval Scientist (NTNU Qwen 08–18 / Malvik Qwen otherwise)
  ├─ Dashboard (NTNU Mistral) if UI is in the slice
  ├─ Nordic Linguist (NTNU Magistral) if copy or lexicons change
  ├─ Reviewer (NTNU Kimi) → merge/no-merge
  └─ Git Historian (same Qwen host as Eval) → commits + index
Captain merges worktree, then Historian records it.
```

### Dispatch mechanics — herdr panes (mandatory)

Crew work runs in the herdr panes of workspace `w0`, never as
in-session subagents, so the user can watch each pane live. Panes:
`dj-scout` w0:t3, `dj-protocol` t4, `dj-implementer` t5,
`dj-dashboard` t6, `dj-eval` t7, `dj-reviewer` t8, `dj-nordic` t9,
`dj-git` tA. Captain is w0:t1.

1. Write the brief to a file (e.g. `/tmp/slice-<n>-<role>.md`) and send
   the short pointer: `herdr agent prompt <name> "Read <path> and
   execute it."`.
2. `herdr agent prompt --wait` often times out while the pane is still
   working. Poll instead: `herdr agent get <name>` (status
   idle/working/done) and `herdr agent read <name> --source visible
   --lines N`. `--source recent-unwrapped` fails while an agent is
   working.
3. `herdr tab focus <tab_id>` restores the Captain tab afterwards.
4. The one-NTNU-job-at-a-time rule counts all panes; serialise there
   exactly as the rate-window table says. This is a **concurrency**
   limit: one NTNU request in flight, no weekly cap of our own. The
   "Weekly limit left: N%" figure in a pane's status bar is the Grok
   CLI's own subscription limit, not NTNU's; treat it as a per-pane
   retry constraint, not a reason to stop the plan. **The Captain idles
   while a worker is in flight**: dispatch, register a status watcher,
   end the turn, and run no other model work until the pane reports.
   Parallel Captain work during a worker turn causes shared-key rate
   limits (observed 2026-11-14/15).
5. Panes own their worktrees when a slice needs isolation; the pane
   creates and reports it, the Captain merges as before.

In-session `spawn_subagent` is only for incidental officer work the
user has not asked to watch. A Grok workflow
(`.grok/workflows/d75-slice.rhai`) remains unimplemented; crew slices
use the panes above.

---

## Out of scope for the crew until asked

- Fine-tuning or LoRA of the 0.5B judge
- 200k-entity Wikidata dump
- Native-speaker lexicon annotation campaign
- User study / human-judgment correlation (research claim, later phase)
- Publishing or pushing to `origin/master`
- Committing `inspiration.txt`, `review.txt`, or `deliverable/`
