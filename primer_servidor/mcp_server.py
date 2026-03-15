import os
import sys
import json
from fastmcp import FastMCP
from pymongo import MongoClient
from bson import ObjectId
from typing import Any, Union, Optional, List
from datetime import datetime

# Fix encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

mcp = FastMCP("Dream Lodge MCP Server")

def get_db():
    """Conecta a la base de datos MongoDB de Dream Lodge"""
    client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=5000)
    return client[os.getenv("DB_NAME", "dreamlodge")]


def serialize_object(obj: Any) -> Any:
    """Convierte ObjectId y otros tipos de BSON a tipos serializables JSON"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: serialize_object(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_object(item) for item in obj]
    return obj


@mcp.tool()
def search_artworks(
    category: Optional[str] = None,
    source: Optional[str] = None,
    title: Optional[str] = None,
    limit: int = 20,
    page: int = 1
) -> dict:
    """
    Busca artworks (obras culturales) en Dream Lodge.
    
    Args:
        category: Categoría de la obra (cine, música, literatura, arte-visual, videojuegos)
        source: Fuente de la obra (IGDB, TMDB, GoogleBooks, MetMuseum, ChicagoArt, Spotify)
        title: Título o parte del título a buscar
        limit: Número máximo de resultados (default: 20)
        page: Número de página (default: 1)
    
    Returns:
        Diccionario con los artworks encontrados y información de paginación
    """
    try:
        db = get_db()
        artworks_collection = db.artworks
        
        query = {}
        
        if category:
            query["category"] = category
        
        if source:
            query["source"] = source
        
        if title:
            query["title"] = {"$regex": title, "$options": "i"}
        
        skip = (page - 1) * limit
        
        artworks = list(artworks_collection.find(query)
                       .limit(limit)
                       .skip(skip)
                       .sort("createdAt", -1))
        
        total = artworks_collection.count_documents(query)
        
        return {
            "data": serialize_object(artworks),
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "totalPages": (total + limit - 1) // limit
            }
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_artwork_by_id(artwork_id: str) -> dict:
    """
    Obtiene un artwork específico por su ID.
    
    Args:
        artwork_id: ID del artwork (puede ser el campo 'id' o '_id' de MongoDB)
    
    Returns:
        Diccionario con la información del artwork
    """
    try:
        db = get_db()
        artworks_collection = db.artworks
        
        # Intentar buscar por _id primero
        if ObjectId.is_valid(artwork_id):
            artwork = artworks_collection.find_one({"_id": ObjectId(artwork_id)})
            if artwork:
                return {"data": serialize_object(artwork)}
        
        # Buscar por el campo 'id'
        artwork = artworks_collection.find_one({"id": artwork_id})
        
        if not artwork:
            return {"error": "Artwork no encontrado"}
        
        return {"data": serialize_object(artwork)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_user_favorites(user_id: str) -> dict:
    """
    Obtiene las obras favoritas de un usuario.
    
    Args:
        user_id: ID del usuario (ObjectId de MongoDB)
    
    Returns:
        Lista de artworks favoritos del usuario
    """
    try:
        db = get_db()
        users_collection = db.users
        artworks_collection = db.artworks
        
        if not ObjectId.is_valid(user_id):
            return {"error": "ID de usuario inválido"}
        
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            return {"error": "Usuario no encontrado"}
        
        favorite_ids = user.get("favoriteArtworks", [])
        
        if not favorite_ids:
            return {"data": []}
        
        # Convertir IDs a ObjectId si son strings
        object_ids = [ObjectId(id) if isinstance(id, str) else id for id in favorite_ids]
        
        favorites = list(artworks_collection.find({"_id": {"$in": object_ids}}))
        
        return {"data": serialize_object(favorites)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_user_pending(user_id: str) -> dict:
    """
    Obtiene las obras pendientes de un usuario.
    
    Args:
        user_id: ID del usuario (ObjectId de MongoDB)
    
    Returns:
        Lista de artworks pendientes del usuario
    """
    try:
        db = get_db()
        users_collection = db.users
        artworks_collection = db.artworks
        
        if not ObjectId.is_valid(user_id):
            return {"error": "ID de usuario inválido"}
        
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            return {"error": "Usuario no encontrado"}
        
        pending_ids = user.get("pendingArtworks", [])
        
        if not pending_ids:
            return {"data": []}
        
        # Convertir IDs a ObjectId si son strings
        object_ids = [ObjectId(id) if isinstance(id, str) else id for id in pending_ids]
        
        pending = list(artworks_collection.find({"_id": {"$in": object_ids}}))
        
        return {"data": serialize_object(pending)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_user_ocean_results(user_id: str) -> dict:
    """
    Obtiene los resultados del test OCEAN (Big Five) de un usuario.
    
    Args:
        user_id: ID del usuario (ObjectId de MongoDB)
    
    Returns:
        Resultados del test OCEAN del usuario
    """
    try:
        db = get_db()
        ocean_collection = db.oceans
        
        if not ObjectId.is_valid(user_id):
            return {"error": "ID de usuario inválido"}
        
        ocean_results = list(ocean_collection.find({
            "entityType": "user",
            "entityId": ObjectId(user_id),
            "deleted": {"$ne": True}
        }).sort("createdAt", -1))
        
        if not ocean_results:
            return {"data": None, "message": "No se encontraron resultados OCEAN para este usuario"}
        
        return {"data": serialize_object(ocean_results)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def search_users(email: Optional[str] = None, name: Optional[str] = None, limit: int = 20) -> dict:
    """
    Busca usuarios en Dream Lodge.
    
    Args:
        email: Email del usuario (búsqueda exacta)
        name: Nombre del usuario (búsqueda parcial)
        limit: Número máximo de resultados (default: 20)
    
    Returns:
        Lista de usuarios encontrados
    """
    try:
        db = get_db()
        users_collection = db.users
        
        query = {"deleted": {"$ne": True}}
        
        if email:
            query["email"] = email
        
        if name:
            query["name"] = {"$regex": name, "$options": "i"}
        
        users = list(users_collection.find(query)
                    .limit(limit)
                    .sort("createdAt", -1))
        
        # Remover información sensible
        for user in users:
            user.pop("password", None)
            user.pop("resetPasswordToken", None)
            user.pop("resetPasswordTokenExpiration", None)
            user.pop("reset_token", None)
        
        return {"data": serialize_object(users)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_artwork_ocean_results(artwork_id: str) -> dict:
    """
    Obtiene los resultados del test OCEAN asociados a un artwork.
    
    Args:
        artwork_id: ID del artwork (ObjectId de MongoDB)
    
    Returns:
        Resultados del test OCEAN del artwork
    """
    try:
        db = get_db()
        ocean_collection = db.oceans
        
        if not ObjectId.is_valid(artwork_id):
            return {"error": "ID de artwork inválido"}
        
        ocean_result = ocean_collection.find_one({
            "entityType": "artwork",
            "entityId": ObjectId(artwork_id),
            "deleted": {"$ne": True}
        })
        
        if not ocean_result:
            return {"data": None, "message": "No se encontraron resultados OCEAN para este artwork"}
        
        return {"data": serialize_object(ocean_result)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_statistics() -> dict:
    """
    Obtiene estadísticas generales de Dream Lodge.
    
    Returns:
        Diccionario con estadísticas de artworks, usuarios, y categorías
    """
    try:
        db = get_db()
        artworks_collection = db.artworks
        users_collection = db.users
        ocean_collection = db.oceans
        
        total_artworks = artworks_collection.count_documents({})
        total_users = users_collection.count_documents({"deleted": {"$ne": True}})
        total_ocean_results = ocean_collection.count_documents({"deleted": {"$ne": True}})
        
        # Contar por categoría
        categories = ["cine", "música", "literatura", "arte-visual", "videojuegos"]
        category_counts = {}
        for category in categories:
            count = artworks_collection.count_documents({"category": category})
            category_counts[category] = count
        
        # Contar por fuente
        sources = ["IGDB", "TMDB", "GoogleBooks", "MetMuseum", "ChicagoArt", "Spotify"]
        source_counts = {}
        for source in sources:
            count = artworks_collection.count_documents({"source": source})
            source_counts[source] = count
        
        return {
            "statistics": {
                "total_artworks": total_artworks,
                "total_users": total_users,
                "total_ocean_results": total_ocean_results,
                "artworks_by_category": category_counts,
                "artworks_by_source": source_counts
            }
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_user_by_email(email: str) -> dict:
    """
    Obtiene un usuario por su email.
    
    Args:
        email: Email del usuario
    
    Returns:
        Información del usuario (sin datos sensibles)
    """
    try:
        db = get_db()
        users_collection = db.users
        
        user = users_collection.find_one({"email": email, "deleted": {"$ne": True}})
        
        if not user:
            return {"error": "Usuario no encontrado"}
        
        # Remover información sensible
        user.pop("password", None)
        user.pop("resetPasswordToken", None)
        user.pop("resetPasswordTokenExpiration", None)
        user.pop("reset_token", None)
        
        return {"data": serialize_object(user)}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    # Puerto dinámico o 8080 por defecto
    # Koyeb asignará el puerto automáticamente a través de la variable PORT
    port = int(os.getenv("PORT", 8080))
    try:
        print(f"🚀 Iniciando Dream Lodge MCP Server en puerto {port}")
        print(f"📡 Servidor disponible en http://0.0.0.0:{port}")
        print(f"🔗 MongoDB: {os.getenv('DB_NAME', 'dreamlodge')}")
    except UnicodeEncodeError:
        # Fallback for consoles that don't support emojis
        print(f"[*] Iniciando Dream Lodge MCP Server en puerto {port}")
        print(f"[*] Servidor disponible en http://0.0.0.0:{port}")
        print(f"[*] MongoDB: {os.getenv('DB_NAME', 'dreamlodge')}")
    mcp.run(transport="sse", host="0.0.0.0", port=port)
