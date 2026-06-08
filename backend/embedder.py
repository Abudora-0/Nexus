"""
embedder.py
-----------
Talks to the Ollama /api/embed endpoint to turn text into vectors.

KEY CONCEPT: An embedding is just a list of ~768 floats that captures
the *meaning* of a piece of text. Similar sentences end up with similar
vectors — that's what lets us do semantic search later.
"""

import httpx
import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")


async def embed_text(text: str) -> list[float]:
    """Get the embedding vector for a single string."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": text},
        )
        response.raise_for_status()
        data = response.json()
        # Ollama returns {"embeddings": [[...floats...]]}
        return data["embeddings"][0]


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple strings in one API call (more efficient)."""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": texts},
        )
        response.raise_for_status()
        data = response.json()
        return data["embeddings"]
