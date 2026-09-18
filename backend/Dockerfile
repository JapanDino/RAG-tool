FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update -o Acquire::Retries=5 \
  && apt-get install -y --no-install-recommends \
       postgresql-client \
       python3-numpy \
       tesseract-ocr \
       tesseract-ocr-rus \
       tesseract-ocr-eng \
       poppler-utils \
  && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade "pip>=26.2.1,<27" \
  && pip install --no-cache-dir --default-timeout=120 --retries 10 -r /tmp/requirements.txt

COPY . /app

CMD ["sleep","infinity"]
