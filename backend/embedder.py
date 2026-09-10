"""
embedder.py
-----------
Turns text into embedding vectors.

KEY CONCEPT: An embedding is just a list of ~768 floats that captures
the *meaning* of a piece of text. Similar sentences end up with similar
vectors, which is what lets us do semantic search later.

The actual call goes through providers.py, which routes to either a local
Ollama model or the hosted Gemini API depending on LLM_PROVIDER.
"""

from providers import embed_batch as _embed_batch


async def embed_text(text: str) -> list[float]:
    """Get the embedding vector for a single string."""
    return (await _embed_batch([text]))[0]


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple strings in one call (more efficient)."""
    return await _embed_batch(texts)
