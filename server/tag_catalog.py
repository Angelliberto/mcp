"""
Catálogo de hashtags tipo género (estilo DeviantArt / metadatos de obras).
Combina géneros reales de APIs públicas (TMDB si hay TMDB_API_KEY) con un respaldo fijo.
"""
from __future__ import annotations

import json as json_lib
import logging
import os
import re
import unicodedata
import urllib.error
import urllib.request

logger = logging.getLogger("dreamlodge.tag_catalog")

# Slugs cortos al estilo #tag (sin espacios, sin tildes) — similar a géneros en obras
_FALLBACK_SLUGS: list[str] = [
    # Cine / serie
    "drama",
    "comedia",
    "terror",
    "thriller",
    "romance",
    "animacion",
    "documental",
    "fantasia",
    "cienciaficcion",
    "western",
    "belico",
    "musical",
    "historia",
    "misterio",
    "crimen",
    "aventura",
    # Música
    "jazz",
    "rock",
    "electronica",
    "clasica",
    "indie",
    "metal",
    "hiphop",
    "folk",
    "blues",
    "reggae",
    "soul",
    "pop",
    # Literatura / temas
    "fantasia",
    "ensayo",
    "poesia",
    "biografia",
    "distopia",
    # Arte visual
    "impresionismo",
    "surrealismo",
    "fotografia",
    "ilustracion",
    "conceptart",
    "retrato",
    "paisaje",
    "digitalart",
    # Videojuegos
    "rpg",
    "estrategia",
    "plataformas",
    "puzzle",
    "shooter",
    "aventura",
    "terror",
    "indie",
    "simulacion",
]


def slugify_hashtag(label: str) -> str:
    """Convierte una etiqueta humana o #tag en slug estable (minúsculas, sin espacios ni tildes)."""
    if not label or not isinstance(label, str):
        return ""
    t = label.strip()
    if t.startswith("#"):
        t = t[1:].strip()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.lower()
    t = re.sub(r"[^a-z0-9]+", "", t)
    return t[:32]


def _fetch_tmdb_genre_slugs() -> list[str]:
    key = (os.getenv("TMDB_API_KEY") or "").strip()
    if not key:
        return []
    slugs: list[str] = []
    for path in ("genre/movie/list", "genre/tv/list"):
        qs = f"language=es-ES&api_key={key}"
        url = f"https://api.themoviedb.org/3/{path}?{qs}"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json_lib.loads(resp.read().decode("utf-8", errors="replace"))
            for g in payload.get("genres") or []:
                name = (g.get("name") or "").strip()
                s = slugify_hashtag(name)
                if s and len(s) >= 2:
                    slugs.append(s)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json_lib.JSONDecodeError) as e:
            logger.warning("tag_catalog: TMDB %s falló: %s", path, e)
            continue
    return slugs


def get_hashtag_slug_catalog() -> list[str]:
    """Lista única de slugs para validación suave y prompt (orden: API primero, luego fallback)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for s in _fetch_tmdb_genre_slugs():
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    for s in _FALLBACK_SLUGS:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    return ordered


def format_catalog_for_prompt(max_items: int = 100) -> str:
    """Texto compacto para el prompt: #slug1 #slug2 …"""
    slugs = get_hashtag_slug_catalog()[:max_items]
    return " ".join(f"#{s}" for s in slugs)

