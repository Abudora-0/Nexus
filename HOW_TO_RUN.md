# Nexus — How to Run

## First Time Setup (do this once)

### 1. Install Requirements
- [Ollama](https://ollama.com) — local AI runtime
- [Node.js](https://nodejs.org) — for the frontend
- [Python 3.10+](https://python.org) — for the backend

### 2. Set Ollama Models Path
So models are stored on D: drive instead of C:
- Press `Win + S` → search **Environment Variables**
- Click **Edit the system environment variables**
- Click **Environment Variables** → Under **System variables** → **New**
  - Name: `OLLAMA_MODELS`
  - Value: `D:\OllamaModels`
- Click OK → OK → OK

### 3. Start Ollama with correct path (every time)
```powershell
$env:OLLAMA_MODELS = "D:\OllamaModels"
Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
```

---

## Every Time You Want to Run Nexus

### Step 1 — Start Ollama
Open PowerShell and run:
```powershell
$env:OLLAMA_MODELS = "D:\OllamaModels"
Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
```

### Step 2 — Start the Backend
Open a **new PowerShell window** and run:
```powershell
cd D:\Projects\docuchat\backend
.\venv\Scripts\activate
uvicorn main:app --reload
```
Wait until you see:
```
INFO:     Application startup complete.
```

### Step 3 — Start the Frontend
Open **another new PowerShell window** and run:
```powershell
cd D:\Projects\docuchat\frontend
npm run dev
```
Wait until you see:
```
VITE ready in ... ms
➜  Local: http://localhost:5173/
```

### Step 4 — Open the App
Go to your browser and open:
```
http://localhost:5173
```

---

## Stopping the App
- Press `Ctrl+C` in both the backend and frontend terminals
- Right-click Ollama in system tray → Quit Ollama

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ollama list` shows nothing | Run `$env:OLLAMA_MODELS = "D:\OllamaModels"` first |
| Backend crashes on start | Make sure Ollama is running first |
| Upload fails | Check backend terminal for error message |
| "No documents found" | Make sure you clicked a document in the sidebar to select it |
| Slow responses | Normal for first response — model loads into RAM, gets faster after |

---

## Models Used
| Model | Purpose | Size | Location |
|-------|---------|------|----------|
| `phi3:mini` | Answering questions | 2.2 GB | D:\OllamaModels |
| `nomic-embed-text` | Document embeddings | 274 MB | D:\OllamaModels |

---

## Project Structure
```
docuchat/
├── backend/
│   ├── main.py          ← FastAPI app (all API routes)
│   ├── embedder.py      ← Converts text to vectors via Ollama
│   ├── vectorstore.py   ← LanceDB wrapper (stores & searches chunks)
│   ├── ingestor.py      ← PDF/TXT → chunks → embed → store pipeline
│   ├── .env             ← Config (model names, Ollama URL)
│   └── requirements.txt ← Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.tsx      ← Main React component
│   │   ├── api.ts       ← Backend API calls
│   │   └── chatStorage.ts ← Chat history (localStorage)
│   └── package.json
└── HOW_TO_RUN.md        ← This file
```
