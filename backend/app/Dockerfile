FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY src /app/src

RUN mkdir -p /app/backend/data/keys /app/backend/data/chroma /app/logs \
    && addgroup --system shellmate \
    && adduser --system --ingroup shellmate shellmate \
    && chown -R shellmate:shellmate /app
USER shellmate

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000" ]
