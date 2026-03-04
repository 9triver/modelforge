FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir ".[serving]"

ENV MODELFORGE_MODEL_STORE_PATH=/app/data/model_store

VOLUME /app/data

EXPOSE 8000

CMD ["uvicorn", "modelforge.main:app", "--host", "0.0.0.0", "--port", "8000"]
