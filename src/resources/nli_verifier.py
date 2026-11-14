"""MiniCheck NLI verifier for Prong 3 (opt-in upgraded track).

Implements the official MiniCheck inference protocol directly with
transformers, per Tang, Laban & Durrett, *MiniCheck: Efficient
Fact-Checking of LLMs on Grounding Documents*, EMNLP 2024
(https://aclanthology.org/2024.emnlp-main.499/, code
https://github.com/Liyan06/MiniCheck, model weights
`lytang/MiniCheck-Flan-T5-Large` on Hugging Face). Protocol as pinned
by the official repo's `minicheck/ft5/model.py`:

  input  = "predict: " + document + tokenizer.eos_token + claim
  logits = model(input_ids, attention_mask,
                 decoder_input_ids=zeros((batch, 1))).logits.squeeze(1)
  p_support = softmax(logits[:, [3, 209]], dim=-1)[:, 1]

The label ids 3 (no-support) and 209 (support) are hardcoded in the
official repo for the Flan-T5 tokenizer — they are not discovered at
runtime here either, deliberately.

**Do NOT `pip install minicheck`:** the PyPI package `minicheck` is an
UNRELATED project (a different codebase, not the EMNLP 2024 MiniCheck).
That namesake is why this module re-implements the official protocol
instead of depending on a package.

The model (Flan-T5-large, 770M) runs on CPU with the transformers +
torch already in requirements — no new pip dependencies. Weights load
lazily on the first score call (~5 s from a warm HF cache, ~30 s cold;
one-time per process), and only when the caller opts in — the default
Prong 3 path never constructs or loads the model. Warm CPU inference
is ~0.2 s per claim.

Failure semantics: a load or inference failure raises
VerifierUnavailableError. The verifier never fabricates a score —
callers translate the error into an 'unknown' relation and keep the
rule-based baseline (see FactualAccuracy).

Configuration (environment, read at construction):

    DANKJEWEL_VERIFIER_MODEL       default lytang/MiniCheck-Flan-T5-Large
    DANKJEWEL_VERIFIER_CACHE_DIR   optional HF cache directory override

Tested with:
    transformers==5.23.0
    torch==2.15.0
    Python 3.12
"""

import logging
import os
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "lytang/MiniCheck-Flan-T5-Large"

# Label ids hardcoded by the official MiniCheck repo for the Flan-T5
# tokenizer: 3 = no-support, 209 = support. Index 1 of the [3, 209]
# slice after softmax is the support probability.
_NO_SUPPORT_LOGIT_ID = 3
_SUPPORT_LOGIT_ID = 209
_MAX_INPUT_LENGTH = 1024


class VerifierUnavailableError(RuntimeError):
    """The NLI verifier model could not be loaded or run."""


class NliVerifier:
    """MiniCheck-Flan-T5-Large fact-checking score against a document.

    score(claim, context) returns P(claim is supported by context) in
    [0, 1] under the official MiniCheck protocol. The model and
    tokenizer load lazily on the first score call (first use only —
    constructing the object is free), guarded so any load or inference
    failure raises VerifierUnavailableError instead of returning an
    invented score.
    """

    def __init__(self, model_name: Optional[str] = None,
                 model=None, tokenizer=None):
        """Create the verifier.

        Args:
            model_name: HF model id (default: DANKJEWEL_VERIFIER_MODEL,
                then lytang/MiniCheck-Flan-T5-Large).
            model: injected model double for tests (anything callable as
                model(input_ids=..., attention_mask=..., decoder_input_ids=...)
                returning an object with .logits). None = lazy real load.
            tokenizer: injected tokenizer double for tests (needs
                .eos_token and __call__ accepting truncation/max_length/
                padding/return_tensors). None = lazy real load.
        """
        self.model_name = (
            model_name
            or os.environ.get("DANKJEWEL_VERIFIER_MODEL")
            or DEFAULT_MODEL
        )
        self.cache_dir = os.environ.get("DANKJEWEL_VERIFIER_CACHE_DIR")
        self._model = model
        self._tokenizer = tokenizer
        self._load_lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        """Whether the model and tokenizer are loaded (real or stub)."""
        return self._model is not None and self._tokenizer is not None

    def _ensure_loaded(self):
        """Lazily load the model and tokenizer on first use.

        Raises:
            VerifierUnavailableError: on any load failure. Imports of
                torch/transformers happen here, not at module import, so
                the default (flag-off) path never pays for them.
        """
        if self.loaded:
            return
        with self._load_lock:
            if self.loaded:
                return
            try:
                import torch
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            except Exception as e:
                raise VerifierUnavailableError(
                    f"verifier dependencies unavailable: {type(e).__name__}: {e}"
                ) from e
            try:
                kwargs = {"cache_dir": self.cache_dir} if self.cache_dir else {}
                self._tokenizer = AutoTokenizer.from_pretrained(
                    self.model_name, **kwargs)
                self._model = AutoModelForSeq2SeqLM.from_pretrained(
                    self.model_name, torch_dtype=torch.float32, **kwargs)
                self._model.eval()
                logger.info("NliVerifier loaded %s", self.model_name)
            except Exception as e:
                self._model = None
                self._tokenizer = None
                raise VerifierUnavailableError(
                    f"could not load verifier model {self.model_name!r}: "
                    f"{type(e).__name__}: {e}"
                ) from e

    def score(self, claim: str, context: str) -> float:
        """Return P(claim is supported by context) in [0, 1].

        Args:
            claim: the claim sentence to check.
            context: the grounding document (formatted KB facts).

        Raises:
            VerifierUnavailableError: model load or inference failed.
        """
        return self.score_many([claim], [context])[0]

    def score_many(self, claims: List[str], contexts: List[str]) -> List[float]:
        """Batched score: support probabilities for aligned lists.

        One forward pass over the padded batch; result order matches
        the input order.

        Args:
            claims: claim sentences to check.
            contexts: grounding documents, one per claim.

        Returns:
            List of support probabilities in [0, 1], aligned with inputs.

        Raises:
            VerifierUnavailableError: model load or inference failed —
                never a fabricated score.
            ValueError: claims and contexts have different lengths or
                are empty.
        """
        if len(claims) != len(contexts):
            raise ValueError(
                f"claims ({len(claims)}) and contexts ({len(contexts)}) "
                "must have the same length")
        if not claims:
            raise ValueError("no claims to score")

        self._ensure_loaded()
        try:
            import torch

            # Official MiniCheck input format: "predict: " + doc + eos + claim.
            inputs = [
                "predict: " + (context or "") + self._tokenizer.eos_token + (claim or "")
                for claim, context in zip(claims, contexts)
            ]
            encoded = self._tokenizer(
                inputs, truncation=True, max_length=_MAX_INPUT_LENGTH,
                padding=True, return_tensors="pt")
            decoder_input_ids = torch.zeros((len(claims), 1), dtype=torch.long)
            with torch.no_grad():
                logits = self._model(
                    input_ids=encoded.input_ids,
                    attention_mask=encoded.attention_mask,
                    decoder_input_ids=decoder_input_ids,
                ).logits.squeeze(1)
            p_support = torch.softmax(
                logits[:, [_NO_SUPPORT_LOGIT_ID, _SUPPORT_LOGIT_ID]], dim=-1
            )[:, 1]
            return [float(p) for p in p_support]
        except VerifierUnavailableError:
            raise
        except Exception as e:
            raise VerifierUnavailableError(
                f"verifier inference failed: {type(e).__name__}: {e}"
            ) from e
