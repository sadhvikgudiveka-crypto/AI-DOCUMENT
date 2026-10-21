from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .core import Chunk, chunk_pages, extract_text, retrieve
from .providers import AIProvider

load_dotenv()
app = FastAPI(title="Marginalia Document Q&A", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
documents: dict[str, "StoredDocument"] = {}


@dataclass
class StoredDocument:
    id: str
    name: str
    pages: list[tuple[int | None, str]]
    chunks: list[Chunk]
    provider: AIProvider


class QuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


def get_provider() -> AIProvider:
    try:
        return AIProvider()
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


async def index_document(filename: str, content: bytes) -> StoredDocument:
    try:
        pages = extract_text(filename, content)
        chunks = chunk_pages(pages, CHUNK_SIZE, CHUNK_OVERLAP)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    provider = get_provider()
    try:
        vectors = await provider.embed([chunk.text for chunk in chunks])
    except Exception as error:
        raise HTTPException(status_code=502, detail="Document embedding failed. Check the AI provider settings.") from error
    for chunk, vector in zip(chunks, vectors):
        chunk.vector = vector
    stored = StoredDocument(str(uuid.uuid4()), filename, pages, chunks, provider)
    documents[stored.id] = stored
    return stored


def document_payload(document: StoredDocument) -> dict:
    return {
        "id": document.id,
        "name": document.name,
        "page_count": sum(page is not None for page, _ in document.pages),
        "chunk_count": len(document.chunks),
    }


@app.get("/api/health")
async def health() -> dict:
    provider = os.getenv("AI_PROVIDER", "demo").lower()
    configured = provider == "demo" or (
        provider == "openai" and bool(os.getenv("OPENAI_API_KEY", "").strip())
    )
    return {
        "status": "ok",
        "provider": provider,
        "demo_mode": provider == "demo",
        "configured": configured,
        "max_upload_mb": int(os.getenv("MAX_UPLOAD_MB", "10")),
    }


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...)) -> dict:
    filename = file.filename or ""
    if not filename.lower().endswith((".pdf", ".txt")):
        raise HTTPException(status_code=400, detail="Choose a PDF or plain-text (.txt) file.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Files must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller.")
    if not content:
        raise HTTPException(status_code=400, detail="The selected file is empty.")
    stored = await index_document(filename, content)
    return document_payload(stored)


@app.post("/api/demo")
async def load_demo() -> dict:
    sample = (
        "Field Notes: Urban Pollinator Gardens\n\n"
        "A small community garden can support native pollinators when it offers blooms from early spring through late autumn. "
        "Plant at least three species that flower in each season, and favor native plants suited to the local climate.\n\n"
        "Avoid pesticides, including products labeled natural, because they can harm bees and other beneficial insects. "
        "Leave a few patches of bare soil for ground-nesting bees and keep some hollow stems standing through winter.\n\n"
        "A garden does not need to be large. Even a sunny balcony with a mix of native flowering plants can provide food and shelter. "
        "In a shared garden, a simple sign explaining the habitat can help neighbors understand why some stems and leaves are left in place."
    )
    stored = await index_document("field-notes-pollinators.txt", sample.encode("utf-8"))
    return document_payload(stored)


@app.get("/api/documents/{document_id}")
async def get_document(document_id: str) -> dict:
    document = documents.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="This document is no longer available. Upload it again to continue.")
    return document_payload(document)


@app.delete("/api/documents/{document_id}")
async def remove_document(document_id: str) -> dict:
    if documents.pop(document_id, None) is None:
        raise HTTPException(status_code=404, detail="This document is no longer available.")
    return {"removed": True}


@app.post("/api/documents/{document_id}/questions")
async def ask_question(document_id: str, body: QuestionRequest) -> dict:
    document = documents.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="This document is no longer available. Upload it again to continue.")
    question = body.question.strip()
    if len(question) < 2:
        raise HTTPException(status_code=422, detail="Ask a question with at least 2 characters.")
    try:
        query_vector = (await document.provider.embed([question]))[0]
        relevant = retrieve(document.chunks, query_vector)
        answer, source_ids = await document.provider.answer(question, relevant)
    except Exception as error:
        raise HTTPException(status_code=502, detail="Could not generate an answer. Check your provider settings and try again.") from error
    by_id = {chunk.id: chunk for chunk in relevant}
    citations = []
    for source_id in source_ids:
        chunk = by_id.get(source_id)
        if chunk:
            citations.append({
                "id": chunk.id,
                "document": document.name,
                "page": chunk.page,
                "passage": chunk.text[:420],
                "start": chunk.start,
            })
    if not citations:
        answer = "I couldn't find enough information in this document to answer that."
    return {"answer": answer, "citations": citations}