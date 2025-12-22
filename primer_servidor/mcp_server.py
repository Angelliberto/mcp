import os
import json
from fastmcp import FastMCP
from pymongo import MongoClient
from bson import ObjectId
from typing import Any, Union

mcp = FastMCP("Mflix Master")

def limpiar_entrada(datos: Any) -> Any:
    """Extrae el contenido real del texto del usuario evitando metadatos de Telegram."""
    if isinstance(datos, dict):
        if "text" in datos: return datos["text"]
        if "message" in datos and isinstance(datos["message"], dict):
            return datos["message"].get("text", datos)
    return datos

def get_db():
    client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=5000)
    return client[os.getenv("DB_NAME", "sample_mflix")]

def serialize(obj):
    if isinstance(obj, ObjectId): return str(obj)
    if isinstance(obj, dict): return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, list): return [serialize(i) for i in obj]
    return obj

@mcp.tool()
def buscar_peliculas(filtro_json: Union[str, dict]) -> str:
    """Busca en 'movies'. Ej filtro: {"imdb.rating": {"$gt": 8}}"""
    try:
        entrada = limpiar_entrada(filtro_json)
        query = json.loads(entrada) if isinstance(entrada, str) else entrada
        # Limpieza de campos de n8n si se colaron
        for k in ["update_id", "message", "toolCallId"]: query.pop(k, None)
        
        db = get_db()
        # Excluimos plot_embedding por ser un array de 1536 elementos (muy pesado para n8n)
        res = list(db.movies.find(query, {"plot_embedding": 0, "poster": 0}).limit(3))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def obtener_comentarios(movie_id: str) -> str:
    """Busca comentarios por movie_id (ObjectId)."""
    try:
        mid = limpiar_entrada(movie_id)
        db = get_db()
        res = list(db.comments.find({"movie_id": ObjectId(mid)}).limit(5))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def buscar_teatros(ciudad: str) -> str:
    """Busca en 'theaters' por ciudad. Ej: 'Altoona'"""
    try:
        city = limpiar_entrada(ciudad)
        db = get_db()
        # Query exacta según tu esquema: location.address.city
        res = list(db.theaters.find({"location.address.city": city}).limit(3))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))