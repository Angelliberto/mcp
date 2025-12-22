# Imagen oficial de Python
FROM python:3.11-slim

# Evita que Python genere archivos basura y muestra logs
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Instalamos dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el servidor y la base de datos
COPY mcp_server.py .
COPY tienda_videojuegos.db .

# Exponemos el puerto para n8n
EXPOSE 8080

# Ejecutamos el servidor
CMD ["python", "mcp_server.py"]