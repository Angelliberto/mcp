import os
import json
from fastmcp import FastMCP
from pymongo import MongoClient
from bson import ObjectId
from typing import List, Dict, Any

# 1. DEFINICIÓN DEL SERVIDOR
mcp = FastMCP("Mflix Movie Database")

# 2. CONEXIÓN A MONGODB (Usando Variables de Entorno de Koyeb)
# Configura MONGO_URI y DB_NAME en el panel de Koyeb
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "sample_mflix")

if not MONGO_URI:
    raise ValueError("❌ Error: La variable de entorno MONGO_URI no está definida.")

try:
    # Aumentamos el timeout para evitar caídas en la nube
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    db = client[DB_NAME]
    client.admin.command('ping')
except Exception as e:
    print(f"❌ Error conectando a Mongo: {e}")
    db = None

# Helper para limpiar datos de MongoDB
def serialize_mongo(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, dict):
        return {k: serialize_mongo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_mongo(i) for i in obj]
    return obj

# --- TOOLS ---

@mcp.tool()
def busqueda_simple(texto: str) -> str:
    """Busca películas por título o trama."""
    if db is None: return "Error: Sin conexión a DB"
    try:
        regex_query = {"$or": [
            {"title": {"$regex": texto, "$options": "i"}},
            {"fullplot": {"$regex": texto, "$options": "i"}}
        ]}
        resultados = list(db.movies.find(regex_query, {"plot_embedding": 0, "poster": 0}).limit(5))
        return json.dumps(serialize_mongo(resultados), ensure_ascii=False)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def consulta_avanzada_json(filtro_json: str) -> str:
    """Consulta avanzada usando JSON de MongoDB."""
    if db is None: return "Error: Sin conexión a DB"
    try:
        query = json.loads(filtro_json)
        resultados = list(db.movies.find(query, {"plot_embedding": 0, "poster": 0}).limit(5))
        return json.dumps(serialize_mongo(resultados), ensure_ascii=False)
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    # OBTENER PUERTO DE KOYEB
    # Koyeb asigna automáticamente un puerto en la variable PORT
    port = int(os.getenv("PORT", 8080))
    
    # En Koyeb debemos escuchar en 0.0.0.0 para recibir tráfico externo
    mcp.run(transport="sse", host="0.0.0.0", port=port)