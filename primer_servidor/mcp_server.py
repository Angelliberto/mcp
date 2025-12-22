import os
import json
from fastmcp import FastMCP
from pymongo import MongoClient
from bson import ObjectId

# 1. SERVIDOR INSTANTÁNEO
mcp = FastMCP("Mflix Movie Database")

# Función interna para conectar solo cuando sea necesario
def get_db():
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        return None
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
    return client[os.getenv("DB_NAME", "sample_mflix")]

def serialize_mongo(obj):
    if isinstance(obj, ObjectId): return str(obj)
    if isinstance(obj, dict): return {k: serialize_mongo(v) for k, v in obj.items()}
    if isinstance(obj, list): return [serialize_mongo(i) for i in obj]
    return obj

# --- TOOLS ---

@mcp.tool()
def consultar_peliculas(titulo: str) -> str:
    """Busca películas. Úsala solo si el usuario pregunta por cine o películas."""
    try:
        db = get_db()
        if db is None: return "Error: Configuración de DB ausente."
        
        # Búsqueda limitada para ser ultra rápida
        res = list(db.movies.find(
            {"title": {"$regex": titulo, "$options": "i"}}, 
            {"title": 1, "year": 1, "plot": 1, "_id": 1}
        ).limit(2))
        
        return json.dumps(serialize_mongo(res))
    except Exception as e:
        return f"Error rápido: {str(e)}"

@mcp.tool()
def estado_servidor() -> str:
    """Verifica si el MCP responde."""
    return "Servidor MCP Operativo en Koyeb"

if __name__ == "__main__":
    # Koyeb usa la variable PORT
    port = int(os.getenv("PORT", 8080))
    mcp.run(transport="sse", host="0.0.0.0", port=port)