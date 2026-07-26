"""
ingestor.py: Document ingestion pipeline
  1. Extract text from PDF/.txt
  2. Split into sentence-aware chunks (smarter than fixed-size)
  3. Embed in parallel batches
  4. Store in LanceDB
"""

import pdfplumber
import hashlib
import re
import asyncio
from embedder import embed_batch
from vectorstore import add_chunks


def extract_text(file_bytes: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        import io
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(pages)
    return file_bytes.decode("utf-8", errors="ignore")


def chunk_text(text: str, target_size: int = 800, overlap: int = 80) -> list[str]:
    """
    Sentence-aware chunking: split on sentence boundaries so chunks
    don't cut mid-sentence. Larger chunks (800 chars) = fewer API calls
    = faster upload, while still giving the LLM enough context.
    """
    # Normalize whitespace
    text = re.sub(r'\n{3,}', '\n\n', text.strip())

    # Split into sentences (rough but effective)
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks, current, current_len = [], [], 0

    for sentence in sentences:
        slen = len(sentence)
        if current_len + slen > target_size and current:
            chunk = " ".join(current).strip()
            if len(chunk) > 30:
                chunks.append(chunk)
            # Keep last few chars as overlap
            overlap_text = chunk[-overlap:] if len(chunk) > overlap else chunk
            current = [overlap_text, sentence]
            current_len = len(overlap_text) + slen
        else:
            current.append(sentence)
            current_len += slen

    if current:
        chunk = " ".join(current).strip()
        if len(chunk) > 30:
            chunks.append(chunk)

    return chunks


async def embed_in_batches(chunks: list[str], batch_size: int = 16) -> list[list[float]]:
    """
    Split chunks into batches and embed them. Larger batches = fewer
    round trips to Ollama = faster overall.
    """
    all_vectors = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        vectors = await embed_batch(batch)
        all_vectors.extend(vectors)
    return all_vectors


def make_doc_id(filename: str, file_bytes: bytes) -> str:
    content_hash = hashlib.md5(file_bytes).hexdigest()[:8]
    safe_name = filename.replace(" ", "_").replace(".", "_")
    return f"{safe_name}_{content_hash}"


async def ingest_file(file_bytes: bytes, filename: str) -> dict:
    text = extract_text(file_bytes, filename)
    if not text.strip():
        raise ValueError("Could not extract any text from the file.")

    chunks = chunk_text(text)
    vectors = await embed_in_batches(chunks)

    doc_id = make_doc_id(filename, file_bytes)
    add_chunks(doc_id, chunks, vectors)

    return {
        "doc_id": doc_id,
        "filename": filename,
        "chunks": len(chunks),
        "chars": len(text),
    }
