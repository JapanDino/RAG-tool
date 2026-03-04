FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN printf 'Acquire::https::Verify-Peer "false";\nAcquire::https::Verify-Host "false";\n' \
      > /etc/apt/apt.conf.d/99no-ssl-verify \
  && apt-get update -o Acquire::Retries=5 \
  && apt-get install -y --no-install-recommends \
       postgresql-client \
       tesseract-ocr \
       tesseract-ocr-rus \
       tesseract-ocr-eng \
       poppler-utils \
  && rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99no-ssl-verify

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app

CMD ["sleep","infinity"]
