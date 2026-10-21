from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    id: str
    text: str
    page: int | None
    start: int
    end: int
    vector: list[float] | None = None


def extract_text(filename: str, content: bytes) -> list[tuple[int | None, str]]:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == "txt":
        try:
            text = content.decode("utf-8-sig").strip()
        except UnicodeDecodeError as error:
            raise ValueError("This text file is not valid UTF-8.") from error
        if not text or "\x00" in text:
            raise ValueError("The document does not contain readable text.")
        return [(None, text)]
    if suffix == "pdf":
        import fitz

        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception as error:
            raise ValueError("This PDF could not be opened. Check that it is a valid PDF.") from error
        if document.page_count > 300:
            raise ValueError("PDFs must contain 300 pages or fewer.")
        pages = [(number + 1, page.get_text("text").strip()) for number, page in enumerate(document)]
        document.close()
        pages = [(number, text) for number, text in pages if text]
        if not pages:
            raise ValueError("No selectable text was found. Scanned PDFs are not supported yet.")
        return pages
    raise ValueError("Choose a PDF or plain-text (.txt) file.")


def chunk_pages(
    pages: list[tuple[int | None, str]], size: int = 1000, overlap: int = 150
) -> list[Chunk]:
    if size < 100 or overlap < 0 or overlap >= size:
        raise ValueError("Chunk size and overlap settings are invalid.")
    chunks: list[Chunk] = []
    for page, text in pages:
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            right = end
            if end < len(text):
                boundary = text.rfind(" ", start + size // 2, end)
                if boundary > start:
                    right = boundary
            passage = text[start:right].strip()
            if passage:
                chunks.append(Chunk(
                    id=f"c{len(chunks) + 1}", text=passage, page=page,
                    start=start, end=right,
                ))
            if right >= len(text):
                break
            start = max(start + 1, right - overlap)
    return chunks


def local_embedding(text: str, dimensions: int = 256) -> list[float]:
    vector = [0.0] * dimensions
    terms = re.findall(r"[a-z0-9]+", text.lower())
    for term in terms:
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % dimensions
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def retrieve(chunks: list[Chunk], query_vector: list[float], limit: int = 4) -> list[Chunk]:
    return sorted(
        chunks,
        key=lambda chunk: similarity(chunk.vector or [], query_vector),
        reverse=True,
    )[:limit]