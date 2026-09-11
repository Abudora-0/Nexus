import asyncio
import logging
import os
import traceback
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
from dotenv import load_dotenv

import providers
from ingestor import ingest_file, make_doc_id
from embedder import embed_text
from vectorstore import search, list_documents, delete_document, get_all_chunks

load_dotenv()

# Comma-separated list of allowed frontend origins, or "*" for any (dev default).
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

SAMPLES_DIR = Path(__file__).parent / "samples"

logger = logging.getLogger("nexus")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Nexus API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def warmup_models():
    """Load local models into RAM in the background (no-op for hosted providers)
    so the user's first real question doesn't pay a cold-load cost."""
    asyncio.create_task(providers.warmup())


@app.on_event("startup")
async def seed_sample_documents():
    """Ingest anything in backend/samples/ so the hosted demo is never empty
    (its filesystem is wiped on every restart/redeploy). Skips docs already
    present, so this is cheap on warm restarts."""
    if not SAMPLES_DIR.is_dir():
        return

    async def _run():
        try:
            existing = set(list_documents())
        except Exception:
            existing = set()
        for path in sorted(SAMPLES_DIR.glob("*.txt")) + sorted(SAMPLES_DIR.glob("*.pdf")):
            data = path.read_bytes()
            if make_doc_id(path.name, data) in existing:
                continue
            try:
                await ingest_file(data, path.name)
                logger.info(f"Seeded sample document '{path.name}'")
            except Exception as e:
                logger.warning(f"Could not seed '{path.name}': {e}")

    asyncio.create_task(_run())


# Upload

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    ext = "." + file.filename.split(".")[-1].lower()
    if ext not in {".pdf", ".txt"}:
        raise HTTPException(400, f"Unsupported type '{ext}'. Use PDF or TXT.")
    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large. Max 10 MB.")
    try:
        result = await ingest_file(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.error(f"Upload failed for '{file.filename}': {e}\n{traceback.format_exc()}")
        raise HTTPException(500, f"Failed to process '{file.filename}'. It may be empty, corrupted, or scanned-image-only.")
    if result["chunks"] == 0:
        raise HTTPException(422, f"No usable text found in '{file.filename}'. It may be a scanned/image-only PDF.")
    return {"message": "Uploaded successfully.", **result}


# Streaming chat

class ChatRequest(BaseModel):
    question: str
    doc_id:   str | None = None
    doc_ids:  list[str] | None = None


def _send(type: str, **kwargs):
    return f"data: {json.dumps({'type': type, **kwargs})}\n\n"


SYSTEM_PROMPT = (
    "You are Nexus, an expert document assistant. Answer questions using ONLY the provided context.\n"
    "- Be direct and thorough. Never say 'the document says'.\n"
    "- Use **bold** for key terms, bullet points for lists.\n"
    "- If not in context, say: I couldn't find that in the uploaded documents."
)


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    try:
        query_vector = await embed_text(req.question)
    except Exception as exc:
        err_msg = str(exc) or exc.__class__.__name__
        logger.error(f"Embedding failed: {exc}")
        async def _err():
            yield _send("token", data=f"⚠️ Embedding error: {err_msg}")
            yield _send("done")
        return StreamingResponse(_err(), media_type="text/event-stream")

    chunks = search(query_vector, top_k=4, doc_id=req.doc_id, doc_ids=req.doc_ids)
    if not chunks:
        async def _no_docs():
            yield _send("token", data="No documents found. Please upload a file and select it first.")
            yield _send("done")
        return StreamingResponse(_no_docs(), media_type="text/event-stream")

    context    = "\n\n---\n\n".join(f"[{c['doc_id']}]\n{c['text']}" for c in chunks)
    sources    = list(dict.fromkeys(c["doc_id"] for c in chunks))
    src_chunks = [{"doc_id": c["doc_id"], "text": c["text"][:200]} for c in chunks]

    user_prompt = f"CONTEXT:\n{context}\n\nQUESTION: {req.question}"

    async def stream_tokens():
        yield _send("sources", data=sources, chunks=src_chunks)
        try:
            async for token in providers.stream_chat(SYSTEM_PROMPT, user_prompt, max_tokens=512):
                yield _send("token", data=token)
        except Exception as e:
            logger.error(f"Chat stream failed: {e}")
            yield _send("token", data=f"⚠️ Model error: {e}")
        finally:
            yield _send("done")

    return StreamingResponse(stream_tokens(), media_type="text/event-stream")


# Document summary

@app.get("/summarize/{doc_id}")
async def summarize_document(doc_id: str):
    chunks = get_all_chunks(doc_id)
    if not chunks:
        raise HTTPException(404, "Document not found.")

    combined = "\n\n".join(chunks)[:4000]
    system = "You are a document summarizer. Be clear and structured."
    user = (
        "Summarize this document with: a one-sentence overview, key topics as "
        f"bullet points, and any important facts or numbers.\n\nDOCUMENT:\n{combined}"
    )

    async def stream_summary():
        try:
            async for token in providers.stream_chat(system, user, max_tokens=600):
                yield _send("token", data=token)
        except Exception as e:
            logger.error(f"Summary stream failed: {e}")
            yield _send("token", data=f"⚠️ Error: {e}")
        finally:
            yield _send("done")

    return StreamingResponse(stream_summary(), media_type="text/event-stream")


# Document management

@app.get("/documents")
def get_documents():
    return {"documents": list_documents()}

@app.delete("/documents/{doc_id}")
def remove_document(doc_id: str):
    delete_document(doc_id)
    return {"message": f"Deleted '{doc_id}'."}

# TEMPORARY: lists the Groq models this key can actually use, to find a
# replacement for a retired CHAT_MODEL without needing shell access on the
# free Render tier. Remove this route once the right model id is confirmed.
@app.get("/debug/groq-models")
async def debug_groq_models():
    import httpx as _httpx
    if not providers.GROQ_API_KEY:
        raise HTTPException(400, "GROQ_API_KEY not set.")
    async with _httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{providers.GROQ_BASE}/models",
            headers={"Authorization": f"Bearer {providers.GROQ_API_KEY}"},
        )
        r.raise_for_status()
        ids = sorted(m["id"] for m in r.json().get("data", []))
    return {"models": ids}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "chat": f"{providers.CHAT_PROVIDER}:{providers.CHAT_MODEL}",
        "embed": f"{providers.EMBED_PROVIDER}:{providers.EMBED_MODEL}",
    }
