const BASE = "http://localhost:8000";

export interface UploadResponse {
  doc_id: string; filename: string; chunks: number; chars: number;
}

export interface SourceChunk { doc_id: string; text: string; }

export async function uploadFile(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/upload`, { method: "POST", body: form });
  if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || `Upload failed (${res.status})`); }
  return res.json();
}

export async function listDocuments(): Promise<string[]> {
  const res = await fetch(`${BASE}/documents`);
  if (!res.ok) throw new Error("Failed to load documents");
  return (await res.json()).documents;
}

export async function deleteDocument(docId: string) {
  await fetch(`${BASE}/documents/${docId}`, { method: "DELETE" });
}

/** Streaming chat with optional doc filter (single or multi) */
export async function chatStream(
  question: string,
  docId: string | null,
  docIds: string[] | null,
  onToken:   (t: string) => void,
  onSources: (s: string[], chunks: SourceChunk[]) => void,
  onDone:    () => void,
) {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, doc_id: docId, doc_ids: docIds }),
  });
  if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || "Chat failed"); }
  await readSSE(res, onToken, onSources, onDone);
}

/** Stream a document summary */
export async function summarizeDoc(
  docId: string,
  onToken: (t: string) => void,
  onDone: () => void,
) {
  const res = await fetch(`${BASE}/summarize/${encodeURIComponent(docId)}`);
  if (!res.ok) throw new Error("Summary failed");
  await readSSE(res, onToken, () => {}, onDone);
}

async function readSSE(
  res: Response,
  onToken:   (t: string) => void,
  onSources: (s: string[], chunks: SourceChunk[]) => void,
  onDone:    () => void,
) {
  const reader = res.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const ev = JSON.parse(line.slice(6));
        if (ev.type === "token")   onToken(ev.data);
        if (ev.type === "sources") onSources(ev.data, ev.chunks ?? []);
        if (ev.type === "done")    onDone();
      } catch {}
    }
  }
  onDone();
}
