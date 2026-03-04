"""Adapter: convert vLLM GenerationResult → Prong 4 IntrinsicData.

The vLLM OpenAI-compatible HTTP API returns sparse top-k logprobs per token,
not full vocabulary logit distributions. This adapter converts that sparse
data into the IntrinsicData format consumed by Prong 4 dimensions.

Data mapping:
    token_logprobs  → log_likelihoods   (exact, per-token NLL)
    top_logprobs    → top_k_logprobs    (sparse [seq_len, k] matrix)
    tokens          → token_strings     (no integer IDs from HTTP API)

See ASSUMPTIONS.md A1 for the scientific justification of the top-k approach.
"""

import logging
from typing import Optional

import numpy as np

from src.vllm_client import GenerationResult
from src.prongs.prong4_intrinsic import IntrinsicData

logger = logging.getLogger(__name__)


def generation_result_to_intrinsic_data(
    gen: GenerationResult,
) -> Optional[IntrinsicData]:
    """Convert a vLLM GenerationResult into IntrinsicData for Prong 4.

    Args:
        gen: GenerationResult from VLLMClient.generate().

    Returns:
        IntrinsicData ready for Prong4Intrinsic.evaluate(), or None if
        the generation has no logprob data.
    """
    if not gen.token_logprobs or not gen.tokens:
        logger.warning("GenerationResult has no logprob data — Prong 4 will use fallback")
        return None

    seq_len = len(gen.tokens)

    # ── log_likelihoods: exact per-token log-probability ────────────────
    # vLLM returns log P(token_i | token_<i) directly.
    # These are log-likelihoods (not negative). Prong 4's Perplexity
    # expects log-likelihoods and negates them internally.
    log_likelihoods = np.array(gen.token_logprobs, dtype=np.float64)

    # ── top_k_logprobs: sparse [seq_len, k] matrix ─────────────────────
    # Each entry in gen.top_logprobs is a dict {token_str: logprob, ...}
    # We convert to a dense matrix sorted by descending probability.
    top_k_logprobs = None
    k = 0
    if gen.top_logprobs:
        # Determine k from the first non-empty entry
        for entry in gen.top_logprobs:
            if entry:
                k = len(entry)
                break

        if k > 0:
            top_k_logprobs = np.full((seq_len, k), -100.0, dtype=np.float64)
            for i, entry in enumerate(gen.top_logprobs):
                if entry:
                    # Sort by logprob descending (most probable first)
                    sorted_lps = sorted(entry.values(), reverse=True)
                    actual_k = min(len(sorted_lps), k)
                    top_k_logprobs[i, :actual_k] = sorted_lps[:actual_k]

    # ── token_ids: placeholder (HTTP API returns strings, not IDs) ──────
    # Use sequential indices as placeholder IDs. The actual token strings
    # are available in gen.tokens if needed.
    token_ids = list(range(seq_len))

    data = IntrinsicData(
        token_ids=token_ids,
        log_likelihoods=log_likelihoods,
        top_k_logprobs=top_k_logprobs,
        top_k=k,
        token_strings=gen.tokens,
    )

    logger.info(
        "Converted GenerationResult → IntrinsicData: %d tokens, k=%d",
        seq_len, k,
    )

    return data

