"""Tests for the MiniCheck NLI verifier wrapper (src/resources/nli_verifier.py).

Protocol tests with stubbed model/tokenizer — no network, no model
download. Pins the official MiniCheck-Flan-T5-Large inference protocol:
  input = "predict: " + document + eos_token + claim
  decoder_input_ids = zeros((batch, 1))
  p_support = softmax(logits[:, [3, 209]], dim=-1)[:, 1]
and the never-fabricate failure semantics (VerifierUnavailableError).
"""

import math
from types import SimpleNamespace

import pytest
import torch

from src.resources.nli_verifier import (
    NliVerifier, VerifierUnavailableError, _NO_SUPPORT_LOGIT_ID,
    _SUPPORT_LOGIT_ID, _MAX_INPUT_LENGTH,
)

VOCAB = 32000  # Flan-T5-large vocab size; only the two label ids matter


class StubTokenizer:
    """Records calls; returns fixed-shaped tensors like the real tokenizer."""

    eos_token = "</s>"

    def __init__(self):
        self.calls = []

    def __call__(self, inputs, truncation=None, max_length=None,
                 padding=None, return_tensors=None):
        self.calls.append({
            'inputs': list(inputs),
            'truncation': truncation,
            'max_length': max_length,
            'padding': padding,
            'return_tensors': return_tensors,
        })
        batch = len(inputs)
        return SimpleNamespace(
            input_ids=torch.zeros((batch, 5), dtype=torch.long),
            attention_mask=torch.ones((batch, 5), dtype=torch.long),
        )


class StubModel:
    """Returns per-claim [no_support, support] logits at ids 3 and 209."""

    def __init__(self, support_probs):
        # support_probs: list of P(support) per batch row
        self.support_probs = list(support_probs)
        self.calls = []

    def __call__(self, input_ids=None, attention_mask=None,
                 decoder_input_ids=None):
        self.calls.append(SimpleNamespace(
            input_ids=input_ids, attention_mask=attention_mask,
            decoder_input_ids=decoder_input_ids,
        ))
        batch = input_ids.shape[0]
        logits = torch.zeros((batch, VOCAB))
        for i in range(batch):
            p = self.support_probs[i % len(self.support_probs)]
            # logit pair whose softmax reproduces p for the [3, 209] slice
            logits[i, _NO_SUPPORT_LOGIT_ID] = math.log(1 - p)
            logits[i, _SUPPORT_LOGIT_ID] = math.log(p)
        return SimpleNamespace(logits=logits)


class FailingModel:
    def __call__(self, **kwargs):
        raise RuntimeError("inference exploded")


def make_verifier(support_probs):
    tok = StubTokenizer()
    model = StubModel(support_probs)
    return NliVerifier(model=model, tokenizer=tok), tok, model


class TestProtocol:

    def test_input_format_pinned(self):
        """Input strings are "predict: " + doc + eos_token + claim."""
        v, tok, _ = make_verifier([0.9])
        p = v.score("Oslo is the capital of Norway.",
                    "Norway capital Oslo. Norway country Europe.")
        assert list(tok.calls[0]['inputs']) == [
            "predict: Norway capital Oslo. Norway country Europe.</s>"
            "Oslo is the capital of Norway."
        ]
        assert 0.0 <= p <= 1.0

    def test_tokenizer_kwargs_pinned(self):
        """Tokenization uses truncation, max_length=1024, padding, pt."""
        v, tok, _ = make_verifier([0.5])
        v.score("a claim", "a doc")
        call = tok.calls[0]
        assert call['truncation'] is True
        assert call['max_length'] == _MAX_INPUT_LENGTH == 1024
        assert call['padding'] is True
        assert call['return_tensors'] == "pt"

    def test_decoder_input_ids_zeros(self):
        """decoder_input_ids is a zeros((batch, 1)) long tensor."""
        v, _, model = make_verifier([0.9, 0.1])
        v.score_many(["c1", "c2"], ["d1", "d2"])
        dec = model.calls[0].decoder_input_ids
        assert dec.dtype == torch.long
        assert dec.shape == (2, 1)
        assert (dec == 0).all()

    def test_support_probability_from_label_ids(self):
        """p = softmax(logits[:, [3, 209]], dim=-1)[:, 1]."""
        v, _, _ = make_verifier([0.9])
        p = v.score("claim", "doc")
        assert p == pytest.approx(0.9, abs=1e-6)

    def test_batch_order_preserved(self):
        """score_many returns probabilities aligned with input order."""
        v, _, _ = make_verifier([0.9, 0.05, 0.5])
        ps = v.score_many(["c1", "c2", "c3"], ["d1", "d2", "d3"])
        assert ps[0] == pytest.approx(0.9, abs=1e-6)
        assert ps[1] == pytest.approx(0.05, abs=1e-6)
        assert ps[2] == pytest.approx(0.5, abs=1e-6)

    def test_score_is_single_item_score_many(self):
        """score() delegates to score_many with one aligned pair."""
        v, tok, _ = make_verifier([0.7])
        assert v.score("c", "d") == pytest.approx(0.7, abs=1e-6)
        assert len(tok.calls) == 1


class TestLazyAndConfig:

    def test_construction_loads_nothing(self):
        """Constructing NliVerifier does not load a model."""
        v = NliVerifier()
        assert v.loaded is False

    def test_injected_stubs_count_as_loaded(self):
        v, _, _ = make_verifier([0.5])
        assert v.loaded is True

    def test_env_model_and_cache(self, monkeypatch):
        """Model name and cache dir come from DANKJEWEL_VERIFIER_* env vars."""
        monkeypatch.setenv("DANKJEWEL_VERIFIER_MODEL", "org/some-verifier")
        monkeypatch.setenv("DANKJEWEL_VERIFIER_CACHE_DIR", "/tmp/hf-cache")
        v = NliVerifier()
        assert v.model_name == "org/some-verifier"
        assert v.cache_dir == "/tmp/hf-cache"

    def test_explicit_model_name_wins(self, monkeypatch):
        monkeypatch.setenv("DANKJEWEL_VERIFIER_MODEL", "org/env-model")
        v = NliVerifier(model_name="org/explicit")
        assert v.model_name == "org/explicit"


class TestFailures:

    def test_load_failure_raises_unavailable(self, monkeypatch):
        """A failing model load raises VerifierUnavailableError, never a score."""
        def _boom(*args, **kwargs):
            raise OSError("no such model on the hub")
        monkeypatch.setattr(
            "transformers.AutoModelForSeq2SeqLM.from_pretrained", _boom)
        v = NliVerifier()
        with pytest.raises(VerifierUnavailableError):
            v.score("claim", "doc")
        assert v.loaded is False

    def test_inference_failure_raises_unavailable(self):
        """A failing forward pass raises VerifierUnavailableError."""
        v = NliVerifier(model=FailingModel(), tokenizer=StubTokenizer())
        with pytest.raises(VerifierUnavailableError):
            v.score("claim", "doc")

    def test_score_many_length_mismatch(self):
        v, _, _ = make_verifier([0.5])
        with pytest.raises(ValueError):
            v.score_many(["c1"], ["d1", "d2"])

    def test_score_many_empty(self):
        v, _, _ = make_verifier([0.5])
        with pytest.raises(ValueError):
            v.score_many([], [])
