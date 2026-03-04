"""Configuration and constants for the evaluation system."""

import os

# Language configurations
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'da': 'Danish',
    'nl': 'Dutch',
    'fo': 'Faroese',
    'de': 'German',
    'no': 'Norwegian',
    'sv': 'Swedish'
}

# Prong configurations
PRONG_TIMEOUT_SECONDS = 2.0
BATCH_SIZE = 32

# Model configurations
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000")
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
WIKIDATA_DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'wikidata_seed.db')
SPACY_MODEL = 'en_core_web_sm'  # Phase 1: English only

