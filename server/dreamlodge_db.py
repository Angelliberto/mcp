"""
Acceso a MongoDB para Dream Lodge (herramientas y agente IA).
"""
import os
from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from pymongo import MongoClient


def get_db():
    client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=5000)
    return client[os.getenv("DB_NAME", "dreamlodge")]


def serialize_object(obj: Any) -> Any:
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: serialize_object(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_object(item) for item in obj]
    return obj


def _build_artwork_query(
    category: Optional[str] = None,
    source: Optional[str] = None,
    title: Optional[str] = None,
    genre: Optional[str] = None,
) -> dict:
    query: dict = {}
    if category:
        query["category"] = category
    if source:
        query["source"] = source
    if title:
        query["title"] = {"$regex": title, "$options": "i"}

    if not genre:
        return query

    genre_query = {
        "$or": [
            {"description": {"$regex": genre, "$options": "i"}},
            {"tags": {"$regex": genre, "$options": "i"}},
            {"genre": {"$regex": genre, "$options": "i"}},
        ]
    }
    if not query:
        return genre_query
    return {"$and": [query, genre_query]}


def search_artworks(
    category: Optional[str] = None,
    source: Optional[str] = None,
    title: Optional[str] = None,
    genre: Optional[str] = None,
    limit: int = 20,
    page: int = 1,
) -> dict:
    try:
        db = get_db()
        coll = db.artworks
        query = _build_artwork_query(category, source, title, genre)
        skip = (page - 1) * limit
        artworks = list(
            coll.find(query).limit(limit).skip(skip).sort("createdAt", -1)
        )
        total = coll.count_documents(query)
        return {
            "data": serialize_object(artworks),
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "totalPages": (total + limit - 1) // limit if limit else 0,
            },
        }
    except Exception as e:
        return {"error": str(e), "data": []}


def get_artwork_by_id(artwork_id: str) -> dict:
    try:
        db = get_db()
        coll = db.artworks
        if ObjectId.is_valid(artwork_id):
            artwork = coll.find_one({"_id": ObjectId(artwork_id)})
            if artwork:
                return {"data": serialize_object(artwork)}
        artwork = coll.find_one({"id": artwork_id})
        if not artwork:
            return {"error": "Artwork no encontrado"}
        return {"data": serialize_object(artwork)}
    except Exception as e:
        return {"error": str(e)}


def get_user_favorites(user_id: str) -> dict:
    try:
        db = get_db()
        users = db.users
        artworks = db.artworks
        if not ObjectId.is_valid(user_id):
            return {"error": "ID de usuario inválido"}
        user = users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return {"error": "Usuario no encontrado"}
        favorite_ids = user.get("favoriteArtworks", [])
        if not favorite_ids:
            return {"data": []}
        object_ids = [
            ObjectId(i) if isinstance(i, str) and ObjectId.is_valid(i) else i
            for i in favorite_ids
        ]
        favorites = list(artworks.find({"_id": {"$in": object_ids}}))
        return {"data": serialize_object(favorites)}
    except Exception as e:
        return {"error": str(e)}


def get_user_pending(user_id: str) -> dict:
    try:
        db = get_db()
        users = db.users
        artworks = db.artworks
        if not ObjectId.is_valid(user_id):
            return {"error": "ID de usuario inválido"}
        user = users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return {"error": "Usuario no encontrado"}
        pending_ids = user.get("pendingArtworks", [])
        if not pending_ids:
            return {"data": []}
        object_ids = [
            ObjectId(i) if isinstance(i, str) and ObjectId.is_valid(i) else i
            for i in pending_ids
        ]
        pending = list(artworks.find({"_id": {"$in": object_ids}}))
        return {"data": serialize_object(pending)}
    except Exception as e:
        return {"error": str(e)}


def get_user_ocean_results(user_id: str) -> dict:
    try:
        db = get_db()
        ocean = db.oceans
        if not ObjectId.is_valid(user_id):
            return {"error": "ID de usuario inválido"}
        ocean_results = list(
            ocean.find(
                {
                    "entityType": "user",
                    "entityId": ObjectId(user_id),
                    "deleted": {"$ne": True},
                }
            ).sort("createdAt", -1)
        )
        if not ocean_results:
            return {
                "data": None,
                "message": "No se encontraron resultados OCEAN para este usuario",
            }
        return {"data": serialize_object(ocean_results)}
    except Exception as e:
        return {"error": str(e)}


def search_users(
    email: Optional[str] = None, name: Optional[str] = None, limit: int = 20
) -> dict:
    try:
        db = get_db()
        coll = db.users
        query: dict = {"deleted": {"$ne": True}}
        if email:
            query["email"] = email
        if name:
            query["name"] = {"$regex": name, "$options": "i"}
        users = list(coll.find(query).limit(limit).sort("createdAt", -1))
        for user in users:
            user.pop("password", None)
            user.pop("resetPasswordToken", None)
            user.pop("resetPasswordTokenExpiration", None)
            user.pop("reset_token", None)
        return {"data": serialize_object(users)}
    except Exception as e:
        return {"error": str(e)}


def get_artwork_ocean_results(artwork_id: str) -> dict:
    try:
        db = get_db()
        ocean = db.oceans
        if not ObjectId.is_valid(artwork_id):
            return {"error": "ID de artwork inválido"}
        ocean_result = ocean.find_one(
            {
                "entityType": "artwork",
                "entityId": ObjectId(artwork_id),
                "deleted": {"$ne": True},
            }
        )
        if not ocean_result:
            return {
                "data": None,
                "message": "No se encontraron resultados OCEAN para este artwork",
            }
        return {"data": serialize_object(ocean_result)}
    except Exception as e:
        return {"error": str(e)}


def get_statistics() -> dict:
    try:
        db = get_db()
        artworks = db.artworks
        users = db.users
        ocean = db.oceans
        total_artworks = artworks.count_documents({})
        total_users = users.count_documents({"deleted": {"$ne": True}})
        total_ocean = ocean.count_documents({"deleted": {"$ne": True}})
        categories = ["cine", "música", "literatura", "arte-visual", "videojuegos"]
        category_counts = {
            c: artworks.count_documents({"category": c}) for c in categories
        }
        sources = ["IGDB", "TMDB", "GoogleBooks", "MetMuseum", "ChicagoArt", "Spotify"]
        source_counts = {s: artworks.count_documents({"source": s}) for s in sources}
        return {
            "statistics": {
                "total_artworks": total_artworks,
                "total_users": total_users,
                "total_ocean_results": total_ocean,
                "artworks_by_category": category_counts,
                "artworks_by_source": source_counts,
            }
        }
    except Exception as e:
        return {"error": str(e)}


def get_user_by_email(email: str) -> dict:
    try:
        db = get_db()
        coll = db.users
        user = coll.find_one({"email": email, "deleted": {"$ne": True}})
        if not user:
            return {"error": "Usuario no encontrado"}
        user.pop("password", None)
        user.pop("resetPasswordToken", None)
        user.pop("resetPasswordTokenExpiration", None)
        user.pop("reset_token", None)
        return {"data": serialize_object(user)}
    except Exception as e:
        return {"error": str(e)}


def get_user_basic_info(user_id: str) -> Optional[dict]:
    if not ObjectId.is_valid(user_id):
        return None
    try:
        db = get_db()
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return None
        return {"name": user.get("name"), "email": user.get("email")}
    except Exception:
        return None

