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
import time
import logging
from contextlib import asynccontextmanager
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from src.vllm_client import VLLMClient, GenerationResult
from src.vllm_adapter import generation_result_to_intrinsic_data
from src.pipeline import EvaluationPipeline
from src.config import VLLM_LOGPROBS_K
from src.llm_backends.factory import BackendConfig, build_backend, is_remote

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────────────────

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000")
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
    vllm_client = VLLMClient(base_url=VLLM_BASE_URL)
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
    language: str = Field("en", description="Language code for Prong 2 lexicons (e.g. en, nl, da)")
    backend_type: str = Field("local", description="'local' (vLLM) or 'remote' (OpenAI-compatible, bring-your-own-key)")
    base_url: Optional[str] = Field(None, description="Base URL for a remote backend (required if backend_type='remote')")
    api_key: Optional[str] = Field(None, description="API key for a remote backend. Never stored server-side.")

    def backend_config(self) -> BackendConfig:
        return BackendConfig(backend_type=self.backend_type, base_url=self.base_url, api_key=self.api_key)

class EvaluateRequest(BaseModel):
    prompt: str = Field("", description="The original prompt (for relevance scoring)")
    text: str = Field(..., description="The text to evaluate")
    language: str = Field("en", description="Language code for Prong 2 lexicons (e.g. en, nl, da)")

class GenerateAndEvaluateRequest(BaseModel):
    prompt: str = Field(..., description="The input prompt for the LLM")
    model: str = Field(..., description="Model ID (from /models endpoint)")
    max_tokens: int = Field(2048, ge=1, le=32768, description="Reasoning models may need several thousand tokens for hidden chain-of-thought before any visible answer")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    top_p: float = Field(1.0, ge=0.0, le=1.0)
    repetition_penalty: float = Field(1.0, ge=1.0, le=2.0)
    frequency_penalty: float = Field(0.0, ge=0.0, le=2.0)
    language: str = Field("en", description="Language code for Prong 2 lexicons (e.g. en, nl, da)")
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
            logprobs=VLLM_LOGPROBS_K,
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
                logprobs=VLLM_LOGPROBS_K,
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
        gen_data = json.dumps({"type": "generation", "data": gen_dict})
        yield f"data: {gen_data}\n\n"

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
        result = evaluator.evaluate(text=req.text, prompt=req.prompt, lang=req.language)
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
            logprobs=VLLM_LOGPROBS_K,
        )
    except Exception as e:
        target = req.base_url if req.backend_type == "remote" else VLLM_BASE_URL
        raise HTTPException(status_code=502, detail=f"Generation failed ({target}): {e}")
    finally:
        if must_close:
            await backend.close()

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
        "generation": gen_result.to_dict(),
        "evaluation": eval_result,
    }


# ── Static assets ───────────────────────────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── Run directly ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host=API_HOST, port=API_PORT, log_level="info")
