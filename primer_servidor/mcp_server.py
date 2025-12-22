import os
import json
from fastmcp import FastMCP
from pymongo import MongoClient
from bson import ObjectId
from typing import Any, Union

mcp = FastMCP("Mflix Ultra Logic")

def get_db():
    client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=5000)
    return client[os.getenv("DB_NAME", "sample_mflix")]

def serialize(obj):
    if isinstance(obj, ObjectId): return str(obj)
    if isinstance(obj, dict): return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, list): return [serialize(i) for i in obj]
    return obj

# --- TOOLS ESPECÍFICAS PARA CADA PREGUNTA ---

@mcp.tool()
def buscar_por_titulo(titulo: str) -> str:
    """Usa esta tool cuando el usuario dé el nombre de una película."""
    db = get_db()
    res = list(db.movies.find({"title": {"$regex": titulo, "$options": "i"}}, {"plot_embedding": 0, "poster": 0}).limit(3))
    return json.dumps(serialize(res), ensure_ascii=False)

@mcp.tool()
def buscar_por_genero(genero_ingles: str) -> str:
    """Usa esta tool cuando el usuario pida un género (Action, Horror, Comedy, etc)."""
    db = get_db()
    res = list(db.movies.find({"genres": genero_ingles}, {"plot_embedding": 0, "poster": 0}).limit(5))
    return json.dumps(serialize(res), ensure_ascii=False)

@mcp.tool()
def buscar_por_año(año: int) -> str:
    """Usa esta tool cuando el usuario mencione un año específico."""
    db = get_db()
    res = list(db.movies.find({"year": año}, {"plot_embedding": 0, "poster": 0}).limit(5))
    return json.dumps(serialize(res), ensure_ascii=False)

@mcp.tool()
def buscar_mejores_peliculas() -> str:
    """Usa esta tool cuando pregunten '¿qué hay?' o 'dame una lista' o 'las mejores'."""
    db = get_db()
    res = list(db.movies.find({"imdb.rating": {"$gte": 9}}, {"plot_embedding": 0, "poster": 0}).limit(5))
    return json.dumps(serialize(res), ensure_ascii=False)

@mcp.tool()
def ver_criticas_por_id(movie_id: str) -> str:
    """Usa esta tool para obtener comentarios de una película usando su ID."""
    db = get_db()
    res = list(db.comments.find({"movie_id": ObjectId(movie_id)}).limit(5))
    return json.dumps(serialize(res), ensure_ascii=False)

@mcp.tool()
def localizar_cines(ciudad: str) -> str:
    """Usa esta tool para buscar teatros en una ciudad específica."""
    db = get_db()
    res = list(db.theaters.find({"location.address.city": ciudad}).limit(3))
    return json.dumps(serialize(res), ensure_ascii=False)

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))