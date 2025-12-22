FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Instalamos dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el contenido del repo al contenedor
COPY . .

# Exponemos el puerto
EXPOSE 8080

# Ejecutamos el script indicando la carpeta donde está realmente
CMD ["python", "primer_servidor/mcp_server.py"]