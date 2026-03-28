import asyncio
import json
import os
import sys
from typing import Any, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse

from fastmcp import FastMCP

import dreamlodge_db as db
from ai_agent import get_ai_agent

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

mcp = FastMCP("Dream Lodge MCP Server")


def _check_internal_secret(request: Request) -> Optional[JSONResponse]:
    expected = os.getenv("MCP_INTERNAL_SECRET", "").strip()
    if not expected:
        return None
    got = request.headers.get("x-mcp-internal-secret", "").strip()
    if got != expected:
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)
    return None


@mcp.tool()
def search_artworks(
    category: Optional[str] = None,
    source: Optional[str] = None,
    title: Optional[str] = None,
    genre: Optional[str] = None,
    limit: int = 20,
    page: int = 1,
) -> dict:
    """
    Busca artworks (obras culturales) en Dream Lodge.

    Args:
        category: cine, música, literatura, arte-visual, videojuegos
        source: IGDB, TMDB, GoogleBooks, MetMuseum, ChicagoArt, Spotify
        title: Título o parte del título
        genre: Término de género (búsqueda en descripción/tags/genre)
        limit: Máximo de resultados (default 20)
        page: Página (default 1)
    """
    return db.search_artworks(
        category=category,
        source=source,
        title=title,
        genre=genre,
        limit=limit,
        page=page,
    )


@mcp.tool()
def get_artwork_by_id(artwork_id: str) -> dict:
    """Obtiene un artwork por ID (_id de Mongo o campo id)."""
    return db.get_artwork_by_id(artwork_id)


@mcp.tool()
def get_user_favorites(user_id: str) -> dict:
    """Favoritos de un usuario."""
    return db.get_user_favorites(user_id)


@mcp.tool()
def get_user_pending(user_id: str) -> dict:
    """Obras pendientes de un usuario."""
    return db.get_user_pending(user_id)


@mcp.tool()
def get_user_ocean_results(user_id: str) -> dict:
    """Resultados OCEAN (Big Five) de un usuario."""
    return db.get_user_ocean_results(user_id)


@mcp.tool()
def search_users(
    email: Optional[str] = None, name: Optional[str] = None, limit: int = 20
) -> dict:
    """Busca usuarios (sin datos sensibles)."""
    return db.search_users(email=email, name=name, limit=limit)


@mcp.tool()
def get_artwork_ocean_results(artwork_id: str) -> dict:
    """OCEAN asociado a un artwork."""
    return db.get_artwork_ocean_results(artwork_id)


@mcp.tool()
def get_statistics() -> dict:
    """Estadísticas generales de Dream Lodge."""
    return db.get_statistics()


@mcp.tool()
def get_user_by_email(email: str) -> dict:
    """Usuario por email (sin datos sensibles)."""
    return db.get_user_by_email(email)


@mcp.tool()
def process_chat_message(
    message: str,
    user_id: Optional[str] = None,
    context_items_json: str = "[]",
    conversation_history_json: str = "[]",
) -> dict:
    """
    Procesa un mensaje de chat con el agente IA (Gemini + Mongo).
    context_items_json y conversation_history_json deben ser JSON en string.
    """
    agent = get_ai_agent()
    try:
        context_items = json.loads(context_items_json or "[]")
        history = json.loads(conversation_history_json or "[]")
    except json.JSONDecodeError as e:
        return {"error": f"JSON inválido: {e}"}
    if not (message or "").strip():
        return {"error": "El mensaje es requerido"}
    return agent.process_message(
        message.strip(),
        user_id=user_id,
        conversation_history=history,
        context_items=context_items if isinstance(context_items, list) else [],
    )


@mcp.tool()
def generate_chat_title(
    user_message: str,
    assistant_message: str = "",
    current_title: str = "",
) -> str:
    """Genera o mejora un título corto en español para la conversación."""
    return get_ai_agent().generate_conversation_title(
        user_message=user_message,
        assistant_message=assistant_message,
        current_title=current_title,
    )


@mcp.tool()
def generate_artistic_description_tool(ocean_result_json: str) -> dict:
    """
    Genera descripción artística a partir de un resultado OCEAN (documento JSON como string).
    """
    agent = get_ai_agent()
    try:
        doc = json.loads(ocean_result_json)
    except json.JSONDecodeError as e:
        return {"error": f"JSON inválido: {e}"}
    if not isinstance(doc, dict):
        return {"error": "ocean_result_json debe ser un objeto JSON"}
    try:
        return agent.generate_artistic_description(doc)
    except ValueError as e:
        return {"error": str(e)}


@mcp.custom_route("/ai/v1/chat/message", methods=["POST"])
async def http_chat_message(request: Request) -> JSONResponse:
    err = _check_internal_secret(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "Cuerpo JSON inválido"}, status_code=400
        )

    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse(
            {"ok": False, "error": "El mensaje es requerido"}, status_code=400
        )

    user_id = body.get("userId")
    context_items = body.get("contextItems") or []
    history = body.get("conversationHistory") or []
    current_title = body.get("currentTitle") or ""

    agent = get_ai_agent()

    def _run():
        return agent.process_message(
            message,
            user_id=user_id,
            conversation_history=history if isinstance(history, list) else [],
            context_items=context_items if isinstance(context_items, list) else [],
        )

    try:
        result = await asyncio.to_thread(_run)
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=500,
        )

    suggested_title = None
    try:
        suggested_title = await asyncio.to_thread(
            agent.generate_conversation_title,
            user_message=message,
            assistant_message=result.get("response") or "",
            current_title=current_title,
        )
    except Exception:
        suggested_title = (current_title or message[:40]) or None

    return JSONResponse(
        {
            "ok": True,
            "data": {
                "response": result.get("response"),
                "toolsUsed": result.get("toolsUsed"),
                "context": result.get("context"),
                "suggestedTitle": suggested_title,
            },
        }
    )


@mcp.custom_route("/ai/v1/ocean/artistic-description", methods=["POST"])
async def http_artistic_description(request: Request) -> JSONResponse:
    err = _check_internal_secret(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "Cuerpo JSON inválido"}, status_code=400
        )

    ocean_result = body.get("oceanResult")
    if not isinstance(ocean_result, dict):
        return JSONResponse(
            {"ok": False, "error": "oceanResult es requerido y debe ser un objeto"},
            status_code=400,
        )

    agent = get_ai_agent()

    def _run():
        return agent.generate_artistic_description(ocean_result)

    try:
        data = await asyncio.to_thread(_run)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    return JSONResponse({"ok": True, "data": data})


@mcp.custom_route("/ai/v1/health", methods=["GET"])
async def http_ai_health(_request: Request) -> JSONResponse:
    agent = get_ai_agent()
    return JSONResponse(
        {
            "ok": True,
            "gemini_configured": agent._configured(),
        }
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    try:
        print(f"Iniciando Dream Lodge MCP Server en puerto {port}")
        print(f"HTTP IA: POST /ai/v1/chat/message , POST /ai/v1/ocean/artistic-description")
    except UnicodeEncodeError:
        print(f"[*] Dream Lodge MCP Server port {port}")
    mcp.run(transport="sse", host="0.0.0.0", port=port)
