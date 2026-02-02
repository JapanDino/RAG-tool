Файл `bloom_dataset.jsonl` содержит примеры для оценки multi‑label классификации.

Формат строки (JSONL):
{
  "text": "Текст задания или фрагмент",
  "labels": ["remember", "understand"]
}

Минимально рекомендуется 100+ примеров, чтобы метрики были стабильнее.

Запуск оценки:
python scripts/evaluate_multilabel.py --data data/bloom_dataset.jsonl
