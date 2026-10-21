from __future__ import annotations

import json
import os
import re

import httpx

from .core import Chunk, local_embedding


class AIProvider:
    def __init__(self) -> None:
        self.mode = os.getenv("AI_PROVIDER", "demo").strip().lower()
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if self.mode not in {"demo", "openai"}:
            raise ValueError("AI_PROVIDER must be 'demo' or 'openai'.")
        if self.mode == "openai" and not self.api_key:
            raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai.")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.mode == "demo":
            return [local_embedding(text) for text in texts]
        response = await self._post("/embeddings", {
            "model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            "input": texts,
        })
        return [item["embedding"] for item in response["data"]]

    async def answer(self, question: str, chunks: list[Chunk]) -> tuple[str, list[str]]:
        if self.mode == "demo":
            return self._demo_answer(question, chunks)
        passage_text = "\n\n".join(f"[{chunk.id}] {chunk.text}" for chunk in chunks)
        response = await self._post("/chat/completions", {
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer only from the provided document excerpts. If they do not support "
                        "an answer, say you could not find that information. Return JSON with "
                        "keys answer and source_ids. source_ids must contain only excerpt IDs "
                        "that directly support the answer. Keep the answer concise."
                    ),
                },
                {"role": "user", "content": f"Question: {question}\n\nExcerpts:\n{passage_text}"},
            ],
        })
        try:
            result = json.loads(response["choices"][0]["message"]["content"])
            answer = str(result.get("answer", "")).strip()
            source_ids = result.get("source_ids", [])
        except (KeyError, TypeError, json.JSONDecodeError):
            return "I couldn't find enough information in this document to answer that.", []
        allowed = {chunk.id for chunk in chunks}
        if not answer or not isinstance(source_ids, list):
            return "I couldn't find enough information in this document to answer that.", []
        valid_ids = [source_id for source_id in source_ids if source_id in allowed]
        if not valid_ids:
            return "I couldn't find enough information in this document to answer that.", []
        return answer, valid_ids

    async def _post(self, path: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.openai.com/v1{path}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _demo_answer(question: str, chunks: list[Chunk]) -> tuple[str, list[str]]:
        if not chunks:
            return "I couldn't find enough information in this document to answer that.", []
        def words(text: str) -> set[str]:
            tokens = re.findall(r"[a-z0-9]+", text.lower())
            return {
                token[:-1] if token.endswith("s") and not token.endswith("ss") and len(token) > 4 else token
                for token in tokens
            }

        summary_terms = {"summary", "summarize", "overview", "ideas", "remember"}
        ignored = {"about", "after", "also", "does", "from", "have", "into", "please", "should", "that", "them", "then", "there", "this", "what", "when", "where", "which", "with", "would", "your"}
        query_words = {word for word in words(question) if len(word) > 2 and word not in ignored and word not in summary_terms}
        query_words.difference_update({"and", "are", "can", "for", "how", "the", "why", "you"})
        tokens_by_chunk = {
            chunk.id: words(chunk.text) for chunk in chunks
        }
        ranked = sorted(
            chunks,
            key=lambda chunk: len(query_words & tokens_by_chunk[chunk.id]),
            reverse=True,
        )
        best = ranked[0]
        hits = len(query_words & tokens_by_chunk[best.id])
        asks_for_summary = bool(summary_terms.intersection(words(question)))
        if (not query_words or hits == 0) and not asks_for_summary:
            return "I couldn't find enough information in this document to answer that.", []
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", best.text.replace("\n", " ")) if part.strip()]
        sentence_tokens = [words(part) for part in sentences]
        term_weights = {
            word: 1 / sum(word in tokens for tokens in sentence_tokens)
            for word in query_words
            if any(word in tokens for tokens in sentence_tokens)
        }
        sentence = max(
            zip(sentences, sentence_tokens),
            key=lambda item: sum(term_weights.get(word, 0) for word in query_words & item[1]),
            default=best.text[:260],
        )[0]
        if asks_for_summary and (not query_words or hits == 0):
            sentence = " ".join(sentences[:2])
        answer = sentence if len(sentence) <= 280 else sentence[:277].rstrip() + "..."
        return answer, [best.id]