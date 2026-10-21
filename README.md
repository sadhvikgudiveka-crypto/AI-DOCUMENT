# Marginalia: AI Document Q&A

Ask questions about a PDF or text file and inspect the passages behind each answer. Files are processed in memory by a local FastAPI service; nothing is written to an upload or index directory.

## Prerequisites

- Node.js 20 or newer with npm
- Python 3.11 or newer

## Run locally

In PowerShell, from this project folder:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

Start the backend in the first terminal:

```powershell
Set-Location backend
python -m uvicorn app.main:app --reload
```

In a second terminal, from the project folder, install the frontend dependencies and start Vite:

```powershell
npm install
npm run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`). The UI proxies `/api` requests to FastAPI on port 8000. Use **Try the sample document** to check the flow without uploading a file or configuring credentials.

## Environment variables

The backend loads the root `.env` file. Copy `.env.example` to `.env`; demo mode works with the provided defaults and no API key.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_PROVIDER` | `demo` | `demo` for local hash embeddings and a simple local answer matcher, or `openai` for OpenAI embeddings and chat completions. |
| `OPENAI_API_KEY` | empty | Required only when `AI_PROVIDER=openai`. Keep this value in the backend environment; it is never included in frontend code. |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI chat-completion model. |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model. |
| `MAX_UPLOAD_MB` | `10` | Maximum upload size in MiB. |
| `CHUNK_SIZE` | `1000` | Approximate maximum chunk length in characters. |
| `CHUNK_OVERLAP` | `150` | Approximate overlap between chunks, in characters. Must be smaller than the chunk size. |

To use OpenAI, set `AI_PROVIDER=openai` and add your key to `.env`, then restart the backend. The provider implementation can be replaced in `backend/app/providers.py` without changing the API routes.

## Architecture

- `src/`: React and TypeScript single-page app. Handles file selection and drag-and-drop, client-side validation, chat state, loading/error states, and citation passage display.
- `backend/app/core.py`: PDF/TXT extraction, page-aware overlapping chunks, local feature-hash embeddings, cosine ranking.
- `backend/app/providers.py`: small provider boundary for local demo behavior or OpenAI embedding and answer requests.
- `backend/app/main.py`: FastAPI upload, demo, delete, health, and question endpoints. Documents and vectors live in process memory only.
- `backend/tests/`: focused tests for extraction, chunk overlap, retrieval, unsupported questions, and request validation.

Question flow: extract text by page, chunk with overlap, embed chunks, retrieve the top matching passages, then answer from only those passages. OpenAI responses must return source IDs from the retrieved set; answers without valid source IDs are replaced with the unsupported-answer message. Citations show PDF page numbers or text passage references and open the quoted source passage.

## Tests

From the project folder after installing backend requirements:

```powershell
..\.venv\Scripts\python.exe -m pytest backend\tests
```

## Current limitations

- Demo mode is deliberately lightweight: it uses local feature hashing for retrieval and a sentence matcher rather than a language model. It is useful for trying the workflow, not for high-quality semantic answers.
- Scanned/image-only PDFs are not OCR'd. PDFs must contain selectable text and have at most 300 pages.
- Documents and indexes are held in process memory. Restarting the backend clears them; this single-process MVP is not designed for multiple users or production deployment.
- Text citations identify a passage and character offset, not an exact location in a separate viewer. The source excerpt is shown when a citation is opened.
- OpenAI mode sends extracted passages and questions to OpenAI for embeddings and answer generation. Use demo mode for local-only processing.