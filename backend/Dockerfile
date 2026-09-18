# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN printf 'Acquire::https::Verify-Peer "false";\nAcquire::https::Verify-Host "false";\n' \
      > /etc/apt/apt.conf.d/99no-ssl-verify \
  && apt-get update -o Acquire::Retries=5 \
  && apt-get install -y --no-install-recommends \
       postgresql-client \
       python3-numpy \
       tesseract-ocr \
       tesseract-ocr-rus \
       tesseract-ocr-eng \
       poppler-utils \
  && rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99no-ssl-verify

COPY backend/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=300 --retries 20 -r /tmp/requirements.txt

COPY . /app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
