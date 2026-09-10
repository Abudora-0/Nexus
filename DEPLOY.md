# Deploying Nexus (free hosted demo)

The local app runs entirely on Ollama. The hosted demo swaps the AI layer for
the **Google Gemini API free tier** so it can run on a 512 MB free server.
Nothing else changes — same RAG pipeline, same LanceDB vector store, same UI.

| Piece | Host | Cost |
|---|---|---|
| Backend (FastAPI) | Render Web Service | Free |
| Frontend (Vite static) | Vercel | Free |
| LLM + embeddings | Google Gemini API | Free tier |

> **Note on the free tier:** Render's free web service sleeps after ~15 min of
> inactivity and cold-starts in ~50 s, and its disk is wiped on every restart.
> Nexus re-seeds `backend/samples/` on startup so the demo is never empty, but
> documents visitors upload disappear when the server sleeps. That's fine for a
> portfolio demo; the "run it yourself" path in the README stays fully local.

---

## 1. Get a Gemini API key

1. Go to <https://aistudio.google.com/apikey>
2. **Create API key** → copy it. Keep it secret (it goes in Render, never in git).

## 2. Deploy the backend to Render

1. Push this repo to GitHub (see the bottom of this file).
2. <https://render.com> → sign in with GitHub → **New** → **Blueprint**.
3. Pick this repo. Render reads `render.yaml` and proposes the `nexus-api` service.
4. Before the first deploy, set the two secret env vars:
   - `GEMINI_API_KEY` = the key from step 1
   - `ALLOWED_ORIGINS` = `*` for now (tighten to your Vercel URL after step 3)
5. **Apply** / **Create**. First build takes ~3–5 min.
6. When it's live, open `https://<your-service>.onrender.com/health` — you should
   see `{"status":"ok","provider":"gemini",...}`. Copy the base URL.

<details>
<summary>Prefer Fly.io or Hugging Face Spaces instead of Render?</summary>

Both work. The backend is a plain FastAPI app: build `pip install -r backend/requirements.txt`,
run `uvicorn main:app --host 0.0.0.0 --port $PORT` with working dir `backend/`, and
set the same env vars (`LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, `CHAT_MODEL`,
`EMBED_MODEL`, `ALLOWED_ORIGINS`). HF Spaces (free CPU tier, 16 GB RAM) doesn't
sleep after 15 min, so uploads survive longer.
</details>

## 3. Deploy the frontend to Vercel

1. <https://vercel.com> → **Add New** → **Project** → import this repo.
2. **Root Directory**: `frontend`
3. Framework preset: **Vite** (auto-detected). Build `npm run build`, output `dist`.
4. **Environment Variables**: add
   - `VITE_API_URL` = the Render base URL from step 2 (no trailing slash)
5. **Deploy**. Copy the resulting `https://<project>.vercel.app` URL.

## 4. Lock down CORS

Back in Render → `nexus-api` → **Environment** → set
`ALLOWED_ORIGINS` = `https://<project>.vercel.app` → save (it redeploys).

Done. Visit the Vercel URL.

---

## Updating the demo

Both hosts auto-deploy on every push to the default branch. Just push.

## Local development is unchanged

`backend/.env` keeps `LLM_PROVIDER=ollama`. See [HOW_TO_RUN.md](HOW_TO_RUN.md).

## Pushing this repo to GitHub

```bash
git add -A
git commit -m "Add hosted demo: Gemini provider, deploy config"
git branch -M main
git remote add origin https://github.com/<you>/nexus.git
git push -u origin main
```
