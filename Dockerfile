# MuleroChat — Dockerfile (Fly.io / produccion publica)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p static/uploads

# Usuario no-root por seguridad
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER 1001

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--ws", "websockets"]
