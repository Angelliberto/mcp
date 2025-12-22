import os
import json
from fastmcp import FastMCP
from pymongo import MongoClient
from bson import ObjectId
from typing import List, Dict, Any

# MCP Server instance
mcp = FastMCP("Mflix Movie Database")

MONGO_URI = os.getenv("MONGO_URI","mongodb+srv://angellibertoceb:rawUoXCLskO3kqgQ@cluster0.aqndn.mongodb.net/?appName=Cluster0")
DB_NAME = os.getenv("DB_NAME", "sample_mflix")

def obtener_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]

def serialize_mongo(obj):
    """Convierte objetos de Mongo (como ObjectId) a formatos legibles por JSON"""
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, dict):
        return {k: serialize_mongo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_mongo(i) for i in obj]
    return obj

@mcp.tool()
def buscar_peliculas(filtro_json: str, limite: int = 5) -> List[Dict[str, Any]]:
    """
    Busca películas en la colección 'movies'.
    Ejemplo de filtros: {"genres": "Drama"}, {"year": {"$gte": 2010}}, {"cast": "Paul Muni"}
    """
    db = obtener_db()
    try:
        query = json.loads(filtro_json)
        # Excluimos plot_embedding por ser un array gigante innecesario para el agente
        resultados = list(db.movies.find(query, {"plot_embedding": 0}).limit(limite))
        return serialize_mongo(resultados)
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def obtener_comentarios_pelicula(movie_id: str) -> List[Dict[str, Any]]:
    """
    Obtiene los comentarios de una película específica usando su ID.
    """
    db = obtener_db()
    try:
        comentarios = list(db.comments.find({"movie_id": ObjectId(movie_id)}))
        return serialize_mongo(comentarios)
    except Exception as e:
        return [{"error": "ID no válido o error de consulta"}]

@mcp.tool()
def buscar_teatros_por_ciudad(ciudad: str) -> List[Dict[str, Any]]:
    """
    Busca teatros (cines) en una ciudad específica.
    """
    db = obtener_db()
    try:
        teatros = list(db.theaters.find({"location.address.city": ciudad}))
        return serialize_mongo(teatros)
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def estadisticas_mflix() -> Dict[str, Any]:
    """
    Devuelve un conteo general de las colecciones para que el agente conozca el volumen de datos.
    """
    db = obtener_db()
    return {
        "total_peliculas": db.movies.count_documents({}),
        "total_usuarios": db.users.count_documents({}),
        "total_comentarios": db.comments.count_documents({}),
        "total_teatros": db.theaters.count_documents({})
    }

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8080)