"""
Búsqueda web opcional para enriquecer el feed (Google vía Serper.dev o SerpAPI.com).
Son proveedores distintos: la clave de uno no sirve para el otro.

- Serper: SERPER_API_KEY → https://google.serper.dev/search
- SerpAPI: SERPAPI_API_KEY → https://serpapi.com/search.json?engine=google

Si falla Serper (p. ej. 403 con clave equivocada) y hay SERPAPI_API_KEY, se intenta SerpAPI.
Sin ninguna clave válida, el curador solo usa Gemini + contexto OCEAN.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("dreamlodge.web_search")

SERPER_URL = "https://google.serper.dev/search"
SERPAPI_URL = "https://serpapi.com/search.json"


def _env_key(*names: str) -> str:
    raw = ""
    for n in names:
        raw = (os.getenv(n) or "").strip()
        if raw:
            break
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1].strip()
    return raw


def _organic_from_serper_payload(data: dict, num: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in (data.get("organic") or [])[:num]:
        title = (item.get("title") or "").strip()
        snip = (item.get("snippet") or "").strip()
        if title or snip:
            out.append({"title": title, "snippet": snip})
    return out


def _organic_from_serpapi_payload(data: dict, num: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in (data.get("organic_results") or [])[:num]:
        title = (item.get("title") or "").strip()
        snip = (item.get("snippet") or "").strip()
        if title or snip:
            out.append({"title": title, "snippet": snip})
    return out


def _call_serper(
    query: str, num: int, key: str
) -> tuple[list[dict[str, str]], bool]:
    """
    Devuelve (filas, request_fallido).
    request_fallido=True → error HTTP/red; el caller puede probar SerpAPI.
    """
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
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = (e.read() or b"").decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        hint = ""
        if e.code == 403:
            hint = (
                " (403 en serper.dev: clave Serper inválida o no es de serper.dev; "
                "SerpAPI usa SERPAPI_API_KEY en serpapi.com)"
            )
        elif e.code == 401:
            hint = " (401: revisa SERPER_API_KEY)"
        logger.warning("serper HTTP %s %s%s — cuerpo: %s", e.code, e.reason, hint, body or "(vacío)")
        return [], True
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        logger.warning("serper falló: %s", e)
        return [], True

    if not isinstance(data, dict):
        return [], False
    return _organic_from_serper_payload(data, num), False


def _call_serpapi(query: str, num: int, key: str) -> list[dict[str, str]]:
    params = urllib.parse.urlencode(
        {
            "engine": "google",
            "q": query.strip(),
            "api_key": key,
            "num": min(num, 10),
        }
    )
    url = f"{SERPAPI_URL}?{params}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = (e.read() or b"").decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        logger.warning(
            "serpapi HTTP %s %s — cuerpo: %s", e.code, e.reason, body or "(vacío)"
        )
        return []
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        logger.warning("serpapi falló: %s", e)
        return []

    if not isinstance(data, dict):
        return []
    return _organic_from_serpapi_payload(data, num)


def serper_search(query: str, *, num: int = 8) -> list[dict[str, str]]:
    """
    Resultados orgánicos {title, snippet}: primero Serper (si hay clave), si falla la
    petición y hay SerpAPI, entonces SerpAPI. Solo SerpAPI si no hay clave Serper.
    """
    q = (query or "").strip()
    if not q:
        return []

    serper_key = _env_key("SERPER_API_KEY", "SERPER_KEY")
    serpapi_key = _env_key("SERPAPI_API_KEY", "SERPAPI_KEY")

    if serper_key:
        rows, failed = _call_serper(q, num, serper_key)
        if not failed:
            return rows
        if serpapi_key:
            logger.info("Usando SerpAPI como respaldo tras fallo de Serper.")
            return _call_serpapi(q, num, serpapi_key)
        logger.info(
            "Búsqueda web desactivada: Serper falló y no hay SERPAPI_API_KEY. "
            "Las claves de serpapi.com van en SERPAPI_API_KEY, no en SERPER_API_KEY."
        )
        return []

    if serpapi_key:
        return _call_serpapi(q, num, serpapi_key)

    return []


def build_curator_context_from_serper(personality_line: str) -> tuple[str, bool]:
    """
    Ejecuta 2–3 consultas acotadas y concatena snippets para el prompt del curador.
    """
    queries = [
        f"cultural recommendations personality traits film series music books games {personality_line[:120]}",
        "best acclaimed albums films novels video games art lovers curated lists",
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


def build_artistic_web_context(
    o: float,
    c: float,
    e: float,
    a: float,
    n: float,
    test_type: object,
    subfacets_preview: str,
) -> tuple[str, bool]:
    """
    Consultas Serper orientadas a obras culturales concretas alineadas al perfil OCEAN
    (para descripción artística + suggestedWorks).
    """
    traits = (
        f"openness {o:.1f} conscientiousness {c:.1f} extraversion {e:.1f} "
        f"agreeableness {a:.1f} neuroticism {n:.1f} test {test_type}"
    )
    queries = [
        f"best films series novels albums video games art personality taste {traits[:140]}",
        f"acclaimed cultural masterpieces movies books music games emotional depth {traits[:120]}",
        f"obras culturales recomendadas cine literatura música juegos arte personalidad {traits[:130]}",
    ]
    if (subfacets_preview or "").strip():
        queries.append(
            f"curation lists film literature music games psychology {subfacets_preview[:160]}"
        )

    chunks: list[str] = []
    for q in queries:
        for row in serper_search(q, num=7):
            line = f"- {row['title']}: {row['snippet']}"
            chunks.append(line[:520])
    if not chunks:
        return "", False
    text = "\n".join(chunks)
    if len(text) > 7000:
        text = text[:7000] + "\n…"
    return text, True
