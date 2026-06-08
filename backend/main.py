from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx, json, os, traceback
from dotenv import load_dotenv

from ingestor import ingest_file
from embedder import embed_text
from vectorstore import search, list_documents, delete_document, get_all_chunks

load_dotenv()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CHAT_MODEL      = os.getenv("CHAT_MODEL", "phi3:mini")

app = FastAPI(title="Nexus API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Upload ────────────────────────────────────────────────────────────────────
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
    return {"message": "Uploaded successfully.", **result}


# ── Streaming Chat ────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str
    doc_id:   str | None = None
    doc_ids:  list[str] | None = None


def _send(type: str, **kwargs):
    return f"data: {json.dumps({'type': type, **kwargs})}\n\n"


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty.")

    # 1. Embed
    try:
        query_vector = await embed_text(req.question)
    except Exception as e:
        async def _err():
            yield _send("token", data=f"⚠️ Embedding error: {e}")
            yield _send("done")
        return StreamingResponse(_err(), media_type="text/event-stream")

    # 2. Retrieve
    chunks = search(query_vector, top_k=4, doc_id=req.doc_id, doc_ids=req.doc_ids)
    if not chunks:
        async def _no_docs():
            yield _send("token", data="No documents found. Please upload a file and select it first.")
            yield _send("done")
        return StreamingResponse(_no_docs(), media_type="text/event-stream")

    context      = "\n\n---\n\n".join(f"[{c['doc_id']}]\n{c['text']}" for c in chunks)
    sources      = list(dict.fromkeys(c["doc_id"] for c in chunks))
    src_chunks   = [{"doc_id": c["doc_id"], "text": c["text"][:200]} for c in chunks]

    # phi3 native prompt format
    prompt = (
        "<|system|>\n"
        "You are Nexus, an expert document assistant. Answer questions using ONLY the provided context.\n"
        "- Be direct and thorough. Never say 'the document says'.\n"
        "- Use **bold** for key terms, bullet points for lists.\n"
        "- If not in context, say: I couldn't find that in the uploaded documents.\n"
        "<|end|>\n"
        "<|user|>\n"
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {req.question}\n"
        "<|end|>\n"
        "<|assistant|>\n"
    )

    async def stream_tokens():
        yield _send("sources", data=sources, chunks=src_chunks)
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST", f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": CHAT_MODEL,
                        "prompt": prompt,
                        "stream": True,
                        "options": {
                            "num_predict": 512,   # max tokens to generate
                            "num_ctx": 2048,       # context window (default 131k = very slow!)
                            "temperature": 0.2,
                            "top_p": 0.9,
                            "top_k": 20,           # faster sampling
                        }
                    }
                ) as resp:
                    if resp.status_code != 200:
                        yield _send("token", data=f"⚠️ Model error (HTTP {resp.status_code}). Is Ollama running with phi3:mini?")
                        yield _send("done")
                        return
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if token := data.get("response", ""):
                                yield _send("token", data=token)
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            yield _send("token", data="⚠️ Cannot connect to Ollama. Make sure it's running.")
        except httpx.TimeoutException:
            yield _send("token", data="⚠️ Response timed out. Try a shorter question.")
        except Exception as e:
            yield _send("token", data=f"⚠️ Unexpected error: {str(e)}")
        finally:
            yield _send("done")

    return StreamingResponse(stream_tokens(), media_type="text/event-stream")


# ── Document Summary ──────────────────────────────────────────────────────────
@app.get("/summarize/{doc_id}")
async def summarize_document(doc_id: str):
    chunks = get_all_chunks(doc_id)
    if not chunks:
        raise HTTPException(404, "Document not found.")

    combined = "\n\n".join(chunks)[:4000]
    prompt = (
        "<|system|>\nYou are a document summarizer. Be clear and structured.<|end|>\n"
        "<|user|>\nSummarize this document with: a one-sentence overview, key topics as bullet points, "
        f"and any important facts or numbers.\n\nDOCUMENT:\n{combined}\n<|end|>\n"
        "<|assistant|>\n"
    )

    async def stream_summary():
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST", f"{OLLAMA_BASE_URL}/api/generate",
                    json={"model": CHAT_MODEL, "prompt": prompt, "stream": True,
                          "options": {"num_predict": 600, "temperature": 0.2}}
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line: continue
                        try:
                            data = json.loads(line)
                            if token := data.get("response", ""):
                                yield _send("token", data=token)
                            if data.get("done"): break
                        except: continue
        except Exception as e:
            yield _send("token", data=f"⚠️ Error: {str(e)}")
        finally:
            yield _send("done")

    return StreamingResponse(stream_summary(), media_type="text/event-stream")


# ── Document Management ───────────────────────────────────────────────────────
@app.get("/documents")
def get_documents():
    return {"documents": list_documents()}

@app.delete("/documents/{doc_id}")
def remove_document(doc_id: str):
    delete_document(doc_id)
    return {"message": f"Deleted '{doc_id}'."}

@app.get("/health")
def health():
    return {"status": "ok", "model": CHAT_MODEL}
