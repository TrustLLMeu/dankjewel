"""Configuration and constants for the evaluation system."""

import os

# Language configurations
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'da': 'Danish',
    'nl': 'Dutch',
    'fo': 'Faroese',
    'de': 'German',
    'is': 'Icelandic',
    'nb': 'Norsk bokmål',
    'nn': 'Norsk nynorsk',
    'sv': 'Swedish'
}

# ── Flesch readability coefficients ──────────────────────────────────
# Language-aware Flesch readability — a heuristic baseline.  LLMs are
# state-of-the-art for readability assessment; a fine-tuned model will
# replace this in a future iteration.
#
# Each entry is (base, ASL_coefficient, ASW_coefficient) for:
#   score = base − ASL_coeff × (words/sentences) − ASW_coeff × (syllables/words)
#
# Empirically validated coefficients:
#   en  – Flesch, R. (1948). "A New Readability Yardstick".
#         Journal of Applied Psychology, 32(3), 221–233.
#   de  – Amstad, T. (1978). Wie verständlich sind unsere Zeitungen?
#   nl  – Douma, J. H. (1960). De leesbaarheid van landbouwbladen.
#
# Pan-Germanic fallback (da, fo, is, nb, nn, sv):
#   Matricciani, E. (2023). "Readability Indices Do Not Say It All on a
#   Text Readability". Analytics, 2(2), 296–314. MDPI.
FLESCH_COEFFICIENTS: dict[str, tuple[float, float, float]] = {
    'en': (206.835, 1.015, 84.6),
    'de': (180.0,   1.0,   58.5),     # Amstad (1978)
    'nl': (206.835, 0.93,  77.0),     # Douma (1960)
}
FLESCH_PAN_GERMANIC: tuple[float, float, float] = (206.835, 1.0, 70.0)  # Matricciani (2023)

# Map project language codes → textstat.set_lang() codes for syllable
# counting.  textstat delegates to pyphen hyphenation dictionaries.
# Languages without a native pyphen dictionary use Norwegian Nynorsk
# (nn) as the nearest available North-Germanic backend.
# See ASSUMPTIONS.md A11.
TEXTSTAT_LANG_MAP: dict[str, str] = {
    'en': 'en',
    'da': 'da',     # pyphen da_DK
    'de': 'de',     # pyphen de_DE
    'fo': 'nn',     # Faroese → Nynorsk (nearest; see A11)
    'is': 'nn',     # Icelandic → Nynorsk (nearest; see A11)
    'nb': 'nb',     # pyphen nb_NO
    'nl': 'nl',     # pyphen nl_NL
    'nn': 'nn',     # pyphen nn_NO
    'sv': 'sv',     # pyphen sv_SE
}

# Human-readable Flesch formula variant names for metadata.
FLESCH_FORMULA_NAMES: dict[str, str] = {
    'en': 'Flesch Reading Ease',
    'de': 'Flesch-Amstad',
    'nl': 'Flesch-Douma',
}
FLESCH_PAN_GERMANIC_NAME: str = 'Flesch-Matricciani (Pan-Germanic)'

# Prong configurations
PRONG_TIMEOUT_SECONDS = 2.0
BATCH_SIZE = 32

# Model configurations
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000")
# Bearer token for the generator endpoint. Needed when the OpenAI-compatible
# server requires auth (e.g. llama.cpp started with --api-key).
VLLM_API_KEY = os.environ.get("VLLM_API_KEY")
VLLM_MODEL_NAME = os.environ.get("VLLM_MODEL_NAME", None)  # Set at runtime or via env
VLLM_TENSOR_PARALLEL_SIZE = int(os.environ.get("VLLM_TENSOR_PARALLEL_SIZE", "1"))

# Prong 4: Intrinsic evaluation — number of top logprobs to request from vLLM.
# Higher k gives better entropy approximation at negligible generation cost.
# See ASSUMPTIONS.md A1 for scientific justification.
VLLM_LOGPROBS_K = int(os.environ.get("VLLM_LOGPROBS_K", "20"))

# API server configuration
API_HOST = os.environ.get("IE_API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("IE_API_PORT", "8080"))

# Prong 3: Extraction-based configurations
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Prefer the extended FEVER-derived DB (thousands of entities pulled from
# claim text + evidence pages) over the small hand-curated seed DB (~122
# entities: Paris/Tromsø/Mount Everest plus the slice-6b Nordic/TrustLLM
# expansion — used by unit tests in
# tests/test_prong3.py, which instantiate OfflineWikidata()/Prong3Extraction()
# directly and are unaffected by this constant). Falls back to the seed DB
# if the extended DB hasn't been built yet (e.g. fresh clone).
_WIKIDATA_FEVER_DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'wikidata_fever.db')
_WIKIDATA_SEED_DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'wikidata_seed.db')
WIKIDATA_DB_PATH = (
    _WIKIDATA_FEVER_DB_PATH if os.path.exists(_WIKIDATA_FEVER_DB_PATH)
    else _WIKIDATA_SEED_DB_PATH
)
SPACY_MODEL = 'en_core_web_sm'  # Phase 1: English only

