# Contributing to Dankjewel

**Last updated:** 2026-11-15

Thank you for contributing! This guide explains how to set up your environment,
create branches, submit pull requests, and use GitHub Issues to coordinate work.

---

## Getting Started

### 1. Clone the repository

```bash
git clone git@github.com:TrustLLMeu/dankjewel.git
cd dankjewel
```

### 2. Set up your environment

Follow [QUICKSTART.md](QUICKSTART.md) to install dependencies:

```bash
pip install -r requirements.txt
python3 -c "import nltk; nltk.download('vader_lexicon')"
python3 -m spacy download en_core_web_sm
python3 scripts/build_wikidata_db.py
```

**Requirements:** Python 3.12. The default configuration needs no model server:
Prongs 1–3 run locally (MiniLM embeddings, toxic-bert, spaCy, a 122-entity seed
KB). Two optional local model servers add the LLM tracks with their flags off by
default — a 0.5B judge (`DANKJEWEL_JUDGE_*`, default port 18092), a 1.5B claim
extractor (`DANKJEWEL_CLAIMS_*`, default 18093), and the in-process MiniCheck
verifier (`llm_verify`). Prong 4's intrinsic dimensions and the
`/generate-and-evaluate` path need a generator that returns logprobs. See
[QUICKSTART.md](QUICKSTART.md).

### 3. Run the tests

Confirm everything works before making changes:

```bash
pytest tests/ -v
```

---

## Branch Naming

Always branch from `master`. Use the following prefixes:

| Prefix | Purpose | Example |
|--------|---------|---------|
| `feature/` | New functionality | `feature/llm-claim-extraction` |
| `bugfix/` | Fixing a bug | `bugfix/flesch-negative-score` |
| `docs/` | Documentation only | `docs/update-quickstart` |
| `lexicon/` | Adding or editing lexicon files | `lexicon/add-swedish-cues` |

### Create a branch

```bash
git checkout master
git pull origin master
git checkout -b feature/my-feature-name
```

---

## Development Workflow

### 1. Make your changes

Edit the relevant files. If you are adding a new dimension, follow the
contracts in `src/base.py` (`DimensionScore`, `Dimension`, `Evaluator`) and
`src/dimensions/base_dimension.py` (`ScorableDimension`).

Key conventions used in this project:

- **Docstrings** on every public class and method (module-level docstring
  explaining purpose).
- **Scores normalized to 0.0–1.0** via `ScorableDimension.normalize_score()`.
- **Timing tracked** via `processing_time_ms` in results.
- **`DimensionScore.metadata`** should include `lang` when language-specific.
- **Evidence provenance**: dimensions that use more than one signal must record
  `metadata.evidence_sources` (`{source: {value, status, n}}`) per the Stage A
  contract in `src/evidence.py`; the dashboard's evidence panels render from it.
- **Honesty states**: missing evidence is `status="unknown"` and failed
  computation is `status="error"`; neither may be scored as a numeric value.
  Heavy opt-in tracks (judge, LLM claims, verifier) default to off and must
  degrade to `unknown` when their server is unreachable.

### 2. Write or update tests

New code must have tests in `tests/` following the existing pattern:

- One test file per prong: `test_prong1.py`, `test_prong2.py`, etc.
- Test file for the API: `test_api.py`
- Use `pytest`. See `tests/test_prong2.py` for examples.

### 3. Run tests before committing

```bash
# All tests
pytest tests/ -v

# Specific test
pytest tests/test_prong3.py -v

# With coverage
pytest tests/ --cov=src
```

All existing tests must pass. Do not submit a PR with failing tests.

### 4. Commit

Use imperative tense. Reference the prong or dimension affected:

```bash
# Good
git commit -m "Add vLLM-based claim extractor for Prong 3"
git commit -m "Fix Flesch score clamping for empty text in Prong 2"
git commit -m "Add Swedish uncertainty cues to lexicon"

# Bad
git commit -m "fixed stuff"
git commit -m "changes"
```

### 5. Push your branch

```bash
git push -u origin feature/my-feature-name
```

---

## Pull Requests

### Opening a PR

1. Push your branch to GitHub.
2. Go to the repository on GitHub and click **"Compare & pull request"**.
3. Target branch: `master`.
4. Fill in the PR description:
   - **What** changed and **why**.
   - Which prong(s) / dimension(s) are affected.
   - Link to the GitHub Issue if one exists (e.g., `Closes #12`).

### Review requirements

- **Every PR requires one approval from the project maintainer** before merge.
- Lexicon-only and docs-only PRs still require approval, but will be reviewed
  quickly.
- If the reviewer requests changes, push new commits to the same branch — the
  PR updates automatically.

### After approval

The maintainer will merge the PR. Do not merge your own PRs.

### Clean up

After merge, delete your branch locally:

```bash
git checkout master
git pull origin master
git branch -d feature/my-feature-name
```

---

## Using GitHub Issues

We use **GitHub Issues** to track bugs, feature requests, and tasks.
This is the single source of truth for project coordination — emails get lost,
Issues don’t.

### When to open an Issue

- You found a **bug** (e.g., a dimension returns scores outside 0–1).
- You want to **propose a feature** or enhancement.
- You are **picking up a task** from [TODO.md](TODO.md) and want to signal
  that you’re working on it.
- You have a **question** about the architecture or a design decision.

### How to open an Issue

1. Go to the **Issues** tab on GitHub.
2. Click **New issue**.
3. Use a clear title: `Bug: Flesch score negative for empty text` or
   `Feature: LLM-based readability dimension`.
4. In the description, include:
   - **What** you observed or want to change.
   - **Steps to reproduce** (for bugs).
   - **Which prong/dimension** is affected.
5. Apply a label if available: `bug`, `enhancement`, `documentation`, `question`.

### Linking Issues to PRs

Reference an Issue in your PR description to link them:

```
Closes #12
```

This automatically closes the Issue when the PR is merged.

### Assigning yourself

If you start working on an Issue, **assign yourself** so others know it’s
taken. Click “Assignees” on the right side of the Issue page.

### Keeping Issues updated

If work stalls or priorities change, leave a comment on the Issue. A short
“pausing this, will resume next week” is enough. This avoids duplicate work
and keeps the team informed without relying on email.

---

## Where to Contribute

See [TODO.md](TODO.md) for planned work. Good starting points:

| Task | Difficulty | Files |
|------|------------|-------|
| Add lexicon entries for a new language | Low | `src/resources/lexicons/<lang>.yaml` |
| Add test cases for existing dimensions | Low | `tests/test_prong*.py` |
| Add a fifth dimension (worked example) | Low–Medium | follow the recipe in `docs/EXTENSIBILITY.md`; one file in `src/dimensions/`, one in `tests/` |
| Extend claim extraction (harder cases, more languages) | Medium | `src/extraction/llm_claim_extractor.py` |
| LLM-based readability (Prong 2) | Medium | `src/dimensions/prong2_dimensions.py` |
| Extend the verifier benchmark | Medium | `scripts/eval_verifier.py`, `scripts/eval_scifact.py`, `scripts/eval_aggrefact.py` |
| Re-run the admission ablation or robustness matrix | Low | `scripts/eval_admission_ablation.py`, `scripts/eval_robustness.py` |

---

## Project Structure Reference

```
src/
├── base.py                  # DimensionScore, Dimension, Evaluator contracts
├── config.py                # Language codes, Flesch coefficients, constants
├── evidence.py              # evidence_sources + coverage contract (Stage A)
├── pipeline.py              # EvaluationPipeline — orchestrates all prongs
├── llm_judge_client.py      # shared OpenAI-compatible client ([JUDGE]/[CLAIMS])
├── vllm_client.py           # Async vLLM HTTP client
├── vllm_adapter.py          # GenerationResult → Prong 4 IntrinsicData
├── prongs/                  # One file per prong
├── dimensions/              # Dimension implementations
├── extraction/              # Claim extraction (spaCy triples + optional 1.5B atoms)
├── models/                  # Embeddings, toxicity model
├── resources/               # Lexicons, offline Wikidata, MiniCheck verifier
│   └── lexicons/            # Per-language YAML lexicons
tests/                       # pytest test files
scripts/                     # Benchmarking, latency and data-building scripts
```

---

## Setting Up Branch Protection (Maintainer Only)

To enforce the one-approval requirement on GitHub:

1. Go to **Settings → Branches → Add branch protection rule**.
2. Branch name pattern: `master`.
3. Enable **"Require a pull request before merging"**.
4. Set **"Required approvals: 1"**.
5. Optionally enable **"Require status checks to pass before merging"** and
   select the CI test job (when configured).
6. Save changes.

This prevents direct pushes to `master` and enforces the review workflow.

---

## Questions?

Open a GitHub Issue with the `question` label, or check:

- [README.md](README.md) — architecture overview
- [QUICKSTART.md](QUICKSTART.md) — setup and usage
- [TODO.md](TODO.md) — planned work
- [ASSUMPTIONS.md](ASSUMPTIONS.md) — scientific decisions and trade-offs
