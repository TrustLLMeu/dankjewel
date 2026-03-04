"""Prong 4: Intrinsic Evaluation (Model-based metrics from logits/probabilities)."""

import time
import numpy as np
from dataclasses import dataclass
from typing import Optional, List
from src.base import Evaluator, ProngResult
from src.dimensions.base_dimension import ScorableDimension


@dataclass
class IntrinsicData:
    """Container for intrinsic evaluation data from LLM inference.

    Supports two data sources:
    1. Full logits (from vLLM native Python API — future)
    2. Sparse top-k logprobs (from vLLM HTTP API — current)

    See ASSUMPTIONS.md A1 for the top-k approximation justification.
    """
    token_ids: List[int]  # Generated token IDs [seq_len]
    logits: Optional[np.ndarray] = None  # [seq_len, vocab_size] raw model logits (future)
    log_likelihoods: Optional[np.ndarray] = None  # [seq_len] log P(token_i) per token
    top_k_logprobs: Optional[np.ndarray] = None  # [seq_len, k] top-k log-probs (from HTTP API)
    top_k: int = 0  # Number of top logprobs per token
    vocab_size: Optional[int] = None  # Size of vocabulary
    token_strings: Optional[List[str]] = None  # Token strings (from HTTP API)

    def validate(self):
        """Check data consistency."""
        assert len(self.token_ids) > 0, "Empty token sequence"
        if self.logits is not None:
            assert self.logits.shape[0] == len(self.token_ids), \
                f"Logits seq_len {self.logits.shape[0]} != token_ids len {len(self.token_ids)}"
            if self.vocab_size is None:
                self.vocab_size = self.logits.shape[1]
        if self.top_k_logprobs is not None:
            assert self.top_k_logprobs.shape[0] == len(self.token_ids), \
                f"top_k_logprobs seq_len {self.top_k_logprobs.shape[0]} != token_ids len {len(self.token_ids)}"
            if self.top_k == 0:
                self.top_k = self.top_k_logprobs.shape[1]

    def has_logits(self) -> bool:
        """Check if full logits are available."""
        return self.logits is not None and self.logits.size > 0

    def has_log_likelihoods(self) -> bool:
        """Check if per-token log-likelihoods are available."""
        return self.log_likelihoods is not None and len(self.log_likelihoods) > 0

    def has_top_k_logprobs(self) -> bool:
        """Check if sparse top-k logprobs are available (from HTTP API)."""
        return self.top_k_logprobs is not None and self.top_k_logprobs.size > 0


class Uncertainty(ScorableDimension):
    """Mean token confidence (uncertainty = 1 - confidence)."""

    def __init__(self):
        super().__init__(name="Uncertainty")

    def evaluate(self, intrinsic_data: IntrinsicData):
        """Compute uncertainty as 1 - mean(confidence).

        Priority: log_likelihoods (exact) > logits (exact) > top_k_logprobs (approx).
        """
        try:
            if intrinsic_data.has_log_likelihoods():
                # Exact: confidence = exp(log_prob) for the chosen token
                confidences = np.exp(np.clip(intrinsic_data.log_likelihoods, -100, 0))
                mean_confidence = float(np.mean(confidences))
                uncertainty = 1.0 - mean_confidence
                return self.create_score(
                    value=max(0.0, min(1.0, uncertainty)),
                    raw_value={'mean_confidence': mean_confidence},
                    metadata={'method': 'log_likelihoods', 'num_tokens': len(confidences)}
                )
            elif intrinsic_data.has_logits():
                logits = intrinsic_data.logits
                logits_stable = logits - np.max(logits, axis=1, keepdims=True)
                exp_logits = np.exp(logits_stable)
                probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
                confidences = np.max(probs, axis=1)
                mean_confidence = float(np.mean(confidences))
                uncertainty = 1.0 - mean_confidence
                return self.create_score(
                    value=max(0.0, min(1.0, uncertainty)),
                    raw_value={'mean_confidence': mean_confidence},
                    metadata={'method': 'logits', 'num_tokens': len(confidences)}
                )
            else:
                return self.create_score(0.5, metadata={'error': 'No logprob data available'})
        except Exception as e:
            return self.create_score(0.5, metadata={'error': str(e)})


class Perplexity(ScorableDimension):
    """Perplexity of generated text (raw, not normalized)."""

    def __init__(self):
        super().__init__(name="Perplexity")

    def evaluate(self, intrinsic_data: IntrinsicData):
        """Compute perplexity = exp(mean NLL)."""
        try:
            if intrinsic_data.has_log_likelihoods():
                log_liks = intrinsic_data.log_likelihoods
                mean_nll = float(np.mean(-log_liks))  # Negate for NLL
                ppl = float(np.exp(mean_nll))
                return self.create_score(
                    value=ppl,
                    raw_value={'mean_nll': mean_nll, 'perplexity': ppl},
                    metadata={'method': 'log_likelihoods', 'num_tokens': len(log_liks)}
                )
            elif intrinsic_data.has_logits():
                # Estimate from logits: use max logit prob
                logits = intrinsic_data.logits
                logits_stable = logits - np.max(logits, axis=1, keepdims=True)
                exp_logits = np.exp(logits_stable)
                probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
                top1_probs = np.max(probs, axis=1)
                log_probs = np.log(np.clip(top1_probs, 1e-10, 1.0))
                mean_log_prob = float(np.mean(log_probs))
                ppl = float(np.exp(-mean_log_prob))
                return self.create_score(
                    value=ppl,
                    raw_value={'perplexity': ppl},
                    metadata={'method': 'logits', 'num_tokens': len(logits)}
                )
            else:
                return self.create_score(1.0, metadata={'error': 'No logits or log_likelihoods'})
        except Exception as e:
            return self.create_score(1.0, metadata={'error': str(e)})


class TokenEntropy(ScorableDimension):
    """Shannon entropy of token-level distributions (normalized to [0,1])."""

    def __init__(self):
        super().__init__(name="Token Entropy")

    def evaluate(self, intrinsic_data: IntrinsicData):
        """Compute Shannon entropy of per-token distributions (in bits).

        Uses full logits if available, otherwise falls back to top-k
        approximation (see ASSUMPTIONS.md A1).
        """
        try:
            if intrinsic_data.has_logits():
                # Exact: full vocabulary distribution
                logits = intrinsic_data.logits
                logits_stable = logits - np.max(logits, axis=1, keepdims=True)
                exp_logits = np.exp(logits_stable)
                probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)

                entropy_nats = -np.sum(probs * np.log(np.clip(probs, 1e-10, 1.0)), axis=1)
                entropy_bits = entropy_nats / np.log(2.0)

                mean_entropy = float(np.mean(entropy_bits))
                max_entropy = float(np.log2(intrinsic_data.vocab_size)) if intrinsic_data.vocab_size else 16.0
                normalized_entropy = min(1.0, mean_entropy / max_entropy) if max_entropy > 0 else 0.5

                return self.create_score(
                    value=normalized_entropy,
                    raw_value={'mean_entropy_bits': mean_entropy, 'max_entropy_bits': max_entropy},
                    metadata={'method': 'logits', 'num_tokens': len(logits), 'vocab_size': intrinsic_data.vocab_size}
                )

            elif intrinsic_data.has_top_k_logprobs():
                # Approximation: top-k logprobs from HTTP API
                top_k_lp = intrinsic_data.top_k_logprobs  # [seq_len, k]
                k = top_k_lp.shape[1]

                # Convert logprobs → probabilities, renormalize to sum to 1
                probs = np.exp(np.clip(top_k_lp, -100, 0))
                probs = probs / np.sum(probs, axis=1, keepdims=True)

                entropy_nats = -np.sum(probs * np.log(np.clip(probs, 1e-10, 1.0)), axis=1)
                entropy_bits = entropy_nats / np.log(2.0)

                mean_entropy = float(np.mean(entropy_bits))
                # Normalize against max entropy for k alternatives (not full vocab)
                max_entropy = float(np.log2(k)) if k > 1 else 1.0
                normalized_entropy = min(1.0, mean_entropy / max_entropy) if max_entropy > 0 else 0.5

                return self.create_score(
                    value=normalized_entropy,
                    raw_value={'mean_entropy_bits': mean_entropy, 'max_entropy_bits': max_entropy},
                    metadata={
                        'method': 'top_k_approximation',
                        'k': k,
                        'num_tokens': len(top_k_lp),
                        'assumption': 'A1',
                    }
                )
            else:
                return self.create_score(0.5, metadata={'error': 'No logits or top_k_logprobs available'})
        except Exception as e:
            return self.create_score(0.5, metadata={'error': str(e)})


class SemanticEntropy(ScorableDimension):
    """Semantic entropy: entropy across clustered similar tokens (normalized to [0,1])."""

    def __init__(self):
        super().__init__(name="Semantic Entropy")

    def evaluate(self, intrinsic_data: IntrinsicData):
        """Compute semantic entropy by clustering top-k tokens.

        Groups tokens by top-k probable alternatives and computes entropy
        across clusters. Uses full logits if available, otherwise top-k
        logprobs from the HTTP API (natural fit — see ASSUMPTIONS.md A1).
        """
        try:
            if intrinsic_data.has_logits():
                # Full logits: extract top-k ourselves
                logits = intrinsic_data.logits
                logits_stable = logits - np.max(logits, axis=1, keepdims=True)
                exp_logits = np.exp(logits_stable)
                probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)

                k = min(5, probs.shape[1])
                top_k_indices = np.argsort(-probs, axis=1)[:, :k]
                top_k_probs = np.take_along_axis(probs, top_k_indices, axis=1)
                method = 'logits'

            elif intrinsic_data.has_top_k_logprobs():
                # Sparse top-k from HTTP API
                top_k_lp = intrinsic_data.top_k_logprobs
                k = top_k_lp.shape[1]
                top_k_probs = np.exp(np.clip(top_k_lp, -100, 0))
                method = 'top_k_approximation'

            else:
                return self.create_score(0.5, metadata={'error': 'No logits or top_k_logprobs available'})

            # Renormalize top-k probabilities to sum to 1
            top_k_probs_norm = top_k_probs / np.sum(top_k_probs, axis=1, keepdims=True)

            # Compute entropy on top-k distribution
            semantic_entropy_nats = -np.sum(
                top_k_probs_norm * np.log(np.clip(top_k_probs_norm, 1e-10, 1.0)),
                axis=1
            )
            semantic_entropy_bits = semantic_entropy_nats / np.log(2.0)

            mean_semantic_entropy = float(np.mean(semantic_entropy_bits))
            max_entropy = float(np.log2(k)) if k > 1 else 1.0
            normalized_entropy = min(1.0, mean_semantic_entropy / max_entropy) if max_entropy > 0 else 0.5

            metadata = {
                'method': method,
                'k': k,
                'num_tokens': len(top_k_probs),
            }
            if method == 'top_k_approximation':
                metadata['assumption'] = 'A1'

            return self.create_score(
                value=normalized_entropy,
                raw_value={'mean_semantic_entropy_bits': mean_semantic_entropy, 'max_entropy_bits': max_entropy},
                metadata=metadata,
            )
        except Exception as e:
            return self.create_score(0.5, metadata={'error': str(e)})


class Prong4Intrinsic(Evaluator):
    """Intrinsic evaluator using model logits and probabilities from vLLM."""

    def __init__(self):
        super().__init__(prong_name="Intrinsic (Prong 4)")
        self._init_dimensions()

    def _init_dimensions(self) -> None:
        """Initialize all intrinsic dimensions."""
        self.register_dimension(Uncertainty())
        self.register_dimension(Perplexity())
        self.register_dimension(TokenEntropy())
        self.register_dimension(SemanticEntropy())

    def evaluate(self, text: str, intrinsic_data: Optional[IntrinsicData] = None) -> ProngResult:
        """
        Evaluate text using intrinsic model metrics.

        Args:
            text: Generated text (for reference)
            intrinsic_data: IntrinsicData from vLLM containing logits/log-likelihoods
                           If None, returns neutral scores (Phase 1 fallback)

        Evaluates:
        - Uncertainty (mean token confidence, inverted)
        - Perplexity (exponential of avg negative log-likelihood, raw)
        - Token Entropy (Shannon entropy of token distributions)
        - Semantic Entropy (entropy of top-k clustered tokens)
        """
        start_time = time.time()
        dimensions = []
        error = None

        if intrinsic_data is None:
            # Phase 1 fallback: No vLLM data available
            # Return neutral scores as placeholders
            from src.base import DimensionScore
            dimensions = [
                DimensionScore(
                    name='Uncertainty',
                    value=0.5,
                    raw_value=None,
                    metadata={'note': 'No intrinsic data available (vLLM required)'}
                ),
                DimensionScore(
                    name='Perplexity',
                    value=1.0,
                    raw_value=None,
                    metadata={'note': 'No intrinsic data available (vLLM required)'}
                ),
                DimensionScore(
                    name='Token Entropy',
                    value=0.5,
                    raw_value=None,
                    metadata={'note': 'No intrinsic data available (vLLM required)'}
                ),
                DimensionScore(
                    name='Semantic Entropy',
                    value=0.5,
                    raw_value=None,
                    metadata={'note': 'No intrinsic data available (vLLM required)'}
                ),
            ]
        else:
            try:
                intrinsic_data.validate()

                for dimension in self.dimensions.values():
                    score = dimension.evaluate(intrinsic_data)
                    dimensions.append(score)
            except Exception as e:
                error = str(e)

        processing_time = time.time() - start_time

        return ProngResult(
            prong_name=self.prong_name,
            dimensions=dimensions,
            processing_time=processing_time,
            error=error
        )

