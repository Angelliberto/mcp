"""
Búsqueda web opcional para enriquecer el feed personalizado (Serper.dev).
Sin API key, el curador solo usa Gemini + contexto OCEAN.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("dreamlodge.web_search")

SERPER_URL = "https://google.serper.dev/search"


def serper_search(query: str, *, num: int = 8) -> list[dict[str, str]]:
    """
    Devuelve lista de {title, snippet} desde Serper Google Search API.
    """
    key = (os.getenv("SERPER_API_KEY") or os.getenv("SERPER_KEY") or "").strip()
    if not key or not (query or "").strip():
        return []

    payload = json.dumps({"q": query.strip(), "num": min(num, 10)}).encode("utf-8")
    req = urllib.request.Request(
        SERPER_URL,
        data=payload,
        headers={
            "X-API-KEY": key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        logger.warning("serper_search falló: %s", e)
        return []

    out: list[dict[str, str]] = []
    for item in (data.get("organic") or [])[:num]:
        title = (item.get("title") or "").strip()
        snip = (item.get("snippet") or "").strip()
        if title or snip:
            out.append({"title": title, "snippet": snip})
    return out


def build_curator_context_from_serper(
    personality_line: str, saved_tags: list[str]
) -> tuple[str, bool]:
    """
    Ejecuta 2–3 consultas acotadas y concatena snippets para el prompt del curador.
    """
    tag_part = ", ".join(saved_tags[:8]) if saved_tags else ""
    queries = [
        f"cultural recommendations personality traits film series music books games {personality_line[:120]}",
        f"best acclaimed albums films novels video games art lovers {tag_part}"[:240],
    ]
    chunks: list[str] = []
    for q in queries:
        for row in serper_search(q, num=6):
            line = f"- {row['title']}: {row['snippet']}"
            chunks.append(line[:500])
    if not chunks:
        return "", False
    text = "\n".join(chunks)
    if len(text) > 6000:
        text = text[:6000] + "\n…"
    return text, True
