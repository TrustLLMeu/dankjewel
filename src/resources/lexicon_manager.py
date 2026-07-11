"""Lexicon and resource management for rule-based evaluation.

Loads per-language keyword lexicons from YAML files in the lexicons/
directory. Validates structure and falls back to English on missing files.
"""

import logging
from pathlib import Path
from typing import Dict, Set

import yaml

logger = logging.getLogger(__name__)

# Every lexicon YAML must contain these keys (each a list of strings).
REQUIRED_KEYS = frozenset({
    "politeness_cues",
    "rudeness_cues",
    "formal_markers",
    "informal_markers",
    "modal_verbs",
    "uncertainty_cues",
})

LEXICONS_DIR = Path(__file__).resolve().parent / "lexicons"


class LexiconManager:
    """Manage per-language keyword lexicons for Prong 2 dimensions.

    Usage::

        from src.resources.lexicon_manager import lexicon_manager
        cues = lexicon_manager.get_keywords("politeness_cues", lang="nl")
    """

    def __init__(self, lexicons_dir: Path = LEXICONS_DIR):
        self._dir = lexicons_dir
        self._cache: Dict[str, dict] = {}

    # ── public API ──────────────────────────────────────────────────

    def load_language(self, lang: str) -> dict:
        """Load and validate a lexicon for *lang*, with English fallback."""
        if lang in self._cache:
            return self._cache[lang]

        yaml_path = self._dir / f"{lang}.yaml"
        try:
            with open(yaml_path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except FileNotFoundError:
            if lang == "en":
                raise  # English must always exist
            logger.warning(
                "Lexicon file not found for lang='%s' (%s); falling back to English.",
                lang, yaml_path,
            )
            return self.load_language("en")

        if not isinstance(data, dict):
            logger.warning(
                "Lexicon for lang='%s' is not a YAML mapping (got %s); falling back to English.",
                lang, type(data).__name__,
            )
            if lang == "en":
                data = {}
            else:
                return self.load_language("en")

        data = self._validate(data, lang)
        self._cache[lang] = data
        return data

    def get_keywords(self, dimension_key: str, lang: str = "en") -> Set[str]:
        """Return the keyword set for *dimension_key* in the given language."""
        data = self.load_language(lang)
        return set(data.get(dimension_key, []))

    def clear_cache(self) -> None:
        """Clear the in-memory cache (useful for testing)."""
        self._cache.clear()

    # ── validation ──────────────────────────────────────────────────

    def _validate(self, data: dict, lang: str) -> dict:
        """Validate lexicon *data* in-place, logging warnings for problems.

        Returns the (potentially patched) data dict — missing keys are set to
        empty lists so callers always get something usable.
        """
        for key in REQUIRED_KEYS:
            if key not in data:
                logger.warning(
                    "Lexicon '%s': missing required key '%s'; defaulting to empty list.",
                    lang, key,
                )
                data[key] = []
                continue

            value = data[key]
            if not isinstance(value, list):
                logger.warning(
                    "Lexicon '%s': key '%s' should be a list, got %s; defaulting to empty list.",
                    lang, key, type(value).__name__,
                )
                data[key] = []
                continue

            # Check each item is a string
            cleaned = []
            for i, item in enumerate(value):
                if not isinstance(item, str):
                    logger.warning(
                        "Lexicon '%s': key '%s'[%d] is not a string (got %s); skipping.",
                        lang, key, i, type(item).__name__,
                    )
                else:
                    cleaned.append(item)
            data[key] = cleaned

        return data


# Module-level singleton — dimensions share this instance.
lexicon_manager = LexiconManager()

