# Dream Lodge MCP Server

Servidor MCP (Model Context Protocol) para Dream Lodge que proporciona herramientas para interactuar con la base de datos MongoDB de la aplicación.

## 🚀 Características

El servidor MCP proporciona las siguientes herramientas:

### Artworks (Obras Culturales)
- **search_artworks**: Busca artworks por categoría, fuente, título con paginación
- **get_artwork_by_id**: Obtiene un artwork específico por su ID
- **get_artwork_ocean_results**: Obtiene los resultados OCEAN asociados a un artwork

### Usuarios
- **search_users**: Busca usuarios por email o nombre
- **get_user_by_email**: Obtiene un usuario específico por su email
- **get_user_favorites**: Obtiene las obras favoritas de un usuario
- **get_user_pending**: Obtiene las obras pendientes de un usuario
- **get_user_ocean_results**: Obtiene los resultados del test OCEAN de un usuario

### Estadísticas
- **get_statistics**: Obtiene estadísticas generales de Dream Lodge

## 📋 Requisitos

- Python 3.11+
- MongoDB (local o remoto)
- Variables de entorno configuradas (ver `.env`)

## ⚙️ Configuración

1. Copia el archivo `.env` y configura las variables:

```env
MONGO_URI=mongodb://localhost:27017
DB_NAME=dreamlodge
PORT=8080
```

2. Instala las dependencias:

```bash
pip install -r requirements.txt
```

## 🐳 Docker

Para ejecutar con Docker:

```bash
docker-compose up --build
```

El servidor estará disponible en `http://localhost:8080`

## 💻 Ejecución Local

```bash
cd primer_servidor
python mcp_server.py
```

## 📚 Uso de las Herramientas

### Ejemplo: Buscar películas

```python
# Buscar artworks de la categoría "cine"
result = search_artworks(category="cine", limit=10)
```

### Ejemplo: Obtener favoritos de un usuario

```python
# Obtener obras favoritas de un usuario
favorites = get_user_favorites(user_id="507f1f77bcf86cd799439011")
```

### Ejemplo: Obtener resultados OCEAN

```python
# Obtener resultados del test Big Five de un usuario
ocean_results = get_user_ocean_results(user_id="507f1f77bcf86cd799439011")
```

## 🔧 Estructura del Proyecto

```
mcp/
├── primer_servidor/
│   ├── mcp_server.py      # Servidor MCP principal
│   ├── pyproject.toml      # Configuración del proyecto
│   └── uv.lock            # Lock file de dependencias
├── docker-compose.yml     # Configuración Docker
├── Dockerfile             # Imagen Docker
├── requirements.txt       # Dependencias Python
├── .env                   # Variables de entorno (no versionado)
└── README.md             # Este archivo
```

## 📝 Notas

- El servidor usa FastMCP para implementar el protocolo MCP
- Todas las herramientas devuelven datos serializados (ObjectId convertido a string)
- Los datos sensibles (contraseñas, tokens) se filtran automáticamente
- El servidor soporta paginación para búsquedas grandes

## 🐛 Solución de Problemas

### Error de conexión a MongoDB
- Verifica que `MONGO_URI` esté correctamente configurado
- Asegúrate de que MongoDB esté corriendo
- Si usas MongoDB Atlas, verifica que la IP esté en la whitelist

### Puerto en uso
- Cambia el puerto en `.env` o usa `PORT=8081` al ejecutar

### Dependencias faltantes
```bash
pip install fastmcp pymongo
```
