"""
Catálogo de hashtags (géneros / palabras clave) para prompts de IA.
- Credenciales: GET al backend Dream Lodge (/api/internal/mcp/media-catalog-credentials) con X-MCP-Internal-Secret.
- Fuentes: TMDB (cine/TV), Spotify (genre seeds), IGDB (géneros, keywords, themes).
- Respaldo local si falla alguna API.
"""
from __future__ import annotations

import json as json_lib
import logging
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("dreamlodge.tag_catalog")

# Slugs de respaldo si no hay red / credenciales
_FALLBACK_SLUGS: list[str] = [
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
    "ensayo",
    "poesia",
    "biografia",
    "distopia",
    "impresionismo",
    "surrealismo",
    "fotografia",
    "ilustracion",
    "conceptart",
    "retrato",
    "paisaje",
    "digitalart",
    "rpg",
    "estrategia",
    "plataformas",
    "puzzle",
    "shooter",
    "simulacion",
]

_CRED_CACHE: dict | None = None
_CRED_CACHE_TS: float = 0.0
_CRED_TTL_SEC: float = 50 * 60  # Tokens ~1h; renovar antes

_CATALOG_CACHE: list[str] | None = None
_CATALOG_CACHE_TS: float = 0.0
_CATALOG_TTL_SEC: float = 30 * 60


def slugify_hashtag(label: str) -> str:
    """Slug estable (minúsculas, sin espacios ni tildes)."""
    if not label or not isinstance(label, str):
        return ""
    t = label.strip()
    if t.startswith("#"):
        t = t[1:].strip()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.lower().replace("-", "").replace("_", "")
    t = re.sub(r"[^a-z0-9]+", "", t)
    return t[:32]


def _backend_base_url() -> str:
    return (
        os.getenv("DL_BACKEND_URL") or os.getenv("BACKEND_URL") or ""
    ).strip().rstrip("/")


def _fetch_json(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> dict | list | None:
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json_lib.loads(raw)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json_lib.JSONDecodeError) as e:
        logger.warning("tag_catalog: HTTP %s %s — %s", method, url[:80], e)
        return None


def fetch_credentials_from_backend() -> dict:
    """
    Pide al backend tokens TMDB/Spotify/IGDB (el backend usa sus .env; el MCP no guarda client secrets).
    """
    global _CRED_CACHE, _CRED_CACHE_TS
    now = time.time()
    if _CRED_CACHE is not None and now - _CRED_CACHE_TS < _CRED_TTL_SEC:
        return _CRED_CACHE

    base = _backend_base_url()
    secret = (os.getenv("MCP_INTERNAL_SECRET") or "").strip()
    if not base or not secret:
        _CRED_CACHE = {}
        _CRED_CACHE_TS = now
        return _CRED_CACHE

    url = f"{base}/api/internal/mcp/media-catalog-credentials"
    payload = _fetch_json(
        url,
        headers={"X-MCP-Internal-Secret": secret},
    )
    if not isinstance(payload, dict) or not payload.get("ok"):
        logger.warning("tag_catalog: credenciales backend no disponibles")
        _CRED_CACHE = {}
        _CRED_CACHE_TS = now
        return _CRED_CACHE

    _CRED_CACHE = payload
    _CRED_CACHE_TS = now
    return _CRED_CACHE


def _tmdb_genre_slugs(api_key: str) -> list[str]:
    if not api_key:
        return []
    slugs: list[str] = []
    auth_headers: dict[str, str] = {}
    for path in ("genre/movie/list", "genre/tv/list"):
        if api_key.startswith("eyJ"):
            auth_headers = {"Authorization": f"Bearer {api_key}"}
            qs = "language=es-ES"
        else:
            qs = f"language=es-ES&api_key={urllib.parse.quote(api_key)}"
        url = f"https://api.themoviedb.org/3/{path}?{qs}"
        payload = _fetch_json(url, headers=auth_headers)
        if not isinstance(payload, dict):
            continue
        for g in payload.get("genres") or []:
            name = (g.get("name") or "").strip()
            s = slugify_hashtag(name)
            if len(s) >= 2:
                slugs.append(s)
    return slugs


def _spotify_genre_seed_slugs(access_token: str) -> list[str]:
    if not access_token:
        return []
    url = "https://api.spotify.com/v1/recommendations/available-genre-seeds"
    payload = _fetch_json(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if not isinstance(payload, dict):
        return []
    seeds = payload.get("genres")
    if not isinstance(seeds, list):
        return []
    out: list[str] = []
    for x in seeds:
        if isinstance(x, str):
            s = slugify_hashtag(x.replace("-", " "))
            if len(s) >= 2:
                out.append(s)
    return out


def _igdb_names(
    access_token: str,
    client_id: str,
    endpoint: str,
    apicalypse: str,
) -> list[str]:
    if not access_token or not client_id:
        return []
    url = f"https://api.igdb.com/v4/{endpoint}"
    body = apicalypse.strip().encode("utf-8")
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "text/plain",
    }
    payload = _fetch_json(url, method="POST", data=body, headers=headers, timeout=25.0)
    if not isinstance(payload, list):
        return []
    names: list[str] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        n = (row.get("name") or "").strip()
        if n:
            names.append(n)
    return names


def _merge_unique(seen: set[str], ordered: list[str], items: list[str]) -> None:
    for s in items:
        if len(s) < 2 or s in seen:
            continue
        seen.add(s)
        ordered.append(s)


def get_hashtag_slug_catalog() -> list[str]:
    """Catálogo deduplicado: TMDB + Spotify + IGDB (+ env local) + fallback."""
    global _CATALOG_CACHE, _CATALOG_CACHE_TS
    now = time.time()
    if _CATALOG_CACHE is not None and now - _CATALOG_CACHE_TS < _CATALOG_TTL_SEC:
        return list(_CATALOG_CACHE)

    creds = fetch_credentials_from_backend()
    tmdb_key = (creds.get("tmdbApiKey") or os.getenv("TMDB_API_KEY") or "").strip()
    spotify_tok = (creds.get("spotifyAccessToken") or "").strip()
    igdb_tok = (creds.get("igdbAccessToken") or "").strip()
    igdb_cid = (creds.get("igdbClientId") or "").strip()

    seen: set[str] = set()
    ordered: list[str] = []

    _merge_unique(seen, ordered, _tmdb_genre_slugs(tmdb_key))
    _merge_unique(seen, ordered, _spotify_genre_seed_slugs(spotify_tok))

    if igdb_tok and igdb_cid:
        for ep, query in (
            ("genres", "fields name; limit 500;"),
            ("keywords", "fields name; limit 400;"),
            ("themes", "fields name; limit 120;"),
        ):
            raw_names = _igdb_names(igdb_tok, igdb_cid, ep, query)
            slugs = [slugify_hashtag(n) for n in raw_names]
            _merge_unique(seen, ordered, [s for s in slugs if s])

    for s in _FALLBACK_SLUGS:
        _merge_unique(seen, ordered, [s])

    _CATALOG_CACHE = ordered
    _CATALOG_CACHE_TS = now
    logger.info("tag_catalog: %s slugs únicos (TMDB/Spotify/IGDB/fallback)", len(ordered))
    return list(ordered)


def format_catalog_for_prompt(max_items: int = 220) -> str:
    """Texto compacto para el prompt: #slug1 #slug2 …"""
    slugs = get_hashtag_slug_catalog()[:max_items]
    return " ".join(f"#{s}" for s in slugs)
