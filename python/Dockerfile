FROM python:3.12-slim

RUN pip install --no-cache-dir \
    asyncpg==0.31.0 \
    fastapi==0.139.2 \
    httpx==0.28.1 \
    pydantic==2.13.4 \
    pytest==8.4.2 \
    pytest-asyncio==1.2.0 \
    redis==8.0.1 \
    'sqlalchemy[asyncio]==2.0.51' \
    uvicorn==0.51.0

WORKDIR /workspace
COPY app /workspace/app
ENV PYTHONUNBUFFERED=1
