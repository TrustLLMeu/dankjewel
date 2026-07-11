"""Toxicity model wrapper using Hugging Face Transformers for unitary/toxic-bert."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _best_cuda_device() -> str:
    """Return the CUDA device string with the most free memory, or 'cpu'."""
    try:
        import torch
        if not torch.cuda.is_available():
            return 'cpu'
        best_idx, best_free = 0, 0
        for i in range(torch.cuda.device_count()):
            free, _total = torch.cuda.mem_get_info(i)
            if free > best_free:
                best_free = free
                best_idx = i
        return f'cuda:{best_idx}'
    except Exception:
        return 'cpu'


class ToxicityModel:
    """Wrapper to load a pretrained toxicity classifier locally via Transformers."""

    def __init__(self, model_name: str = "unitary/toxic-bert", device: Optional[str] = None):
        self.model_name = model_name
        self.device = device
        self.model = None
        self.tokenizer = None

    def _init(self):
        if self.model is not None:
            return
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            import torch
        except Exception as e:
            raise RuntimeError("transformers and torch are required for toxicity model: pip install transformers torch")

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)

        if self.device is None:
            self.device = _best_cuda_device()

        try:
            self.model.to(self.device)
            logger.info("Toxicity model loaded on %s", self.device)
        except RuntimeError:
            # CUDA OOM — fall back to CPU
            logger.warning("Failed to load toxicity model on %s, falling back to CPU", self.device)
            self.device = 'cpu'
            self.model.to(self.device)

    def score(self, text: str) -> dict:
        """Return a dictionary with raw logits and a probability score (0..1).

        The returned dict: { 'probability': float, 'raw_logits': [..] }
        """
        self._init()
        import torch
        inputs = self.tokenizer(text, return_tensors='pt', truncation=True, max_length=512)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            # Model may have one or multiple logits; assume binary-like -> use sigmoid on first logit
            try:
                prob = torch.sigmoid(logits)[0][0].item()
            except Exception:
                # fallback: softmax over logits
                probs = torch.softmax(logits, dim=-1)[0].cpu().tolist()
                prob = max(probs)
            return {
                'probability': float(prob),
                'raw_logits': logits[0].cpu().tolist()
            }

