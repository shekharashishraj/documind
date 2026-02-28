FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY core ./core
COPY pipeline ./pipeline
COPY apps ./apps
COPY configs ./configs
COPY pdfs ./pdfs
COPY eval_pdf_qa.json ./

RUN python -m pip install --upgrade pip \
  && pip install --no-cache-dir -e .

EXPOSE 8080

CMD ["sh", "-c", "uvicorn apps.web.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
