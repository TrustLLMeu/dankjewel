"""Synchronous client for the shared tiny LLM judge.

Talks to the local OpenAI-compatible servers (llama.cpp/vLLM on
Malvik) that host the ≤1.5B judge and claim extractor for the whole
product — task prefixes ("[JUDGE]", "[CLAIMS]", later "[READABILITY]")
instead of one server per dimension. The evaluation
pipeline is synchronous, so this client is sync httpx — do not couple it
to src/vllm_client.py, which is async and serves generation/logprobs.

Configuration (environment, read at construction).

[JUDGE] task:
    DANKJEWEL_JUDGE_BASE_URL    default http://127.0.0.1:18092/v1
    DANKJEWEL_JUDGE_MODEL       default Qwen/Qwen2.5-0.5B-Instruct
    DANKJEWEL_JUDGE_API_KEY     optional; sent as Authorization: Bearer
                                only when set (never hardcoded)
    DANKJEWEL_JUDGE_TIMEOUT_S   default 30 — a slow judge call must be
                                cut off and surfaced as "unknown", not
                                block the evaluate path

[CLAIMS] task (the 0.5B judge fails at claim extraction — it echoes
input sentences verbatim and never resolves pronouns, so claims run on
the 1.5B):
    DANKJEWEL_CLAIMS_BASE_URL    default http://127.0.0.1:18093/v1
    DANKJEWEL_CLAIMS_MODEL       default Qwen/Qwen2.5-1.5B-Instruct
    DANKJEWEL_CLAIMS_API_KEY     optional; falls back to a constructor-
                                 provided key, then to
                                 DANKJEWEL_JUDGE_API_KEY; sent as
                                 Authorization: Bearer only when set
                                 (never hardcoded)
    DANKJEWEL_CLAIMS_TIMEOUT_S   default 30

The client never fabricates a score or a claim: a connection/timeout
failure raises JudgeUnavailableError, and an unparseable reply or a
score outside [0,1] raises JudgeParseError (its ClaimsParseError
subclass for the [CLAIMS] task). Callers translate those into the
dual-output metadata (judge_status "unknown" / "error") and keep the
baseline score.

Tested with:
    httpx==0.28.1
    Python 3.12
"""

import json
import logging
import os
import re
import threading
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:18092/v1"
DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
DEFAULT_TIMEOUT_S = 30.0

CLAIMS_DEFAULT_BASE_URL = "http://127.0.0.1:18093/v1"
CLAIMS_DEFAULT_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
CLAIMS_DEFAULT_TIMEOUT_S = 30.0

# The few-shot prompt verified live against the 0.5B judge on
# 2026-11-14 (relevant→1.0, irrelevant→0.0; the zero-shot variant did
# NOT discriminate). Known limitations: partial answers collapse to
# the 0 anchor, and at temperature 0 a user message that repeats an
# exemplar verbatim echoes that exemplar's score instead of judging —
# judge real text, not the exemplars. Do not rewrite the prompt
# without re-verifying discrimination.
_JUDGE_SYSTEM_PROMPT = (
    "[JUDGE] Rate how relevant the Answer is to the Prompt. "
    "0 = irrelevant, 0.5 = partially relevant, 1 = directly answers. "
    'Reply with ONLY JSON: {"score": 0 to 1, "rationale": at most 40 words}.\n'
    "Examples:\n"
    'Prompt: What is 2+2? Answer: The sum is 4. -> '
    '{"score": 1, "rationale": "Directly answers the arithmetic question."}\n'
    'Prompt: What is 2+2? Answer: Apples grow on trees. -> '
    '{"score": 0, "rationale": "No connection to the arithmetic question."}'
)

# The [CLAIMS] prompt verified live against the 1.5B model on
# 2026-11-14 (pronoun resolution and decomposition work; opinion
# filtering does NOT — opinion claims are kept and verify UNKNOWN
# against the KB, which FactualAccuracy's honest denominator already
# excludes). The 1.5B sometimes drops the comma between adjacent quoted
# array elements ('["a" "b"]'); _parse_claims repairs that. Do not
# rewrite the prompt without re-verifying extraction quality.
_CLAIMS_SYSTEM_PROMPT = (
    "[CLAIMS] Extract atomic, self-contained factual claims from the text. "
    "Rules: (1) resolve pronouns to explicit names; if a referent cannot be "
    "resolved, omit the claim. (2) Each claim is one verifiable statement "
    "with an explicit subject and no pronouns. (3) Skip opinions, "
    "speculation, and pure filler. (4) The output must be valid JSON: a "
    "JSON array of strings, elements separated by commas. Reply with ONLY "
    "a JSON array of strings. Example: Text: France won the 2018 World "
    "Cup. They beat the hosts in the final. -> "
    '["France won the 2018 FIFA World Cup.", "France beat the host nation '
    'in the 2018 World Cup final."] Text with no verifiable facts -> []'
)

_ADMIT_SYSTEM_PROMPT = (
    "[ADMIT] Decide whether the sentence is a checkable factual claim about a "
    "named entity: it must assert something that could be verified against a "
    "knowledge base. Commentary, advice, definitions, opinions, questions and "
    "instructions are not claims. Reply with ONLY the word yes or no. "
    "Examples: 'Oslo is the capital of Norway.' -> yes. "
    "'A false claim is a statement.' -> no. "
    "'Critical thinking is your best defense.' -> no. "
    "'The Earth is flat.' -> yes."
)


class JudgeError(Exception):
    """Base class for tiny-judge failures."""


class JudgeUnavailableError(JudgeError):
    """The judge could not be reached (connection error, timeout, HTTP 4xx/5xx)."""


class JudgeParseError(JudgeError):
    """The judge replied, but not with a usable {"score", "rationale"} JSON object."""


class ClaimsParseError(JudgeParseError):
    """The claims model replied, but not with a usable JSON array of strings."""


def _parse_verdict(content: str) -> dict:
    """Parse the judge reply into {"score": float, "rationale": str}.

    Tolerates a markdown fence or prose around the JSON object, but
    never invents a missing score or rationale: anything unparsable or
    with a score outside [0,1] raises JudgeParseError.
    """
    text = (content or "").strip()
    obj = None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Models sometimes wrap the object in ```json fences``` or a
        # short preamble; use the outermost {...} span, nothing else.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                obj = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                obj = None
    if not isinstance(obj, dict):
        raise JudgeParseError(f"judge reply is not a JSON object: {content[:120]!r}")
    score = obj.get("score")
    rationale = obj.get("rationale")
    # bool is an int subclass — exclude it explicitly.
    if isinstance(score, bool) or not isinstance(score, (int, float)) \
            or not (0.0 <= float(score) <= 1.0):
        raise JudgeParseError(f"judge score missing or out of [0,1]: {score!r}")
    if not isinstance(rationale, str):
        raise JudgeParseError(f"judge rationale missing or not a string: {rationale!r}")
    return {"score": float(score), "rationale": rationale}


def _strip_code_fence(text: str) -> str:
    """Strip a leading/trailing ``` (or ```json) markdown fence, if any."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
    stripped = re.sub(r"\s*```\s*$", "", stripped)
    return stripped.strip()


def _outermost_array_span(text: str) -> Optional[str]:
    """Return the outermost [...] span of `text`, or None when absent."""
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        return text[start:end + 1]
    return None


def _parse_yes_no(content: str) -> Optional[bool]:
    """Parse a yes/no admission reply; None when the reply is unclear.

    The prompt asks for a single word, but the 1.5B occasionally prefixes
    it ("Yes." / "It is a claim: yes"). Look for the first standalone
    yes/no token; anything else is treated as unknown.
    """
    text = _strip_code_fence((content or "").strip()).lower()
    match = re.search(r'\b(yes|no)\b', text)
    if not match:
        return None
    return match.group(1) == 'yes'


def _parse_claims(content: str) -> List[str]:
    """Parse the claims-model reply into a list of atomic claim strings.

    Tolerates a markdown fence, prose around the array, and the missing
    comma between adjacent quoted elements that the 1.5B model sometimes
    drops ('["a" "b"]' — repaired with re.sub(r'"\\s*"', '", "', ...) on
    the array body). Never invents a claim: anything unrecoverable, or
    a reply that is not a JSON array of strings, raises ClaimsParseError.
    """
    text = _strip_code_fence((content or "").strip())
    if not text:
        raise ClaimsParseError("claims reply is empty")
    candidates = [text]
    span = _outermost_array_span(text)
    if span is not None:
        if span != text:
            candidates.append(span)  # prose-wrapped array
        # Missing comma between adjacent quoted elements — only tried
        # after the raw candidates fail, so valid JSON is never touched.
        candidates.append(re.sub(r'"\s*"', '", "', span))
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, list):
            raise ClaimsParseError(
                f"claims reply is not a JSON array: {content[:120]!r}")
        if any(not isinstance(item, str) for item in obj):
            raise ClaimsParseError(
                f"claims array has non-string elements: {content[:120]!r}")
        return [item.strip() for item in obj if item.strip()]
    raise ClaimsParseError(
        f"claims reply is not a JSON array of strings: {content[:120]!r}")


def _env_float(name: str, default: float) -> float:
    """Read a float env var, falling back to the default when unset/invalid."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r, using %s", name, raw, default)
        return default


class LLMJudgeClient:
    """Sync OpenAI-compatible client for the shared tiny judge.

    One client per judge task call site; use `get_shared_judge_client()`
    so later [CLAIMS]/[READABILITY] slices reuse the same instance and
    the same server. Attributes `model_name`/`base_url` are public so
    dimension metadata can disclose which judge produced a score;
    `claims_model_name`/`claims_base_url` are the [CLAIMS] task
    equivalents.

    Constructor arguments configure the [JUDGE] task; the [CLAIMS] task
    reads its own DANKJEWEL_CLAIMS_* environment configuration (see
    module docstring).

    `transport` is an httpx transport override for tests (MockTransport);
    production code leaves it None.
    """

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None,
                 api_key: Optional[str] = None, timeout: Optional[float] = None,
                 transport: Optional[httpx.BaseTransport] = None):
        self.base_url = (base_url or os.environ.get("DANKJEWEL_JUDGE_BASE_URL")
                         or DEFAULT_BASE_URL).rstrip('/')
        self.model_name = model or os.environ.get("DANKJEWEL_JUDGE_MODEL") or DEFAULT_MODEL
        self.api_key = api_key if api_key is not None \
            else (os.environ.get("DANKJEWEL_JUDGE_API_KEY") or None)
        self.timeout = float(timeout if timeout is not None
                             else _env_float("DANKJEWEL_JUDGE_TIMEOUT_S", DEFAULT_TIMEOUT_S))
        # [CLAIMS] task — env-only base URL/model/timeout (separate 1.5B
        # server). Key precedence: the claims env key, then a constructor-
        # provided key (test injection), then the judge env key — one key
        # style works across both servers.
        self.claims_base_url = (os.environ.get("DANKJEWEL_CLAIMS_BASE_URL")
                                or CLAIMS_DEFAULT_BASE_URL).rstrip('/')
        self.claims_model_name = (os.environ.get("DANKJEWEL_CLAIMS_MODEL")
                                  or CLAIMS_DEFAULT_MODEL)
        self.claims_api_key = (os.environ.get("DANKJEWEL_CLAIMS_API_KEY")
                               or api_key
                               or (os.environ.get("DANKJEWEL_JUDGE_API_KEY") or None))
        self.claims_timeout = _env_float("DANKJEWEL_CLAIMS_TIMEOUT_S",
                                         CLAIMS_DEFAULT_TIMEOUT_S)
        self._transport = transport
        self._http: Optional[httpx.Client] = None

    def _get_http(self) -> httpx.Client:
        """Lazily create the sync HTTP client (no connection at construction)."""
        if self._http is None or self._http.is_closed:
            self._http = httpx.Client(timeout=self.timeout, transport=self._transport)
        return self._http

    def judge(self, prompt: str, response: str, task: str = "JUDGE") -> dict:
        """Ask the tiny judge to rate `response` against `prompt`.

        Args:
            prompt: the original prompt (what the response should answer).
            response: the response text to rate.
            task: judge task prefix; only the verified "[JUDGE]" relevance
                prompt exists so far — later slices add their own.

        Returns:
            {"score": float in [0,1], "rationale": str}

        Raises:
            JudgeUnavailableError: connection error, timeout, or HTTP error status.
            JudgeParseError: reply was not usable {"score", "rationale"} JSON.
        """
        if task != "JUDGE":
            # Only the [JUDGE] relevance prompt is verified against the
            # 0.5B model; other tasks must bring their own prompt.
            raise ValueError(f"no verified judge prompt for task {task!r}")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": f"Prompt: {prompt}\nAnswer: {response}"},
            ],
            "temperature": 0.0,  # scoring, not creativity
            "max_tokens": 128,  # JSON with a ≤40-word rationale fits comfortably
        }
        try:
            http = self._get_http()
            resp = http.post(f"{self.base_url}/chat/completions",
                             json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException as e:
            raise JudgeUnavailableError(
                f"judge timed out after {self.timeout}s: {e}") from e
        except httpx.HTTPStatusError as e:
            raise JudgeUnavailableError(
                f"judge returned HTTP {e.response.status_code}") from e
        except httpx.TransportError as e:
            raise JudgeUnavailableError(
                f"cannot reach judge at {self.base_url}: {e}") from e
        except json.JSONDecodeError as e:
            raise JudgeParseError(f"judge returned non-JSON body: {e}") from e
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise JudgeParseError(f"unexpected judge response shape: {e}") from e
        return _parse_verdict(content)

    def claims(self, text: str) -> List[str]:
        """Ask the [CLAIMS] model for atomic claims from `text`.

        One call per paragraph is the caller's job (LLMClaimExtractor);
        this method sends the text as a single "Text: ..." user message
        so cross-sentence pronouns can resolve.

        Args:
            text: the text (typically one paragraph) to decompose.

        Returns:
            List of decontextualized atomic claim strings (may be empty).

        Raises:
            JudgeUnavailableError: connection error, timeout, or HTTP error status.
            ClaimsParseError: reply was not a recoverable JSON array of strings.
        """
        headers = {"Content-Type": "application/json"}
        if self.claims_api_key:
            headers["Authorization"] = f"Bearer {self.claims_api_key}"
        payload = {
            "model": self.claims_model_name,
            "messages": [
                {"role": "system", "content": _CLAIMS_SYSTEM_PROMPT},
                {"role": "user", "content": f"Text: {text}"},
            ],
            "temperature": 0.0,  # extraction, not creativity
            "max_tokens": 300,  # a paragraph of atomic claims as JSON
        }
        try:
            http = self._get_http()
            resp = http.post(f"{self.claims_base_url}/chat/completions",
                             json=payload, headers=headers,
                             timeout=self.claims_timeout)
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException as e:
            raise JudgeUnavailableError(
                f"claims model timed out after {self.claims_timeout}s: {e}") from e
        except httpx.HTTPStatusError as e:
            raise JudgeUnavailableError(
                f"claims model returned HTTP {e.response.status_code}") from e
        except httpx.TransportError as e:
            raise JudgeUnavailableError(
                f"cannot reach claims model at {self.claims_base_url}: {e}") from e
        except json.JSONDecodeError as e:
            raise ClaimsParseError(f"claims model returned non-JSON body: {e}") from e
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise ClaimsParseError(f"unexpected claims response shape: {e}") from e
        return _parse_claims(content)

    def close(self) -> None:
        """Close the underlying HTTP client (idempotent)."""
        if self._http is not None and not self._http.is_closed:
            self._http.close()

    def admit(self, sentence: str) -> Optional[bool]:
        """Ask the [ADMIT] model whether a sentence is a checkable claim.

        Used by the optional LLM admission filter in Prong 3. Returns True
        or False, and None when the model is unreachable or the reply
        cannot be parsed — the caller then keeps the claim (the
        deterministic gates already ran).

        Args:
            sentence: the claim's atomic_text or source sentence.

        Returns:
            True (claim), False (not a claim), or None (unknown).
        """
        headers = {"Content-Type": "application/json"}
        if self.claims_api_key:
            headers["Authorization"] = f"Bearer {self.claims_api_key}"
        payload = {
            "model": self.claims_model_name,
            "messages": [
                {"role": "system", "content": _ADMIT_SYSTEM_PROMPT},
                {"role": "user", "content": f"Sentence: {sentence}"},
            ],
            "temperature": 0.0,
            "max_tokens": 4,
        }
        try:
            http = self._get_http()
            resp = http.post(f"{self.claims_base_url}/chat/completions",
                             json=payload, headers=headers,
                             timeout=self.claims_timeout)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError,
                json.JSONDecodeError):
            return None
        return _parse_yes_no(content)


_shared_client: Optional[LLMJudgeClient] = None
_shared_lock = threading.Lock()


def get_shared_judge_client() -> LLMJudgeClient:
    """Return the process-wide shared judge client, created lazily.

    All judge call sites ([JUDGE] and later [CLAIMS]/[READABILITY]) must
    reuse this one client so the product keeps a single connection pool
    to the single shared judge server.
    """
    global _shared_client
    if _shared_client is None:
        with _shared_lock:
            if _shared_client is None:
                _shared_client = LLMJudgeClient()
    return _shared_client
