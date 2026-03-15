FROM python:3.11-slim

# Variables de entorno
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Crear directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema (si es necesario)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY primer_servidor/ ./primer_servidor/

# El puerto se configura desde la variable de entorno PORT (Koyeb lo asigna automáticamente)
# Exponemos el puerto por defecto (Koyeb puede usar cualquier puerto)
EXPOSE 8080

# Health check (opcional pero recomendado)
# Nota: Koyeb puede hacer health checks automáticos, pero este es un fallback
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=5)" || exit 1

# Ejecutar el servidor MCP
# Koyeb asignará el puerto automáticamente a través de la variable PORT
CMD ["python", "primer_servidor/mcp_server.py"]