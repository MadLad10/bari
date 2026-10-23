FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-ben poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-local.txt requirements-dev.txt ./
ARG INSTALL_DEV=true
RUN if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; else pip install -r requirements-local.txt; fi

COPY . .

# Run as a non-root user so files written to bind mounts stay owned by the host user.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/uploads /app/private_uploads /home/app/.cache \
    && chown -R app /app /home/app/.cache
USER app

EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
