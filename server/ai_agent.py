"""
Agente IA Dream Lodge: Gemini + herramientas Mongo (lógica migrada desde aiAgent.js).
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Optional

import dreamlodge_db as db
from system_prompts import build_system_prompt
from web_search import build_artistic_web_context, build_curator_context_from_serper

logger = logging.getLogger("dreamlodge.ai")

_WORK_CAT_ALLOWED = frozenset(
    {"cine", "musica", "literatura", "videojuegos", "arte-visual"}
)
_WORK_CAT_ALIAS = {
    "pelicula": "cine",
    "películas": "cine",
    "series": "cine",
    "serie": "cine",
    "tv": "cine",
    "film": "cine",
    "movie": "cine",
    "música": "musica",
    "music": "musica",
    "album": "musica",
    "libro": "literatura",
    "libros": "literatura",
    "book": "literatura",
    "juego": "videojuegos",
    "juegos": "videojuegos",
    "game": "videojuegos",
    "games": "videojuegos",
    "arte": "arte-visual",
    "art": "arte-visual",
    "pintura": "arte-visual",
}


def normalize_work_candidate_rows(
    raw_list: Any, *, max_items: int = 24
) -> list[dict[str, str]]:
    """Normaliza filas {category, title, creator?} para feed y descripción artística."""
    if not isinstance(raw_list, list):
        return []
    cleaned: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_list[:max_items]:
        if not isinstance(item, dict):
            continue
        cat = str(item.get("category") or "").strip().lower()
        cat = cat.replace(" ", "").replace("_", "-")
        if cat in _WORK_CAT_ALIAS:
            cat = _WORK_CAT_ALIAS[cat]
        if cat not in _WORK_CAT_ALLOWED:
            continue
        title = str(item.get("title") or "").strip()
        if len(title) < 2:
            continue
        creator = str(item.get("creator") or "").strip()
        key = (cat, title.lower())
        if key in seen:
            continue
        seen.add(key)
        row: dict[str, str] = {"category": cat, "title": title[:200]}
        if creator:
            row["creator"] = creator[:120]
        cleaned.append(row)
    return cleaned


def _format_exception_for_client(exc: BaseException, max_len: int = 800) -> str:
    """Texto seguro para mostrar al cliente (sin sustituir logs completos)."""
    parts: list[str] = []
    cur: Optional[BaseException] = exc
    depth = 0
    while cur is not None and depth < 4:
        s = str(cur).strip()
        if s and s not in parts:
            parts.append(s)
        cur = cur.__cause__ or cur.__context__
        depth += 1
    msg = " | ".join(parts) if parts else type(exc).__name__
    if len(msg) > max_len:
        return msg[: max_len - 1] + "…"
    return msg


def _trait_total(scores: dict, key: str) -> float:
    """Extrae el total 0–5 de un rasgo OCEAN aunque venga como dict o número."""
    v = scores.get(key)
    if isinstance(v, dict):
        t = v.get("total")
        try:
            return float(t) if t is not None else 0.0
        except (TypeError, ValueError):
            return 0.0
    if isinstance(v, (int, float)):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
    return 0.0

try:
    import google.generativeai as genai

    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


def _env_models() -> list[str]:
    """Orden: env GEMINI_MODEL primero, luego modelos que Google sigue ofreciendo a cuentas nuevas."""
    raw = os.getenv("GEMINI_MODEL")
    candidates = [
        raw,
        # 2.5: recomendado para API key / nuevos proyectos (2.0-flash ya no para usuarios nuevos)
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-1.0-pro",
    ]
    return [m for m in candidates if m]


class DreamLodgeAIAgent:
    def __init__(self) -> None:
        self.api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
        self._models_cache: Optional[list[str]] = None
        if _GENAI_AVAILABLE and self.api_key:
            genai.configure(api_key=self.api_key)

    def _configured(self) -> bool:
        return bool(_GENAI_AVAILABLE and self.api_key)

    def _list_generate_models(self) -> list[str]:
        if not self._configured():
            return []
        if self._models_cache is not None:
            return self._models_cache
        try:
            names = []
            for m in genai.list_models():
                methods = getattr(m, "supported_generation_methods", None) or []
                if "generateContent" in methods:
                    name = str(m.name or "").replace("models/", "")
                    if name:
                        names.append(name)
            self._models_cache = names
            return names
        except Exception:
            return []

    def _model_candidates(self) -> list[str]:
        preferred = _env_models()
        available = self._list_generate_models()
        if available:
            ordered = [m for m in preferred if m in available]
            rest = [m for m in available if m not in ordered]
            return ordered + rest
        return preferred

    def _is_not_supported(self, err: Exception) -> bool:
        msg = str(err).lower()
        s = getattr(err, "status", None)
        return (
            s == 404
            or "not found" in msg
            or "not_found" in msg
            or "statuscode.not_found" in msg
            or "no longer available" in msg
            or "not supported" in msg
            or "generatecontent" in msg
        )

    def _is_quota(self, err: Exception) -> bool:
        msg = str(err).lower()
        s = getattr(err, "status", None)
        return s == 429 or "quota" in msg or "rate limit" in msg or "429" in msg

    def generate_with_gemini(
        self,
        prompt: str,
        *,
        purpose: str = "respuesta",
        timeout_ms: int = 40000,
    ) -> str:
        if not self._configured():
            raise RuntimeError(
                "El servicio de IA no está configurado (Gemini no disponible)."
            )

        candidates = self._model_candidates()
        if not candidates:
            raise RuntimeError(
                "No hay modelos Gemini configurados. Define GEMINI_API_KEY o GEMINI_MODEL."
            )

        tried: list[str] = []
        last_err: Optional[Exception] = None

        for model_name in candidates:
            tried.append(model_name)
            try:
                model = genai.GenerativeModel(model_name)

                def _call():
                    return model.generate_content(prompt)

                with ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(_call)
                    try:
                        result = fut.result(timeout=max(timeout_ms / 1000, 1))
                    except FuturesTimeout as te:
                        raise RuntimeError(
                            f"Timeout generando {purpose} con {model_name}"
                        ) from te

                text = ""
                if result:
                    try:
                        text = (result.text or "").strip()
                    except ValueError:
                        for cand in getattr(result, "candidates", None) or []:
                            content = getattr(cand, "content", None)
                            for part in getattr(content, "parts", None) or []:
                                t = getattr(part, "text", None)
                                if t:
                                    text += t
                        text = text.strip()
                if not text:
                    raise RuntimeError(
                        f"El modelo {model_name} no generó ninguna respuesta."
                    )
                return text
            except Exception as e:
                last_err = e
                if self._is_not_supported(e):
                    continue
                if self._is_quota(e):
                    continue
                raise

        if last_err:
            detail = _format_exception_for_client(last_err)
            raise RuntimeError(
                f"Gemini falló tras probar: {', '.join(tried)}. {detail}"
            ) from last_err
        raise RuntimeError(
            f"No hay modelos Gemini compatibles. Modelos probados: {', '.join(tried)}"
        )

    @staticmethod
    def normalize_for_intent(text: str) -> str:
        if not text or not isinstance(text, str):
            return ""
        t = (
            unicodedata.normalize("NFD", text.lower().strip())
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        return re.sub(r"\s+", " ", t)

    def extract_search_params(self, message: str) -> dict[str, Any]:
        params: dict[str, Any] = {}
        normalized = self.normalize_for_intent(message)

        category_map = {
            "cine": [
                "cine",
                "pelicula",
                "peliculas",
                "peli",
                "pelis",
                "movie",
                "film",
                "films",
                "cinema",
            ],
            "música": [
                "musica",
                "cancion",
                "canciones",
                "song",
                "songs",
                "album",
                "albums",
                "disco",
                "musical",
            ],
            "literatura": [
                "literatura",
                "libro",
                "libros",
                "book",
                "books",
                "novela",
                "novelas",
                "leer",
                "lectura",
            ],
            "arte-visual": [
                "arte",
                "artista",
                "artistas",
                "pintura",
                "pinturas",
                "art",
                "visual",
                "cuadro",
                "cuadros",
            ],
            "videojuegos": [
                "videojuego",
                "videojuegos",
                "juego",
                "juegos",
                "game",
                "games",
                "gaming",
            ],
        }
        for cat, keywords in category_map.items():
            for kw in keywords:
                if kw in normalized:
                    params["category"] = cat
                    break
            if "category" in params:
                break

        generos = {
            "drama": ["drama", "dramatico", "dramatica", "dramaticos", "dramaticas"],
            "comedia": [
                "comedia",
                "comico",
                "comica",
                "comicos",
                "comicas",
                "humor",
                "gracioso",
                "graciosa",
            ],
            "ciencia ficción": [
                "ciencia ficcion",
                "scifi",
                "sci-fi",
                "futurista",
                "futuro",
                "espacial",
            ],
            "fantasía": [
                "fantasia",
                "fantasioso",
                "fantasiosa",
                "magia",
                "magico",
                "magica",
            ],
            "terror": ["terror", "horror", "miedo", "escalofriante", "suspenso"],
            "acción": ["accion", "aventura", "aventurero", "aventurera"],
            "romance": ["romance", "romantico", "romantica", "amor", "amoroso", "amorosa"],
            "thriller": ["thriller", "suspense", "intriga", "misterio"],
        }
        for genero, keywords in generos.items():
            for kw in keywords:
                if kw in normalized:
                    params["genre"] = genero
                    break
            if "genre" in params:
                break

        for source in ["tmdb", "spotify", "igdb", "googlebooks"]:
            if source in normalized:
                params["source"] = source.upper()
                break

        title_match = (
            re.search(r'"([^"]+)"', message)
            or re.search(r"título[:\s]+(.+?)(?:\.|$)", message, re.I)
            or re.search(r"llamad[oa][:\s]+(.+?)(?:\.|$)", message, re.I)
            or re.search(r"titulad[oa][:\s]+(.+?)(?:\.|$)", message, re.I)
        )
        if title_match:
            params["title"] = title_match.group(1).strip()

        return params

    @staticmethod
    def extract_artwork_id(message: str, context_items: list | None) -> Optional[str]:
        context_items = context_items or []
        if context_items:
            first = context_items[0]
            if isinstance(first, dict) and first.get("id"):
                return str(first["id"])
        m = re.search(r"id[:\s]+([a-zA-Z0-9-_]+)", message, re.I)
        if m:
            return m.group(1)
        return None

    def analyze_message_and_select_tools(
        self, user_message: str, *, context_items: list | None = None
    ) -> list[str]:
        context_items = context_items or []
        tools: list[str] = []
        sp = self.extract_search_params(user_message)
        has_structured = bool(
            sp.get("category") or sp.get("genre") or sp.get("source") or sp.get("title")
        )
        artwork_id = self.extract_artwork_id(user_message, context_items)
        if has_structured:
            tools.append("search_artworks")
        if artwork_id:
            tools.append("get_artwork_by_id")
        if context_items and "get_artwork_by_id" not in tools:
            tools.append("get_artwork_by_id")
        return tools

    def execute_tools(
        self,
        tools: list[str],
        user_message: str,
        *,
        user_id: Optional[str] = None,
        context_items: list | None = None,
    ) -> dict[str, Any]:
        context_items = context_items or []
        results: dict[str, Any] = {}

        for tool in tools:
            try:
                if tool == "search_artworks":
                    sp = self.extract_search_params(user_message)
                    results["artworks"] = db.search_artworks(
                        category=sp.get("category"),
                        source=sp.get("source"),
                        title=sp.get("title"),
                        genre=sp.get("genre"),
                        limit=20,
                        page=1,
                    )
                elif tool == "get_user_ocean_results" and user_id:
                    results["oceanResults"] = db.get_user_ocean_results(user_id)
                elif tool == "get_user_favorites" and user_id:
                    results["favorites"] = db.get_user_favorites(user_id)
                elif tool == "get_artwork_by_id":
                    aid = self.extract_artwork_id(user_message, context_items)
                    if aid:
                        results["artwork"] = db.get_artwork_by_id(aid)
            except Exception as e:
                print(f"Error ejecutando herramienta {tool}: {e}")

        return results

    def generate_response(
        self,
        user_message: str,
        system_prompt: str,
        conversation_history: list,
        tool_results: dict[str, Any],
    ) -> str:
        context_text = system_prompt + "\n\n"
        if conversation_history:
            context_text += "Historial de conversación:\n"
            for msg in conversation_history[-5:]:
                role = msg.get("role", "")
                content = msg.get("content", "")
                label = "Usuario" if role == "user" else "Asistente"
                context_text += f"- {label}: {content}\n"
            context_text += "\n"

        aw = tool_results.get("artworks") or {}
        if aw.get("data") and len(aw["data"]) > 0:
            artworks = aw["data"]
            context_text += f"Obras encontradas en la base de datos de Dream Lodge ({len(artworks)} resultados):\n"
            for i, artwork in enumerate(artworks[:10], 1):
                context_text += f"{i}. {artwork.get('title')} ({artwork.get('category')})"
                if artwork.get("creator"):
                    context_text += f" - Por {artwork.get('creator')}"
                if artwork.get("year"):
                    context_text += f" ({artwork.get('year')})"
                desc = artwork.get("description") or ""
                if desc:
                    context_text += f"\n   {desc[:200]}"
                if artwork.get("rating") is not None:
                    context_text += f"\n   Calificación: {artwork.get('rating')}/10"
                context_text += "\n"
            context_text += "\nIMPORTANTE: Estas obras están en la base de datos de Dream Lodge. Preséntalas de manera atractiva y específica, mencionando detalles relevantes.\n\n"

        one = tool_results.get("artwork") or {}
        if one.get("data"):
            artwork = one["data"]
            context_text += "Información sobre la obra solicitada:\n"
            context_text += f"Título: {artwork.get('title')}\n"
            context_text += f"Categoría: {artwork.get('category')}\n"
            if artwork.get("creator"):
                context_text += f"Creador: {artwork.get('creator')}\n"
            if artwork.get("year"):
                context_text += f"Año: {artwork.get('year')}\n"
            if artwork.get("description"):
                context_text += f"Descripción: {artwork.get('description')}\n"
            if artwork.get("rating") is not None:
                context_text += f"Calificación: {artwork.get('rating')}/10\n"
            context_text += "\n"

        oc = tool_results.get("oceanResults") or {}
        if oc.get("data"):
            context_text += "El usuario ha completado su perfil de personalidad OCEAN. Puedes hacer recomendaciones personalizadas.\n\n"

        fav = tool_results.get("favorites") or {}
        fd = fav.get("data")
        if fd:
            flist = fd if isinstance(fd, list) else [fd]
            if flist:
                context_text += f"Obras favoritas del usuario ({len(flist)}):\n"
                for x in flist[:5]:
                    context_text += f"- {x.get('title') or x.get('artworkId')}\n"
                context_text += "\n"

        full_prompt = f"{context_text}Mensaje del usuario: {user_message}\n\n"

        if aw.get("data") and len(aw["data"]) > 0:
            full_prompt += f"""INSTRUCCIONES IMPORTANTES:
- Has encontrado {len(aw["data"])} obra(s) en la base de datos.
- Preséntalas de manera atractiva y específica, mencionando título, creador, año y categoría.
- Explica brevemente por qué cada obra podría interesarle al usuario.
"""
            if oc.get("data"):
                full_prompt += "- Conecta las recomendaciones con su perfil de personalidad OCEAN si es relevante.\n"
            full_prompt += "- Si hay muchas obras, menciona las 3-5 más relevantes y ofrece mostrar más si quiere.\n"
            full_prompt += "- Sé entusiasta y específico, evita listas genéricas.\n\n"
        elif oc.get("data"):
            full_prompt += """INSTRUCCIONES IMPORTANTES:
- El usuario tiene un perfil de personalidad OCEAN disponible.
- Haz recomendaciones personalizadas basándote en sus rasgos de personalidad.
- Sé específico: menciona géneros, estilos o tipos de contenido que se alineen con su perfil.
- Explica brevemente por qué estas recomendaciones encajan con su personalidad.
- Si no tienes obras específicas en la base de datos, usa tu conocimiento general para sugerir contenido conocido.
- NUNCA digas "no tengo información" - siempre ofrece algo útil.

"""
        elif fd and isinstance(fd, list) and len(fd) > 0:
            full_prompt += f"""INSTRUCCIONES IMPORTANTES:
- Conoces los gustos del usuario a través de sus {len(fd)} favorito(s).
- Haz recomendaciones similares o complementarias basándote en sus favoritos.
- Sé específico: menciona obras concretas, géneros o estilos relacionados.
- Si no tienes obras específicas en la base, usa tu conocimiento para sugerir contenido conocido que sea similar.

"""
        else:
            full_prompt += """INSTRUCCIONES IMPORTANTES:
- Responde siempre con algo útil y específico.
- NUNCA digas "no pude encontrar", "no pude satisfacer tu solicitud" o "no entendí" como mensaje principal.
- Interpreta la intención aunque haya typos o escritura informal.
- Si no tienes datos en la base de datos, usa tu conocimiento general para sugerir contenido conocido, géneros o estilos.
- Sé proactivo: ofrece opciones concretas o haz preguntas útiles para refinar la búsqueda.
- Mantén un tono amigable y entusiasta.

"""

        full_prompt += "Responde de manera natural, conversacional y útil. Sé específico y evita respuestas genéricas o vagas."

        return self.generate_with_gemini(
            full_prompt, purpose="respuesta de chat", timeout_ms=45000
        )

    def process_message(
        self,
        user_message: str,
        *,
        user_id: Optional[str] = None,
        conversation_history: list | None = None,
        context_items: list | None = None,
    ) -> dict[str, Any]:
        conversation_history = conversation_history or []
        context_items = context_items or []

        user_info = None
        ocean_results: list | None = None
        favorites: list = []

        if user_id:
            user_info = db.get_user_basic_info(user_id)
            if user_info:
                o = db.get_user_ocean_results(user_id)
                if o.get("data"):
                    ocean_results = o["data"] if isinstance(o["data"], list) else [o["data"]]
                f = db.get_user_favorites(user_id)
                if f.get("data"):
                    favorites = f["data"]

        system_prompt = build_system_prompt(
            context_items=context_items,
            ocean_results=ocean_results or [],
            favorites=favorites,
            user_info=user_info,
        )

        tools_to_use = self.analyze_message_and_select_tools(
            user_message, context_items=context_items
        )
        tool_results = self.execute_tools(
            tools_to_use,
            user_message,
            user_id=user_id,
            context_items=context_items,
        )

        sp = self.extract_search_params(user_message)
        should_search = (
            "search_artworks" in tools_to_use
            or "get_artwork_by_id" in tools_to_use
            or bool(context_items)
        )
        if should_search and sp:
            art = tool_results.get("artworks") or {}
            if not art.get("data"):
                extra = db.search_artworks(
                    category=sp.get("category"),
                    source=sp.get("source"),
                    title=sp.get("title"),
                    genre=sp.get("genre"),
                    limit=20,
                    page=1,
                )
                if extra.get("data"):
                    tool_results["artworks"] = extra

        if ocean_results:
            tool_results["oceanResults"] = {"data": ocean_results}
        if favorites:
            tool_results["favorites"] = {"data": favorites}

        if not self._configured():
            raise RuntimeError(
                "El servicio de IA no está configurado (Gemini no disponible). Configura GEMINI_API_KEY."
            )

        ai_response = self.generate_response(
            user_message, system_prompt, conversation_history, tool_results
        )

        return {
            "response": ai_response,
            "toolsUsed": tools_to_use,
            "context": {
                "hasOceanResults": bool(ocean_results),
                "favoritesCount": len(favorites),
                "contextItemsCount": len(context_items),
                "artworksFound": len((tool_results.get("artworks") or {}).get("data") or []),
            },
        }

    def generate_conversation_title(
        self,
        *,
        user_message: str,
        assistant_message: str = "",
        current_title: str = "",
    ) -> str:
        fallback = "Nueva conversación"
        um = (user_message or "").strip()
        if not um:
            return fallback
        if not self._configured():
            ct = (current_title or "").strip()
            return ct or um[:40]

        prompt = "\n".join(
            [
                "Genera o mejora un título MUY corto en español para una conversación de chat.",
                "Reglas:",
                "- Máximo 5 palabras.",
                "- Sin comillas, sin emojis, sin punto final.",
                "- Debe sonar natural y específico al contexto.",
                f'Título actual: "{current_title}"' if current_title else "Título actual: (sin título útil aún)",
                f'Último mensaje del usuario: "{um}"',
                (
                    f'Última respuesta del asistente: "{assistant_message[:240]}"'
                    if assistant_message
                    else ""
                ),
                "Devuelve SOLO el título.",
            ]
        )
        try:
            text = self.generate_with_gemini(
                prompt, purpose="título de conversación", timeout_ms=12000
            )
            cleaned = re.sub(r'^["\'`]+|["\'`]+$', "", (text or "").strip())
            cleaned = re.sub(r"\s+", " ", cleaned).strip()[:60]
            return cleaned or (current_title or um[:40])
        except Exception:
            return (current_title or um[:40])

    def generate_artistic_description(self, ocean_result: dict) -> dict[str, Any]:
        scores = ocean_result.get("scores")
        if not scores or not isinstance(scores, dict):
            logger.warning(
                "generate_artistic_description: scores ausente o no es dict, keys ocean=%s",
                list(ocean_result.keys()) if isinstance(ocean_result, dict) else type(ocean_result),
            )
            raise ValueError("Resultados OCEAN no válidos")

        o = _trait_total(scores, "openness")
        c = _trait_total(scores, "conscientiousness")
        e = _trait_total(scores, "extraversion")
        a = _trait_total(scores, "agreeableness")
        n = _trait_total(scores, "neuroticism")
        test_type = ocean_result.get("testType")

        if not self._configured():
            raise RuntimeError(
                "GEMINI_API_KEY no está configurada en el servidor MCP; no hay descripción artística sin el modelo."
            )

        logger.info(
            "artistic_description: totals O=%.2f C=%.2f E=%.2f A=%.2f N=%.2f testType=%s",
            o,
            c,
            e,
            a,
            n,
            test_type,
        )

        sub = ""
        if test_type == "deep":
            parts = []
            for dim, dim_scores in scores.items():
                if not isinstance(dim_scores, dict):
                    continue
                subfacets = [k for k in dim_scores.keys() if k != "total"]
                if subfacets:
                    line = ", ".join(
                        f"{sf}: {dim_scores.get(sf, 'N/A')}" for sf in subfacets
                    )
                    parts.append(f"- {dim}: {line}")
            if parts:
                sub = "Subfacetas detalladas:\n" + "\n".join(parts) + "\n"

        web_block, web_used = build_artistic_web_context(
            o, c, e, a, n, test_type, sub[:400] if sub else ""
        )

        logger.info(
            "artistic_description: web_context_chars=%s web_used=%s",
            len(web_block or ""),
            web_used,
        )

        prompt = f"""Eres curador cultural. El usuario hizo el test OCEAN (Big Five). Tu tarea es proponer OBRAS CONCRETAS (reales, buscables en TMDB, Spotify, Google Books, IGDB o museos) que encajen con su perfil, usando los fragmentos de búsqueda web cuando aporten títulos o listas fiables.

Perfil numérico (0-5):
- Apertura {float(o):.2f}, Responsabilidad {float(c):.2f}, Extraversión {float(e):.2f}, Amabilidad {float(a):.2f}, Neuroticismo {float(n):.2f}

{sub}
Fragmentos web (títulos y listas; prioriza obras que aparezcan aquí si encajan con OCEAN):
{web_block or "(Sin resultados web: elige obras muy conocidas y coherentes con el perfil.)"}

En tu razonamiento interno (no lo escribas): elige 10-16 obras reales mezclando categorías.

Responde SOLO JSON válido, sin markdown:
{{
  "profile": "nombre corto del perfil artístico",
  "description": "2-3 párrafos en español, tono cálido",
  "recommendations": ["3-6 frases cortas; puede incluir nombres de obras"],
  "suggestedWorks": [
    {{"category":"cine","title":"Título exacto buscable","creator":"director o autor opcional"}}
  ]
}}

Reglas suggestedWorks:
- category exactamente: cine, musica, literatura, videojuegos, arte-visual
- Títulos reales; mezcla categorías."""

        try:
            text = self.generate_with_gemini(
                prompt, purpose="descripción artística", timeout_ms=55000
            )
        except Exception as ex:
            logger.exception("artistic_description: fallo al llamar a Gemini")
            detail = _format_exception_for_client(ex)
            raise RuntimeError(
                f"No se pudo generar la descripción con el modelo de IA. {detail}"
            ) from ex

        m = re.search(r"\{[\s\S]*\}", text or "")
        if not m:
            logger.warning(
                "artistic_description: respuesta sin JSON, primeros 300 chars: %s",
                (text or "")[:300],
            )
            raise RuntimeError(
                "El modelo no devolvió un JSON reconocible. Vuelve a intentarlo."
            )

        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError as ex:
            logger.warning("artistic_description: JSON inválido: %s", ex)
            raise RuntimeError(
                f"El modelo devolvió JSON inválido: {ex}"
            ) from ex

        if not isinstance(parsed, dict):
            raise RuntimeError("La respuesta del modelo no es un objeto JSON.")

        profile = (parsed.get("profile") or "").strip()
        description = (parsed.get("description") or "").strip()
        if not profile or not description:
            raise RuntimeError(
                "La respuesta del modelo está incompleta (falta profile o description)."
            )

        rec = parsed.get("recommendations")
        if rec is not None and not isinstance(rec, list):
            raise RuntimeError("El campo recommendations debe ser una lista.")
        if rec is None:
            parsed["recommendations"] = []

        raw_works = parsed.get("suggestedWorks")
        if isinstance(raw_works, list):
            works = normalize_work_candidate_rows(raw_works, max_items=20)
            parsed["suggestedWorks"] = works
            for w in works:
                logger.info(
                    "artistic_suggested_work: category=%s title=%s creator=%s",
                    w.get("category"),
                    w.get("title"),
                    w.get("creator", "") or "",
                )
            logger.info(
                "artistic_suggested_works_summary: %s",
                json.dumps(works, ensure_ascii=False),
            )
        else:
            parsed["suggestedWorks"] = []

        logger.info(
            "artistic_description: OK profile=%s web_used=%s works=%s",
            profile,
            web_used,
            len(parsed.get("suggestedWorks") or []),
        )
        return parsed

    def curate_personalized_feed(
        self,
        ocean_result: dict,
        artistic_profile: dict | None = None,
    ) -> dict[str, Any]:
        """
        1) Contexto web opcional (Serper).
        2) Gemini produce candidatos {category, title, creator?} para resolver luego en APIs TMDB/Spotify/IGDB/Books/Met.
        """
        scores = ocean_result.get("scores")
        if not scores or not isinstance(scores, dict):
            return {"candidates": [], "webSearchUsed": False, "reason": "no_ocean_scores"}

        if not self._configured():
            return {"candidates": [], "webSearchUsed": False, "reason": "no_gemini"}

        o = _trait_total(scores, "openness")
        c = _trait_total(scores, "conscientiousness")
        e = _trait_total(scores, "extraversion")
        a = _trait_total(scores, "agreeableness")
        n = _trait_total(scores, "neuroticism")

        personality_line = (
            f"openness {o:.1f} conscientiousness {c:.1f} extraversion {e:.1f} "
            f"agreeableness {a:.1f} neuroticism {n:.1f}"
        )
        web_block, web_used = build_curator_context_from_serper(personality_line)

        art_extra = ""
        if artistic_profile and isinstance(artistic_profile, dict):
            prof = (artistic_profile.get("profile") or "").strip()
            desc = (artistic_profile.get("description") or "").strip()[:500]
            recs = artistic_profile.get("recommendations")
            rec_line = ""
            if isinstance(recs, list) and recs:
                rec_line = "Sugerencias previas: " + "; ".join(
                    str(x) for x in recs[:6] if x
                )
            art_extra = f"\nPerfil artístico existente: {prof}\n{desc}\n{rec_line}\n"

        prompt = f"""Eres curador cultural para una app de descubrimiento (cine, series, música, libros, videojuegos, arte).

Perfil OCEAN del usuario (escala 0-5):
- Apertura {o:.2f}, Responsabilidad {c:.2f}, Extraversión {e:.2f}, Amabilidad {a:.2f}, Neuroticismo {n:.2f}
{art_extra}
Fragmentos recientes de búsqueda web (pueden incluir títulos reales; úsalos si encajan con el perfil):
{web_block or "(Sin resultados web: elige obras clásicas o muy conocidas, títulos exactos en español o en el título original más reconocible.)"}

TAREA: Devuelve SOLO un JSON válido, sin markdown ni texto alrededor, con esta forma:
{{"candidates":[{{"category":"cine","title":"Nombre exacto de la obra","creator":"autor o director opcional"}}, ...]}}

Reglas estrictas:
- "category" debe ser exactamente uno de: cine, musica, literatura, videojuegos, arte-visual
- Entre 14 y 20 elementos en total; mezcla las categorías (varios de cada tipo).
- Solo obras reales que existan (película, serie, álbum, libro, videojuego, artista u obra de arte).
- "title" debe ser el título principal buscable en TMDB, Spotify, Google Books, IGDB o museos.
- Para arte-visual usa nombre de artista + obra si aplica, o solo artista reconocible.
- No incluyas explicaciones ni campos extra fuera de "candidates".
"""

        try:
            text = self.generate_with_gemini(
                prompt, purpose="curación feed personalizado", timeout_ms=55000
            )
        except Exception as ex:
            logger.exception("curate_feed: fallo Gemini")
            detail = _format_exception_for_client(ex)
            raise RuntimeError(
                f"No se pudo curar el feed con el modelo. {detail}"
            ) from ex

        m = re.search(r"\{[\s\S]*\}", text or "")
        if not m:
            logger.warning("curate_feed: sin JSON en respuesta")
            return {"candidates": [], "webSearchUsed": web_used, "reason": "bad_model_json"}

        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError as ex:
            logger.warning("curate_feed: JSON inválido %s", ex)
            return {"candidates": [], "webSearchUsed": web_used, "reason": "json_error"}

        raw_list = parsed.get("candidates")
        if not isinstance(raw_list, list):
            return {"candidates": [], "webSearchUsed": web_used, "reason": "no_candidates"}

        cleaned = normalize_work_candidate_rows(raw_list, max_items=24)

        logger.info(
            "curate_feed: %s candidatos web_used=%s", len(cleaned), web_used
        )
        return {"candidates": cleaned, "webSearchUsed": web_used}


_agent: Optional[DreamLodgeAIAgent] = None


def get_ai_agent() -> DreamLodgeAIAgent:
    global _agent
    if _agent is None:
        _agent = DreamLodgeAIAgent()
    return _agent
