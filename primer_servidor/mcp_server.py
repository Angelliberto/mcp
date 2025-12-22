import os
from fastmcp import FastMCP
from pymongo import MongoClient
from typing import List, Dict, Any
import json

# MCP Server instance
mcp = FastMCP("Videogames Store MongoDB")

# Configuración de conexión (Usa variables de entorno en Koyeb)
MONGO_URI = os.getenv("MONGO_URI","mongodb+srv://angellibertoceb:rawUoXCLskO3kqgQ@cluster0.aqndn.mongodb.net/?appName=Cluster0 ")
DB_NAME = os.getenv("DB_NAME", "sample_mflix")

def obtener_db():
    """Conecta a MongoDB y devuelve la base de datos"""
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]

@mcp.tool()
def listar_colecciones() -> List[str]:
    """
    Lista todas las colecciones (tablas) disponibles en la base de datos MongoDB.
    """
    db = obtener_db()
    return db.list_collection_names()

@mcp.tool()
def describir_coleccion(nombre_coleccion: str) -> Dict[str, Any]:
    """
    Obtiene información sobre una colección, incluyendo conteo de documentos 
    y un ejemplo del esquema basado en el primer documento encontrado.
    """
    db = obtener_db()
    coleccion = db[nombre_coleccion]
    
    total_documentos = coleccion.count_documents({})
    ejemplo = coleccion.find_one()
    
    # Limpiamos el ObjectId para que sea serializable a JSON
    if ejemplo and "_id" in ejemplo:
        ejemplo["_id"] = str(ejemplo["_id"])

    return {
        "coleccion": nombre_coleccion,
        "total_documentos": total_documentos,
        "esquema_ejemplo": ejemplo if ejemplo else "Colección vacía"
    }

@mcp.tool()
def buscar_en_mongo(coleccion: str, query_json: str, limite: int = 10) -> List[Dict[str, Any]]:
    """
    Ejecuta una búsqueda en una colección específica usando un filtro JSON.
    
    Args:
        coleccion: Nombre de la colección
        query_json: Filtro en formato JSON string, ej: '{"plataforma": "PS5"}'
        limite: Máximo de resultados a devolver
    """
    try:
        db = obtener_db()
        # Convertimos el string JSON del agente a un diccionario de Python
        filtro = json.loads(query_json)
        
        resultados = list(db[coleccion].find(filtro).limit(limite))
        
        # Formatear IDs para la respuesta
        for res in resultados:
            if "_id" in res:
                res["_id"] = str(res["_id"])
                
        return resultados
    except Exception as e:
        return [{"error": str(e), "tipo": "MongoQueryError"}]

if __name__ == "__main__":
    # Escuchando en el puerto 8080 para Koyeb
    mcp.run(transport="http", host="0.0.0.0", port=8080)