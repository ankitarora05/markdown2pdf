# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

WORKDIR /app

RUN useradd --create-home --uid 1000 user

# PyMuPDF ships its rendering engine in its manylinux wheel. DejaVu fonts
# provide reliable glyph coverage for generated PDFs in the slim image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user:user app ./app
COPY --chown=user:user themes ./themes
COPY --chown=user:user google4d282da7d3423ef3.html ./google4d282da7d3423ef3.html

EXPOSE 7860

USER user
ENV HOME=/home/user

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '7860') + '/health', timeout=3)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]
