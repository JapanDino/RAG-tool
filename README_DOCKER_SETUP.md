# RAG Bloom Project: Docker Quickstart

## Build and Run
docker compose up -d --build

## Stop
docker compose down

## Check logs
docker compose logs -f backend

## Database shell
docker compose exec db psql -U rag -d rag_db

## Apply Alembic migrations
docker compose exec backend alembic upgrade head

## Seed Bloom Taxonomy (if available)
docker compose exec backend python -m app.seed.bloom
