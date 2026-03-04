"""Toxicity model wrapper using Hugging Face Transformers for unitary/toxic-bert."""
from typing import Optional


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
            self.device = 'cuda' if (hasattr(__import__('torch'), 'cuda') and __import__('torch').cuda.is_available()) else 'cpu'
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

