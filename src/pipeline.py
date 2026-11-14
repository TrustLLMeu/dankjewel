"""Main evaluation pipeline."""

import json
from typing import List, Optional
from src import config
from src.llm_judge_client import LLMJudgeClient
from src.prongs import Prong1LLMAsJudge, Prong2RuleBased, Prong3Extraction, Prong4Intrinsic
from src.aggregation.aggregator import ScoreAggregator


class EvaluationPipeline:
    """Main pipeline for multi-dimensional text evaluation."""

    def __init__(self, enable_prongs: List[int] = None, judge: Optional[LLMJudgeClient] = None):
        """
        Initialize the evaluation pipeline.

        Args:
            enable_prongs: List of prong numbers to enable (1-4). Defaults to all.
            judge: Tiny-judge client for the optional LLM track (dual
                output). None (the default) lazily uses the process-wide
                shared client; tests can inject a stub.
        """
        if enable_prongs is None:
            enable_prongs = [1, 2, 3, 4]

        self.prongs = {}
        self.aggregator = ScoreAggregator()

        if 1 in enable_prongs:
            self.prongs['Prong 1'] = Prong1LLMAsJudge(judge=judge)
        if 2 in enable_prongs:
            self.prongs['Prong 2'] = Prong2RuleBased()
        if 3 in enable_prongs:
            self.prongs['Prong 3'] = Prong3Extraction(wikidata_db_path=config.WIKIDATA_DB_PATH)
        if 4 in enable_prongs:
            self.prongs['Prong 4'] = Prong4Intrinsic()

    def evaluate(self, text: str, prompt: str = None, intrinsic_data=None, lang: str = "en",
                 tiny_judge: bool = False, llm_extract: bool = False,
                 llm_verify: bool = False) -> dict:
        """
        Evaluate text across all enabled prongs.

        Args:
            text: The text to evaluate
            prompt: Optional prompt/query that generated the text (used by Prong 1 for relevance)
            intrinsic_data: Optional IntrinsicData from vLLM for Prong 4.
                           If None, Prong 4 dimensions are returned with
                           status="unknown" (display-only placeholders,
                           excluded from aggregation).
            lang: Language code for Prong 2 lexicon selection (default: "en").
            tiny_judge: Opt in to the tiny-LLM judge track on Prong 1
                Relevance (dual output in that dimension's metadata).
                Default False: embeddings baseline only, unchanged latency.
            llm_extract: Opt in to the LLM claim-extraction track on
                Prong 3 (dual output: spaCy claims merged with
                decontextualized LLM atomic claims, claim.source/
                atomic_text in claim_details). Default False: spaCy-only
                extraction, identical behavior.
            llm_verify: Opt in to the MiniCheck NLI verifier on Prong 3
                FactualAccuracy's five-way relation track (dual output:
                relation/relation_counts/verifier_score in metadata;
                the binary value math is unchanged). Default False:
                rule-based five-way labels only, no model load.

        Returns:
            Dictionary containing all prong results and aggregated scores
        """
        results = []

        for prong_name, prong in self.prongs.items():
            try:
                if prong_name == 'Prong 4':
                    result = prong.evaluate(text, intrinsic_data=intrinsic_data)
                elif prong_name == 'Prong 1':
                    # Prong 1 uses prompt for relevance scoring
                    result = prong.evaluate(text, prompt=prompt, tiny_judge=tiny_judge)
                elif prong_name == 'Prong 2':
                    result = prong.evaluate(text, lang=lang)
                elif prong_name == 'Prong 3':
                    result = prong.evaluate(text, llm_extract=llm_extract,
                                            llm_verify=llm_verify)
                else:
                    result = prong.evaluate(text)
                results.append(result)
            except Exception as e:
                print(f"Error in {prong_name}: {e}")

        # Aggregate results
        aggregated = self.aggregator.aggregate_prongs(results)

        # Build final output. `metadata.prong1_backend` records which
        # Prong 1 implementation produced the scores — the default
        # embeddings + toxic-bert backend ("embeddings"), never a
        # generative LLM judge.
        output = {
            'text_length': len(text),
            'prong_results': [r.to_dict() for r in results],
            'aggregated_scores': aggregated
        }
        if 'Prong 1' in self.prongs:
            output['metadata'] = {'prong1_backend': 'embeddings'}

        return output

    def evaluate_to_json(self, text: str, prompt: str = None, intrinsic_data=None, lang: str = "en",
                         tiny_judge: bool = False, llm_extract: bool = False,
                         llm_verify: bool = False) -> str:
        """
        Evaluate text and return results as JSON string.

        Args:
            text: The text to evaluate
            prompt: Optional prompt/query that generated the text
            intrinsic_data: Optional IntrinsicData from vLLM for Prong 4
            lang: Language code for Prong 2 lexicon selection (default: "en").
            tiny_judge: Opt in to the tiny-LLM judge track on Prong 1
                Relevance (dual output). Default False.
            llm_extract: Opt in to the LLM claim-extraction track on
                Prong 3 (dual output). Default False.
            llm_verify: Opt in to the MiniCheck NLI verifier track on
                Prong 3 (dual output). Default False.

        Returns:
            JSON string of evaluation results
        """
        results = self.evaluate(text, prompt=prompt, intrinsic_data=intrinsic_data, lang=lang,
                                tiny_judge=tiny_judge, llm_extract=llm_extract,
                                llm_verify=llm_verify)
        return json.dumps(results, indent=2)

