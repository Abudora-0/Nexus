# Nexus

A fully local document chat application. Upload PDFs or text files and ask questions about them — powered by RAG (Retrieval-Augmented Generation) with local AI models via Ollama. No API keys, no cloud, no data leaves your machine.

![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-6-3178C6?logo=typescript&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-black)

## Design

An archive reading room: espresso-ink dark theme with parchment text and brass accents, Cormorant Garamond display type over Spectral body serif, a card-catalogue sidebar, manuscript-leaf chat bubbles, and citations rendered as § footnotes. Fits the product: a private, local archive you consult.

## Features

- **Local-First** — all processing runs via Ollama; your documents never leave your machine
- **PDF & TXT Support** — upload and parse documents up to 10 MB
- **Semantic Search** — documents are chunked, embedded, and stored in LanceDB for vector similarity search
- **Streaming Responses** — answers stream token-by-token via Server-Sent Events
- **Source Citations** — every answer shows the retrieved chunks and their source locations
- **Document Summarization** — generate a full summary of any uploaded document
- **Document Management** — upload, select, and delete documents from the sidebar
- **Chat History** — conversations are persisted in browser localStorage
- **Configurable LLM Params** — tune temperature, context window, top-p, and top-k
- **Markdown Rendering** — responses render with full Markdown and code highlighting

## Tech Stack

### Backend
| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| LLM Runtime | Ollama |
| Language Model | `phi3:mini` (2.2 GB) |
| Embeddings | `nomic-embed-text` (274 MB) |
| Vector Store | LanceDB |
| PDF Parsing | pdfplumber |
| HTTP Client | httpx |

### Frontend
| Layer | Technology |
|---|---|
| Framework | React 19 + Vite |
| Language | TypeScript |
| Animations | Framer Motion |
| File Upload | react-dropzone |
| Markdown | react-markdown + react-syntax-highlighter |
| HTTP | Axios |

## Getting Started

### Prerequisites

- [Ollama](https://ollama.com) — local AI runtime
- Python 3.10+
- Node.js 18+

### 1. Install Ollama Models

```bash
ollama pull phi3:mini
ollama pull nomic-embed-text
```

### 2. Backend Setup

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

## How It Works

1. **Upload** a PDF or TXT file via drag-and-drop
2. The backend **chunks** the document and generates **vector embeddings** using `nomic-embed-text`
3. Embeddings are stored in **LanceDB** (a local vector database)
4. When you ask a question, the backend performs a **semantic search** to retrieve the most relevant chunks
5. The retrieved chunks are injected into the prompt and sent to **phi3:mini** via Ollama
6. The response **streams** back to the frontend token-by-token

## Project Structure

```
├── backend/
│   ├── main.py           # FastAPI app — all API routes
│   ├── embedder.py       # Text → vector embeddings via Ollama
│   ├── vectorstore.py    # LanceDB wrapper (store & search)
│   ├── ingestor.py       # PDF/TXT → chunks → embed → store pipeline
│   └── requirements.txt
└── frontend/
    └── src/
        ├── App.tsx        # Main React component
        ├── api.ts         # Backend API calls
        └── chatStorage.ts # Chat history (localStorage)
```

## License

MIT
