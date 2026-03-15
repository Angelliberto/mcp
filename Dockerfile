FROM python:3.11-slim

# Variables de entorno
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Crear directorio de trabajo
WORKDIR /app

# No se necesitan dependencias del sistema adicionales

# Copiar e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY primer_servidor/ ./primer_servidor/

# El puerto se configura desde la variable de entorno PORT (Koyeb lo asigna automáticamente)
# Exponemos el puerto por defecto (Koyeb puede usar cualquier puerto)
EXPOSE 8080

# Health check - Koyeb manejará los health checks automáticamente
# Si necesitas un health check en Docker, puedes descomentar lo siguiente:
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#     CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8080}/', timeout=5)" || exit 1

# Ejecutar el servidor MCP
# Koyeb asignará el puerto automáticamente a través de la variable PORT
CMD ["python", "primer_servidor/mcp_server.py"]