FROM python:3.11-slim

# Tesseract (OCR) and Poppler (PDF -> image, for pdf2image) are system
# packages, not pip packages — this is why a plain Render "Python" web
# service (no Dockerfile) won't work for this app.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
