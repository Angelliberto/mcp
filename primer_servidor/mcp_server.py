import os
import json
from fastmcp import FastMCP
from pymongo import MongoClient
from bson import ObjectId
from typing import List, Dict, Any

# 1. DEFINICIÓN DEL SERVIDOR
mcp = FastMCP("Mflix Movie Database")

# 2. CONEXIÓN GLOBAL (OPTIMIZACIÓN DE VELOCIDAD)
# Al hacerlo aquí afuera, se conecta solo 1 vez cuando arranca el servidor, no en cada petición.
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "sample_mflix")

try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    # Un pequeño ping para asegurar que la conexión está viva al inicio
    client.admin.command('ping')
    print("✅ Conectado exitosamente a MongoDB Atlas")
except Exception as e:
    print(f"❌ Error conectando a Mongo: {e}")

# Helpers
def serialize_mongo(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, dict):
        return {k: serialize_mongo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_mongo(i) for i in obj]
    return obj

# --- TOOLS MEJORADAS ---

@mcp.tool()
def busqueda_simple(texto: str) -> List[Dict[str, Any]]:
    """
    Busca películas por título o trama usando una búsqueda de texto simple.
    Úsala cuando el usuario pregunte por temas generales como 'películas de barcos', 'Harry Potter', etc.
    """
    try:
        # Busca en el índice de texto (si existe) o usa regex como fallback flexible
        # Opción Regex (más lenta pero funciona sin índices especiales):
        regex_query = {"$or": [
            {"title": {"$regex": texto, "$options": "i"}},
            {"fullplot": {"$regex": texto, "$options": "i"}}
        ]}
        
        resultados = list(db.movies.find(regex_query, 
                                       {"plot_embedding": 0, "poster": 0}) # Excluimos campos pesados
                                       .limit(5))
        
        if not resultados:
            return [{"mensaje": f"No encontré películas que coincidan con '{texto}'."}]
            
        return serialize_mongo(resultados)
    except Exception as e:
        return [{"error": str(e)}]

@mcp.tool()
def consulta_avanzada_json(filtro_json: str) -> List[Dict[str, Any]]:
    """
    SOLO usar si necesitas filtros específicos (año, rating, director).
    Espera un string JSON válido de MongoDB. Ej: {"year": 2015, "imdb.rating": {"$gt": 8}}
    """
    try:
        query = json.loads(filtro_json)
        resultados = list(db.movies.find(query, {"plot_embedding": 0, "poster": 0}).limit(5))
        return serialize_mongo(resultados)
    except Exception as e:
        return [{"error": f"JSON inválido o error de consulta: {str(e)}"}]

@mcp.tool()
def estadisticas_rapidas() -> str:
    """Devuelve un resumen rápido de qué hay en la base de datos."""
    try:
        count = db.movies.estimated_document_count()
        return f"Hay un total de {count} películas en la base de datos."
    except Exception as e:
        return f"Error obteniendo stats: {str(e)}"

if __name__ == "__main__":

    mcp.run(transport="sse", host="0.0.0.0", port=8080)