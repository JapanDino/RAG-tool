# Материалы для защиты

## 1) Инструкция запуска
### Локально (API + Frontend)
1. Установить зависимости:
   - `pip install -r backend/requirements.txt`
   - `cd frontend && npm install`
2. Запустить API:
   - `scripts/run_api.sh` (или `uvicorn backend.app.main:app --reload`)
3. Запустить Frontend:
   - `scripts/run_frontend.sh` (или `npm run dev`)
4. Открыть UI: `http://localhost:3000`

### Docker (альтернатива)
1. `docker-compose up --build`
2. API: `http://localhost:8000`, UI: `http://localhost:3000`

## 2) Демо‑сценарии
См. `docs/DEMO_EXAMPLES.md` — готовые тексты и ожидаемые результаты.

## 3) Метрики качества
Скрипт:
`python scripts/evaluate_multilabel.py --data data/bloom_dataset.jsonl`

## 4) Дамп БД
Если нужно приложить дамп:
- Postgres: `pg_dump -Fc -f artifacts/db_dump.dump <db_name>`
- SQLite: копия файла базы.

## 5) Скриншоты/видео
Рекомендуемые скриншоты:
- Вкладка “Анализ контента” (таблица узлов + экспорт).
- Вкладка “Граф знаний” (фильтры и легенда цветов).

Папка для артефактов:
- `artifacts/` (создать при необходимости).
