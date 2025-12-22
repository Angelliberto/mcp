import os
import json
from fastmcp import FastMCP
from pymongo import MongoClient
from bson import ObjectId

# Servidor con el nombre de tu prompt
mcp = FastMCP("Mflix Master")

def get_db():
    client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=5000)
    return client[os.getenv("DB_NAME", "sample_mflix")]

def serialize(obj):
    if isinstance(obj, ObjectId): return str(obj)
    if isinstance(obj, dict): return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, list): return [serialize(i) for i in obj]
    return obj

@mcp.tool()
def buscar_peliculas(filtro_json: str) -> str:
    """Busca películas usando un JSON de MongoDB. (Ej: {"year": 1995})"""
    try:
        db = get_db()
        query = json.loads(filtro_json)
        # Excluimos campos pesados para evitar que n8n se cuelgue por exceso de datos
        res = list(db.movies.find(query, {"plot_embedding": 0, "poster": 0}).limit(3))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e:
        return f"Error en consulta: {str(e)}"

@mcp.tool()
def obtener_comentarios_pelicula(movie_id: str) -> str:
    """Obtiene comentarios usando el ID de la película."""
    try:
        db = get_db()
        res = list(db.comments.find({"movie_id": ObjectId(movie_id)}).limit(5))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def buscar_teatros_por_ciudad(ciudad: str) -> str:
    """Busca cines por ciudad. (Ej: 'Altoona')"""
    try:
        db = get_db()
        res = list(db.theaters.find({"location.address.city": ciudad}).limit(3))
        return json.dumps(serialize(res), ensure_ascii=False)
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    mcp.run(transport="sse", host="0.0.0.0", port=port)