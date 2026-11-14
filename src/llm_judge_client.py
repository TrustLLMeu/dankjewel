"""Synchronous client for the shared tiny LLM judge.

Talks to the single local OpenAI-compatible server (llama.cpp/vLLM on
Malvik) that hosts the ≤1.5B judge for the whole product — one process,
one client per interpreter, task prefixes ("[JUDGE]", later "[CLAIMS]"
and "[READABILITY]") instead of one server per dimension. The evaluation
pipeline is synchronous, so this client is sync httpx — do not couple it
to src/vllm_client.py, which is async and serves generation/logprobs.

Configuration (environment, read at construction):
    DANKJEWEL_JUDGE_BASE_URL    default http://127.0.0.1:18092/v1
    DANKJEWEL_JUDGE_MODEL       default Qwen/Qwen2.5-0.5B-Instruct
    DANKJEWEL_JUDGE_API_KEY     optional; sent as Authorization: Bearer
                                only when set (never hardcoded)
    DANKJEWEL_JUDGE_TIMEOUT_S   default 30 — a slow judge call must be
                                cut off and surfaced as "unknown", not
                                block the evaluate path

The client never fabricates a score: a connection/timeout failure raises
JudgeUnavailableError, and an unparseable reply or a score outside [0,1]
raises JudgeParseError. Callers translate those into the dual-output
metadata (judge_status "unknown" / "error") and keep the baseline score.

Tested with:
    httpx==0.28.1
    Python 3.12
"""

import json
import logging
import os
import threading
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:18092/v1"
DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
DEFAULT_TIMEOUT_S = 30.0

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


class JudgeError(Exception):
    """Base class for tiny-judge failures."""


class JudgeUnavailableError(JudgeError):
    """The judge could not be reached (connection error, timeout, HTTP 4xx/5xx)."""


class JudgeParseError(JudgeError):
    """The judge replied, but not with a usable {"score", "rationale"} JSON object."""


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
    dimension metadata can disclose which judge produced a score.

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

    def close(self) -> None:
        """Close the underlying HTTP client (idempotent)."""
        if self._http is not None and not self._http.is_closed:
            self._http.close()


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
