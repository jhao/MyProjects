FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=5500 \
    DEBUG=0 \
    DATA_DIR=/app/data \
    UPLOAD_DIR=/app/data/uploads \
    DATABASE_URL=sqlite:////app/data/mpj.sqlite3

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY app ./app
COPY run.py .

RUN mkdir -p /app/data/uploads

EXPOSE 5500

CMD ["python", "run.py"]
