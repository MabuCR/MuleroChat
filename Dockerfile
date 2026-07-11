# MuleroChat — Dockerfile (WCNP-compliant)
# - Base image desde registry interno Walmart (docker.ci.artifacts.walmart.com)
# - No-root user (política de seguridad WCNP)
# - Puerto 8080 (estándar WCNP)

FROM docker.ci.artifacts.walmart.com/python:3.11-slim

LABEL maintainer="maa001e@walmart.com"
LABEL app="mulero-chat"

WORKDIR /app

# Instalar uv (gestor rápido de paquetes)
RUN pip install --no-cache-dir \
    --index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple \
    --trusted-host pypi.ci.artifacts.walmart.com \
    uv

# Copiar dependencias primero (aprovecha cache de Docker)
COPY requirements.txt .

# Instalar dependencias con mirror PyPI de Walmart
RUN uv pip install --system \
    --index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple \
    --allow-insecure-host pypi.ci.artifacts.walmart.com \
    -r requirements.txt

# Copiar el resto del código
COPY . .

# Crear carpeta de uploads con permisos correctos
RUN mkdir -p static/uploads

# WCNP: correr como usuario no-root (requerido por política de seguridad)
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER 1001

EXPOSE 8080

# uvicorn con soporte explícito de WebSockets
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--ws", "websockets", \
     "--log-level", "info"]
