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

# --- TOOLS (NOMBRES SOLO EN INGLÉS/ASCII) ---

@mcp.tool()
def buscar_por_titulo(titulo: str) -> str:
    """Busca por titulo exacto o parcial."""
    try:
        db = get_db()
        res = list(db.movies.find({"title": {"$regex": titulo, "$options": "i"}}, {"plot_embedding": 0, "poster": 0}).limit(3))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
def buscar_por_genero(genero_ingles: str) -> str:
    """Busca por genero (Action, Horror, etc)."""
    try:
        db = get_db()
        res = list(db.movies.find({"genres": genero_ingles}, {"plot_embedding": 0, "poster": 0}).limit(5))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
def buscar_por_year(year: int) -> str: 
    """Busca por año (Renombrado para evitar la ñ)."""
    try:
        db = get_db()
        # Aseguramos que sea int
        year_int = int(year)
        res = list(db.movies.find({"year": year_int}, {"plot_embedding": 0, "poster": 0}).limit(5))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
def buscar_mejores_peliculas() -> str:
    """Busca peliculas con rating > 9."""
    try:
        db = get_db()
        res = list(db.movies.find({"imdb.rating": {"$gte": 9}}, {"plot_embedding": 0, "poster": 0}).limit(5))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
def ver_criticas_por_id(movie_id: str) -> str:
    """Busca comentarios por ID."""
    try:
        db = get_db()
        res = list(db.comments.find({"movie_id": ObjectId(movie_id)}).limit(5))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
def localizar_cines(ciudad: str) -> str:
    """Busca cines por ciudad."""
    try:
        db = get_db()
        res = list(db.theaters.find({"location.address.city": ciudad}).limit(3))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e: return f"Error: {str(e)}"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    mcp.run(transport="sse", host="0.0.0.0", port=port)