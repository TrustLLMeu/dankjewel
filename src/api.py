"""FastAPI server: vLLM text generation + Instant Evaluator.

Provides REST endpoints for:
  - Model listing (from vLLM, or from a remote OpenAI-compatible host)
  - Text generation (batch and SSE streaming), via a local vLLM server OR
    a remote OpenAI-compatible host (bring your own API key)
  - Text evaluation (via IE pipeline, using HuggingFace models)
  - Combined generate-and-evaluate (the main workflow)
  - Static frontend at /

Backend selection: every generation-related request accepts optional
`backend_type` ("local"|"remote"), `base_url`, and `api_key` fields.
Defaults to "local" (the existing vLLM-only behavior, unchanged). Remote
backends are constructed per-request and never cached — see
src/llm_backends/factory.py for the security rationale.

Start with:
    uvicorn src.api:app --host 0.0.0.0 --port 8080

Requires a running vLLM server for the local backend:
    python -m vllm.entrypoints.openai.api_server \\
        --model <model_name> --port 8000
"""

import json
import os
import re
import time
import logging
import subprocess
from contextlib import asynccontextmanager
from typing import Literal, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from starlette.responses import StreamingResponse

from src.vllm_client import VLLMClient, GenerationResult
from src.vllm_adapter import generation_result_to_intrinsic_data
from src.pipeline import EvaluationPipeline
from src.config import SUPPORTED_LANGUAGES, VLLM_LOGPROBS_K
from src.llm_backends.factory import BackendConfig, build_backend, is_remote

logger = logging.getLogger(__name__)

# Supported Prong 2 / judge language codes. Keeping this a Literal makes
# an unsupported code a 422 instead of a silent English fallback.
LanguageCode = Literal['en', 'da', 'nl', 'fo', 'de', 'is', 'nb', 'nn', 'sv']
assert set(LanguageCode.__args__) == set(SUPPORTED_LANGUAGES)

# ── Configuration ───────────────────────────────────────────────────────────

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000")
VLLM_API_KEY = os.environ.get("VLLM_API_KEY")
API_HOST = os.environ.get("IE_API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("IE_API_PORT", "8080"))

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# ── Shared instances ────────────────────────────────────────────────────────

vllm_client: Optional[VLLMClient] = None
evaluator: Optional[EvaluationPipeline] = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup/shutdown lifecycle for the API server."""
    global vllm_client, evaluator
    vllm_client = VLLMClient(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY)
    evaluator = EvaluationPipeline(enable_prongs=[1, 2, 3, 4])
    logger.info("IE API started — vLLM at %s", VLLM_BASE_URL)
    yield
    if vllm_client:
        await vllm_client.close()


# ── App setup ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Dankjewel Instant Evaluator API",
    description=(
        "Generate text — locally via vLLM, or remotely via any "
        "OpenAI-compatible host (bring your own key) — and evaluate it "
        "with the multi-dimensional Dankjewel Instant Evaluator pipeline."
    ),
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ───────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="The input prompt for the LLM")
    model: str = Field(..., description="Model ID (from /models endpoint)")
    max_tokens: int = Field(2048, ge=1, le=32768, description="Reasoning models may need several thousand tokens for hidden chain-of-thought before any visible answer")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    top_p: float = Field(1.0, ge=0.0, le=1.0)
    repetition_penalty: float = Field(1.0, ge=1.0, le=2.0)
    frequency_penalty: float = Field(0.0, ge=0.0, le=2.0)
    language: LanguageCode = Field("en", description="Language code for Prong 2 lexicons and judge routing (en, da, nl, fo, de, is, nb, nn, sv)")
    logprobs_k: int = Field(20, ge=0, le=20, description="Top-k logprobs per token; 0 disables them (Prong 4 then stays unknown). Defaults to VLLM_LOGPROBS_K.")
    backend_type: str = Field("local", description="'local' (vLLM) or 'remote' (OpenAI-compatible, bring-your-own-key)")
    base_url: Optional[str] = Field(None, description="Base URL for a remote backend (required if backend_type='remote')")
    api_key: Optional[str] = Field(None, description="API key for a remote backend. Never stored server-side.")

    def backend_config(self) -> BackendConfig:
        return BackendConfig(backend_type=self.backend_type, base_url=self.base_url, api_key=self.api_key)

class EvaluateRequest(BaseModel):
    prompt: str = Field("", description="The original prompt (for relevance scoring)")
    text: str = Field(..., min_length=1, description="The text to evaluate; must contain at least one non-whitespace character")
    language: LanguageCode = Field("en", description="Language code for Prong 2 lexicons and judge routing (en, da, nl, fo, de, is, nb, nn, sv)")
    tiny_judge: bool = Field(False, description="Opt in: also run the local tiny-LLM judge on Relevance, routed by language (English: Qwen2.5-0.5B; other languages: Qwen2.5-1.5B via DANKJEWEL_JUDGE_BASE_URL_NONEN/DANKJEWEL_JUDGE_MODEL_NONEN), adding a dual llm_value/rationale track to that dimension's metadata. Default off: embeddings baseline only, identical behavior and latency.")
    llm_extract: bool = Field(False, description="Opt in: also run the local 1.5B claim-extraction track (Qwen2.5-1.5B, [CLAIMS] task) on Prong 3, merging decontextualized LLM atomic claims (claim.source 'llm'/'both') with the spaCy triples in claim_details. Default off: spaCy-only extraction, identical behavior and latency.")
    llm_verify: bool = Field(False, description="Opt in: also run the MiniCheck-Flan-T5-Large (770M) NLI verifier on Prong 3 FactualAccuracy's five-way relation track — KB-unknown claims are scored against the subject's formatted KB facts (relation/relation_counts/verifier_score in metadata; confirmed/denied/partially_supported/conflated labels). Default off: rule-based five-way labels only, no model load. First run loads the model (~30 s).")
    llm_admit: bool = Field(False, description="Opt in: run the local 1.5B admission classifier ([ADMIT] task) over the admitted Prong 3 claims and drop those it classifies as non-claims (commentary, advice, definitions). Metadata records llm_admit_dropped/llm_admit_unknown; claims are kept when the model is unavailable. Default off: deterministic gates only.")

    @field_validator('text')
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        """Reject whitespace-only input at the API boundary."""
        if not value.strip():
            raise ValueError('text must not be blank')
        return value

class GenerateAndEvaluateRequest(BaseModel):
    prompt: str = Field(..., description="The input prompt for the LLM")
    model: str = Field(..., description="Model ID (from /models endpoint)")
    max_tokens: int = Field(2048, ge=1, le=32768, description="Reasoning models may need several thousand tokens for hidden chain-of-thought before any visible answer")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    top_p: float = Field(1.0, ge=0.0, le=1.0)
    repetition_penalty: float = Field(1.0, ge=1.0, le=2.0)
    frequency_penalty: float = Field(0.0, ge=0.0, le=2.0)
    language: LanguageCode = Field("en", description="Language code for Prong 2 lexicons and judge routing (en, da, nl, fo, de, is, nb, nn, sv)")
    logprobs_k: int = Field(20, ge=0, le=20, description="Top-k logprobs per token; 0 disables them (Prong 4 then stays unknown). Defaults to VLLM_LOGPROBS_K.")
    backend_type: str = Field("local", description="'local' (vLLM) or 'remote' (OpenAI-compatible, bring-your-own-key)")
    base_url: Optional[str] = Field(None, description="Base URL for a remote backend (required if backend_type='remote')")
    api_key: Optional[str] = Field(None, description="API key for a remote backend. Never stored server-side.")

    def backend_config(self) -> BackendConfig:
        return BackendConfig(backend_type=self.backend_type, base_url=self.base_url, api_key=self.api_key)

class ModelsRequest(BaseModel):
    backend_type: str = Field("local", description="'local' (vLLM) or 'remote' (OpenAI-compatible)")
    base_url: Optional[str] = Field(None, description="Base URL for a remote backend (required if backend_type='remote')")
    api_key: Optional[str] = Field(None, description="API key for a remote backend. Never stored server-side.")


async def _resolve_backend(cfg: BackendConfig):
    """Return (backend, must_close).

    must_close=True for per-request remote backends, which are never cached
    or shared (see src/llm_backends/factory.py). must_close=False for the
    shared local vLLM backend managed by the app lifespan.
    """
    try:
        if is_remote(cfg):
            return build_backend(cfg, vllm_client), True
        return vllm_client, False
    except ValueError as e:
        # e.g. backend_type='remote' with no base_url — a client error, not
        # a network failure, so 422 rather than 502.
        raise HTTPException(status_code=422, detail=str(e))



# ── Frontend ────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve the HTML5 control panel."""
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "Frontend not found. Place index.html in frontend/"}


# ── API Endpoints ───────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check — also checks if vLLM is reachable."""
    vllm_ok = await vllm_client.health_check() if vllm_client else False
    return {
        "status": "ok",
        "vllm_connected": vllm_ok,
        "vllm_url": VLLM_BASE_URL,
        "logprobs_k": VLLM_LOGPROBS_K,
    }


@app.get("/models")
async def list_models():
    """List available models from the local vLLM server (backward-compatible shortcut)."""
    try:
        models = await vllm_client.list_models()
        return {"models": models}
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach vLLM server at {VLLM_BASE_URL}: {e}"
        )


@app.post("/models")
async def list_models_for_backend(req: ModelsRequest):
    """List available models for any backend (local or remote, bring-your-own-key)."""
    cfg = BackendConfig(backend_type=req.backend_type, base_url=req.base_url, api_key=req.api_key)
    backend, must_close = await _resolve_backend(cfg)
    try:
        models = await backend.list_models()
        return {"models": models}
    except Exception as e:
        target = req.base_url if req.backend_type == "remote" else VLLM_BASE_URL
        raise HTTPException(status_code=502, detail=f"Cannot reach backend at {target}: {e}")
    finally:
        if must_close:
            await backend.close()


@app.post("/generate")
async def generate(req: GenerateRequest):
    """Generate text via the selected backend (local vLLM or remote) — no evaluation."""
    backend, must_close = await _resolve_backend(req.backend_config())
    try:
        result = await backend.generate(
            prompt=req.prompt,
            model=req.model,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
            repetition_penalty=req.repetition_penalty,
            frequency_penalty=req.frequency_penalty,
            logprobs=(req.logprobs_k or None),
        )
        return {
            "text": result.text,
            "model": result.model,
            "finish_reason": result.finish_reason,
            "generation_time_ms": result.generation_time_ms,
            "num_tokens": len(result.tokens) if result.tokens else 0,
        }
    except Exception as e:
        target = req.base_url if req.backend_type == "remote" else VLLM_BASE_URL
        raise HTTPException(status_code=502, detail=f"Generation failed ({target}): {e}")
    finally:
        if must_close:
            await backend.close()


@app.post("/generate/stream")
async def generate_stream(req: GenerateRequest):
    """Stream text generation via SSE. Each event is a JSON chunk with a token.

    Frontend connects with EventSource or fetch() and reads the stream.
    After the final token, evaluation runs and a final 'evaluation' event is sent.
    Works with either backend (local vLLM or remote, bring-your-own-key).
    """
    backend, must_close = await _resolve_backend(req.backend_config())

    async def event_stream():
        accumulated_tokens = []
        accumulated_logprobs = []
        accumulated_top_logprobs = []
        reasoning_chars = 0
        start_time = time.perf_counter()

        try:
            async for chunk in backend.generate_stream(
                prompt=req.prompt,
                model=req.model,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                top_p=req.top_p,
                repetition_penalty=req.repetition_penalty,
                frequency_penalty=req.frequency_penalty,
                logprobs=(req.logprobs_k or None),
            ):
                # Some hosted "reasoning" models (gpt-oss, DeepSeek-R1 style,
                # etc.) stream hidden chain-of-thought via a separate field
                # before any visible answer. Forward it as its own event type
                # so the frontend can show progress instead of looking stuck
                # on an empty output. It is NOT included in the evaluated text.
                reasoning_token = chunk.get("reasoning_token")
                if reasoning_token:
                    reasoning_chars += len(reasoning_token)
                    reasoning_data = json.dumps({
                        "type": "reasoning",
                        "token": reasoning_token,
                    })
                    yield f"data: {reasoning_data}\n\n"

                token = chunk.get("token", "")
                if token:
                    accumulated_tokens.append(token)
                    lp = chunk.get("token_logprob")
                    if lp is not None:
                        accumulated_logprobs.append(lp)
                    tlp = chunk.get("top_logprobs")
                    if tlp is not None:
                        accumulated_top_logprobs.append(tlp)

                # Send token event
                event_data = json.dumps({
                    "type": "token",
                    "token": token,
                    "finish_reason": chunk.get("finish_reason"),
                    "done": chunk.get("done", False),
                })
                yield f"data: {event_data}\n\n"

                if chunk.get("done"):
                    break

        except Exception as e:
            error_data = json.dumps({"type": "error", "detail": str(e)})
            yield f"data: {error_data}\n\n"
            if must_close:
                await backend.close()
            return

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        full_text = "".join(accumulated_tokens).strip()

        # Build GenerationResult for the adapter
        gen_result = GenerationResult(
            text=full_text,
            model=req.model,
            finish_reason="stop",
            generation_time_ms=elapsed_ms,
            prompt=req.prompt,
            token_logprobs=accumulated_logprobs or None,
            tokens=accumulated_tokens or None,
            top_logprobs=accumulated_top_logprobs or None,
        )

        # Send generation metadata
        gen_dict = gen_result.to_dict()
        gen_dict["reasoning_chars"] = reasoning_chars
        gen_dict["logprobs_k"] = req.logprobs_k
        gen_dict["logprobs_reason"] = (
            "ok" if gen_result.token_logprobs else
            ("disabled" if req.logprobs_k == 0 else "backend_returned_none"))
        gen_data = json.dumps({"type": "generation", "data": gen_dict})
        yield f"data: {gen_data}\n\n"

        if not full_text.strip():
            # No visible answer to evaluate. Tell the client explicitly
            # and stop; the old path evaluated an empty string.
            empty_data = json.dumps({
                "type": "empty_output",
                "detail": "The model produced no visible answer within the token budget.",
            })
            yield f"data: {empty_data}\n\n"
            yield "data: [DONE]\n\n"
            if must_close:
                await backend.close()
            return

        # Run evaluation
        try:
            intrinsic_data = generation_result_to_intrinsic_data(gen_result)
            eval_result = evaluator.evaluate(
                text=full_text,
                prompt=req.prompt,
                intrinsic_data=intrinsic_data,
                lang=req.language,
            )
            eval_data = json.dumps({"type": "evaluation", "data": eval_result})
            yield f"data: {eval_data}\n\n"
        except Exception as e:
            error_data = json.dumps({"type": "error", "detail": f"Evaluation failed: {e}"})
            yield f"data: {error_data}\n\n"

        yield "data: [DONE]\n\n"
        if must_close:
            await backend.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/evaluate")
async def evaluate(req: EvaluateRequest):
    """Evaluate arbitrary text — no vLLM needed."""
    if evaluator is None:
        raise HTTPException(status_code=503, detail="Evaluator not initialized.")
    try:
        result = evaluator.evaluate(text=req.text, prompt=req.prompt, lang=req.language,
                                    tiny_judge=req.tiny_judge, llm_extract=req.llm_extract,
                                    llm_verify=req.llm_verify, llm_admit=req.llm_admit)
        return result
    except Exception as e:
        logger.exception("Evaluation failed")
        raise HTTPException(
            status_code=500,
            detail=f"Evaluation failed: {type(e).__name__}: {e}"
        )


@app.post("/generate-and-evaluate")
async def generate_and_evaluate(req: GenerateAndEvaluateRequest):
    """Generate text via the selected backend, then evaluate — the main workflow (non-streaming)."""
    backend, must_close = await _resolve_backend(req.backend_config())
    try:
        gen_result = await backend.generate(
            prompt=req.prompt,
            model=req.model,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
            repetition_penalty=req.repetition_penalty,
            frequency_penalty=req.frequency_penalty,
            logprobs=(req.logprobs_k or None),
        )
    except Exception as e:
        target = req.base_url if req.backend_type == "remote" else VLLM_BASE_URL
        raise HTTPException(status_code=502, detail=f"Generation failed ({target}): {e}")
    finally:
        if must_close:
            await backend.close()

    gen_dict = gen_result.to_dict()
    gen_dict["logprobs_k"] = req.logprobs_k
    gen_dict["logprobs_reason"] = (
        "ok" if gen_result.token_logprobs else
        ("disabled" if req.logprobs_k == 0 else "backend_returned_none"))

    if not gen_result.text.strip():
        # No visible answer: there is nothing to evaluate. Returning
        # evaluation=None keeps a style/prong default from becoming a
        # quality score for an empty completion.
        return {
            "generation": gen_dict,
            "evaluation": None,
            "empty_output": True,
        }

    intrinsic_data = generation_result_to_intrinsic_data(gen_result)

    try:
        eval_result = evaluator.evaluate(
            text=gen_result.text,
            prompt=req.prompt,
            intrinsic_data=intrinsic_data,
            lang=req.language,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {e}")

    return {
        "generation": gen_dict,
        "evaluation": eval_result,
    }


# ── Commit history (Git Historian) ──────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMIT_INDEX = REPO_ROOT / "docs" / "commit-index.md"


def _git(*args: str) -> str:
    """Run one git command in the repo root and return stdout."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError("git executable not found") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("git timed out") from e
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or "").strip()
        raise RuntimeError(f"git failed: {detail}") from e
    return proc.stdout


def _parse_commit_index():
    """Annotations from docs/commit-index.md, keyed by short hash.

    The table supplies date/area/review item; the newest-first sections
    supply why/files/closes/verify. Returns (annotations, open_slices).
    """
    ann: dict[str, dict] = {}
    open_slices = ""
    if not COMMIT_INDEX.exists():
        return ann, open_slices
    text = COMMIT_INDEX.read_text(encoding="utf-8")
    m = re.search(r"\*\*Open slices:\*\* ?(.+)", text)
    if m:
        open_slices = m.group(1).strip()
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        short = cells[1].strip("`")
        if not re.fullmatch(r"[0-9a-f]{7,40}", short):
            continue
        a = ann.setdefault(short, {})
        a.setdefault("date", cells[0])
        a.setdefault("area", cells[2])
        a.setdefault("review_item", cells[4])
    current: Optional[str] = None
    for line in text.splitlines():
        if line.startswith("### "):
            m = re.match(r"^### +`([0-9a-f]{7,40})`", line)
            current = m.group(1) if m else None
            continue
        if line.startswith("## "):
            current = None
            continue
        if current is None:
            continue
        m = re.match(r"^- \*\*(Why|Files|Closes|Verify):\*\* ?(.*)$", line)
        if not m:
            continue
        key = m.group(1).lower()
        val = m.group(2).strip()
        if key == "files":
            tokens = re.findall(r"`([^`]+)`", val)
            val = ", ".join(tokens) if tokens else val
        ann.setdefault(current, {})[key] = val
    return ann, open_slices


def _build_commits_payload() -> dict:
    """git log from the merge-base with master through HEAD, annotated."""
    branch = _git("branch", "--show-current").strip()
    head = _git("rev-parse", "HEAD").strip()
    base = _git("merge-base", "master", "HEAD").strip()
    status = _git("status", "--porcelain")
    tree = "dirty" if any(
        line and not line.startswith("??") for line in status.splitlines()
    ) else "clean"
    meta = _git(
        "log", f"{base}..HEAD", "--format=%x1e%H%x1f%ad%x1f%s%x1f%b", "--date=short"
    )
    names = _git("log", f"{base}..HEAD", "--name-only", "--format=%x1e%H")
    ann, open_slices = _parse_commit_index()
    files_by_hash: dict[str, list] = {}
    for chunk in names.split("\x1e"):
        lines = [l for l in chunk.splitlines() if l.strip()]
        if lines:
            files_by_hash[lines[0].strip()] = lines[1:]
    commits = []
    for chunk in meta.split("\x1e"):
        if "\x1f" not in chunk:
            continue
        full, date, subject, body = chunk.split("\x1f", 3)
        full = full.strip()
        a = ann.get(full[:7], {})
        commits.append({
            "short": full[:7],
            "hash": full,
            "date": a.get("date") or date,
            "subject": subject,
            "body": body.strip(),
            "area": a.get("area") or "unindexed",
            "review_item": a.get("review_item", ""),
            "why": a.get("why", ""),
            "files": files_by_hash.get(full, []),
            "closes": a.get("closes", ""),
            "verify": a.get("verify", ""),
        })
    where = {
        "latest": f"{commits[0]['short']} — {commits[0]['subject']}" if commits else "",
        "open_slices": open_slices,
        "tree": tree,
    }
    return {"branch": branch, "head": head, "where": where, "commits": commits}


@app.get("/commits", include_in_schema=False)
async def serve_commits_page():
    """Serve the browsable commit history page."""
    page = FRONTEND_DIR / "commits.html"
    if page.exists():
        return FileResponse(page)
    return {"message": "Commits page not found. Place commits.html in frontend/"}


@app.get("/api/commits")
async def api_commits():
    """Annotated git log for the current branch (merge-base with master → HEAD)."""
    try:
        return _build_commits_payload()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"git unavailable: {e}")


# ── Static assets ───────────────────────────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── Run directly ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host=API_HOST, port=API_PORT, log_level="info")
