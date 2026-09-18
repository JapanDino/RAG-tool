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
Рекомендуемый продуктовый сценарий Course Quality Auditor:

1. Нажать «Попробовать демо» или импортировать read-only Canvas course.
2. Запустить аудит и показать матрицу цели → материалы → задания.
3. Открыть finding и сгенерировать grounded Copilot draft с цитатами.
4. Принять draft и показать Canvas Change Set — конкретную операцию переноса без автоматической публикации.
5. Во вкладке «Вопросы к курсу» задать вопрос по материалу и открыть источник ответа.
6. Для курса с Outcome Alignments показать precision/recall/F1 и диагностическую threshold curve.
7. Оценить Q&A как полезный и показать, как review появляется в обезличенном ML feedback JSONL.
8. Нажать «Запустить испытания», показать PASS/FAIL, SHA-256 набора и скачать протокол с методикой.

См. `docs/DEMO_EXAMPLES.md` — готовые тексты и ожидаемые результаты.

Основной сценарий для демонстрации графа:
- открыть `data/demo_knowledge_module.json`;
- вставить поле `text` во вкладку «Анализ»;
- запустить анализ и проверить узлы `закон сохранения энергии`, `F=ma`, `массы`, `ускорение`;
- открыть вкладку «Граф» и нажать «Загрузить граф»;
- показать цветовую кодировку уровней Блума, фильтры, hover-card и экспорт.

## 3) Метрики качества
Скрипт:
`python scripts/evaluate_multilabel.py --data data/bloom_dataset.jsonl`

Baseline report:
- `docs/BASELINE_QUALITY_REPORT.md`
- `docs/BASELINE_QUALITY_REPORT.json`

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
