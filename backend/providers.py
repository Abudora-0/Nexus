"""
providers.py
------------
Pluggable AI backend. Chat and embeddings are chosen independently:

  CHAT_PROVIDER   "ollama" | "gemini" | "groq"
  EMBED_PROVIDER  "ollama" | "gemini"

Both default to LLM_PROVIDER (a single knob for local dev, where you want
everything on "ollama"). The hosted demo runs chat on Groq (fast, free tier)
and embeddings on Gemini (Groq has no embeddings API).

The rest of the app only touches these two coroutines:

    embed_batch(texts)              -> list[list[float]]
    stream_chat(system, user, ...)  -> async iterator of text chunks
"""

import os
import json
import math
from typing import AsyncIterator

import httpx
from dotenv import load_dotenv

load_dotenv()

_BOTH = os.getenv("LLM_PROVIDER", "ollama").lower()
CHAT_PROVIDER = os.getenv("CHAT_PROVIDER", _BOTH).lower()
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", _BOTH).lower()

# Model names default sensibly per provider so a minimal .env still works.
_DEFAULT_CHAT = {
    "ollama": "qwen2.5:1.5b",
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
}
_DEFAULT_EMBED = {"ollama": "nomic-embed-text", "gemini": "text-embedding-004"}
CHAT_MODEL = os.getenv("CHAT_MODEL", _DEFAULT_CHAT.get(CHAT_PROVIDER, "qwen2.5:1.5b"))
EMBED_MODEL = os.getenv("EMBED_MODEL", _DEFAULT_EMBED.get(EMBED_PROVIDER, "nomic-embed-text"))

# Vector dimension the LanceDB table is built for. Both embed defaults emit 768.
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
KEEP_ALIVE = "30m"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)


def _l2_normalize(vec: list[float]) -> list[float]:
    """Scale a vector to unit length. Keeps L2 nearest-neighbor search in
    LanceDB behaving like cosine similarity regardless of which embedding
    model produced the vector."""
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


# Embeddings

async def embed_batch(texts: list[str]) -> list[list[float]]:
    if EMBED_PROVIDER == "gemini":
        return await _gemini_embed(texts)
    return await _ollama_embed(texts)


async def _ollama_embed(texts: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": texts, "keep_alive": KEEP_ALIVE},
        )
        r.raise_for_status()
        return [_l2_normalize(v) for v in r.json()["embeddings"]]


async def _gemini_embed(texts: list[str]) -> list[list[float]]:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    req = {
        "requests": [
            {"model": f"models/{EMBED_MODEL}", "content": {"parts": [{"text": t}]}}
            for t in texts
        ]
    }
    # Newer embedding models support Matryoshka truncation; ask for our dim.
    if "gemini-embedding" in EMBED_MODEL:
        for r in req["requests"]:
            r["outputDimensionality"] = EMBED_DIM
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{GEMINI_BASE}/models/{EMBED_MODEL}:batchEmbedContents",
            params={"key": GEMINI_API_KEY},
            json=req,
        )
        resp.raise_for_status()
        return [_l2_normalize(e["values"]) for e in resp.json()["embeddings"]]


# Chat (streaming)

async def stream_chat(
    system: str,
    user: str,
    *,
    max_tokens: int = 512,
    temperature: float = 0.2,
) -> AsyncIterator[str]:
    """Yield the model's answer as it is generated, chunk by chunk."""
    if CHAT_PROVIDER == "gemini":
        gen = _gemini_stream(system, user, max_tokens, temperature)
    elif CHAT_PROVIDER == "groq":
        gen = _openai_chat_stream(GROQ_BASE, GROQ_API_KEY, "GROQ_API_KEY",
                                  system, user, max_tokens, temperature)
    else:
        gen = _ollama_stream(system, user, max_tokens, temperature)
    async for chunk in gen:
        yield chunk


async def _ollama_stream(system, user, max_tokens, temperature):
    prompt = (
        f"<|system|>\n{system}\n<|end|>\n"
        f"<|user|>\n{user}\n<|end|>\n"
        f"<|assistant|>\n"
    )
    async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": CHAT_MODEL,
                "prompt": prompt,
                "stream": True,
                "keep_alive": KEEP_ALIVE,
                "options": {
                    "num_predict": max_tokens,
                    "num_ctx": 2048,
                    "temperature": temperature,
                    "top_p": 0.9,
                    "top_k": 20,
                },
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if token := data.get("response", ""):
                    yield token
                if data.get("done"):
                    break


async def _openai_chat_stream(base, key, key_name, system, user, max_tokens, temperature):
    """Streaming chat over any OpenAI-compatible /chat/completions endpoint (Groq)."""
    if not key:
        raise RuntimeError(f"{key_name} is not set.")
    body = {
        "model": CHAT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 0.9,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    delta = json.loads(payload)["choices"][0].get("delta", {})
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue
                if content := delta.get("content"):
                    yield content


async def _gemini_stream(system, user, max_tokens, temperature):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    body = {
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "systemInstruction": {"parts": [{"text": system}]},
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "topP": 0.9,
        },
    }
    async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{GEMINI_BASE}/models/{CHAT_MODEL}:streamGenerateContent",
            params={"key": GEMINI_API_KEY, "alt": "sse"},
            json=body,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    data = json.loads(payload)
                    parts = (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [])
                    )
                except (json.JSONDecodeError, IndexError):
                    continue
                for p in parts:
                    if text := p.get("text", ""):
                        yield text


# Warmup (local models only)

async def warmup() -> None:
    """Pre-load local models into RAM. No-op for hosted providers."""
    async with httpx.AsyncClient(timeout=120) as client:
        if CHAT_PROVIDER == "ollama":
            try:
                r = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json={
                    "model": CHAT_MODEL, "prompt": "hi", "stream": False,
                    "keep_alive": KEEP_ALIVE, "options": {"num_predict": 1}})
                r.raise_for_status()
            except Exception:
                pass
        if EMBED_PROVIDER == "ollama":
            try:
                r = await client.post(f"{OLLAMA_BASE_URL}/api/embed", json={
                    "model": EMBED_MODEL, "input": "hi", "keep_alive": KEEP_ALIVE})
                r.raise_for_status()
            except Exception:
                pass
