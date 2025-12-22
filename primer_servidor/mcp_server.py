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

# --- TOOLS ATÓMICAS (Nombres en Inglés sin ñ) ---

@mcp.tool()
def buscar_por_titulo(titulo: str) -> str:
    """Busca peliculas por titulo parcial o exacto."""
    try:
        db = get_db()
        # Solo título y año, quitamos plot para velocidad
        res = list(db.movies.find({"title": {"$regex": titulo, "$options": "i"}}, {"title": 1, "year": 1, "imdb.rating": 1, "_id": 1}).limit(3))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
def buscar_por_genero(genero_ingles: str) -> str:
    """Busca por genero. Requiere input en INGLÉS (Action, Horror, etc)."""
    try:
        db = get_db()
        res = list(db.movies.find({"genres": genero_ingles}, {"title": 1, "year": 1, "imdb.rating": 1, "_id": 1}).limit(5))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
def buscar_por_year(year: int) -> str: 
    """Busca por año exacto (Input debe ser INT)."""
    try:
        db = get_db()
        res = list(db.movies.find({"year": int(year)}, {"title": 1, "year": 1, "imdb.rating": 1, "_id": 1}).limit(5))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
def buscar_mejores_peliculas() -> str:
    """Busca peliculas con rating > 9 (Para usuarios vagos)."""
    try:
        db = get_db()
        res = list(db.movies.find({"imdb.rating": {"$gte": 9}}, {"title": 1, "year": 1, "imdb.rating": 1, "_id": 1}).limit(5))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
def ver_criticas_por_id(movie_id: str) -> str:
    """Busca comentarios. Requiere el ID de MongoDB."""
    try:
        db = get_db()
        res = list(db.comments.find({"movie_id": ObjectId(movie_id)}).limit(3))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e: return f"Error: {str(e)}"

@mcp.tool()
def localizar_cines(ciudad: str) -> str:
    """Busca cines por nombre de ciudad."""
    try:
        db = get_db()
        res = list(db.theaters.find({"location.address.city": ciudad}).limit(3))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e: return f"Error: {str(e)}"

if __name__ == "__main__":
    # Puerto dinámico o 8080 por defecto
    mcp.run(transport="sse", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))