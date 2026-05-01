# To-Do Tech List — Bloom RAG Studio
**Дата:** 2026-05-01  
**Приоритеты:** 🔴 Критично (блокирует качество результатов) · 🟠 Важно (серьёзный баг/пробел) · 🟡 Желательно (полировка)

---

## 🔴 КРИТИЧНО — сделать в первую очередь

### [T-01] Исправить чанкование: заменить срез по 800 символов на sentence-aware сплиттер
**Файл:** `backend/app/tasks/tasks.py:313`  
**Что сделать:**
- Заменить `[text_str[i:i+800] for i in range(0, len(text_str), 800)]`
- Использовать уже написанный `split_into_chunks` из `backend/app/services/chunking.py`
- Добавить в `chunking.py` параметр `max_tokens` (цель: 300–500 токенов) и перекрытие 15–20%
- Дополнительно: добавить верхнюю границу длины чанка в `chunking.py` (параграфы без точек)

```python
# Было:
parts = [text_str[i:i+800] for i in range(0, len(text_str), 800)]

# Должно быть:
from app.services.chunking import split_into_chunks
parts = split_into_chunks(text_str, max_tokens=400, overlap=0.2)
```

---

### [T-02] Исправить Bloom-scoring: заменить длину текста на `prob_vector[level_index]`
**Файл:** `backend/app/utils/bloom.py:12-24`  
**Что сделать:**
- Убрать `score = min(1.0, 0.5 + len(chunk.strip())/2000.0)`
- Score должен браться из `prob_vector` классификатора: `score = prob_vector[level_index]`
- Если LLM выключен, использовать keyword-based `prob_vector` из `classify_bloom_multilabel`

```python
# Было:
score = min(1.0, 0.5 + len(chunk.strip()) / 2000.0)

# Должно быть:
from app.utils.bloom import classify_bloom_multilabel
result = classify_bloom_multilabel(chunk)
score = float(result["prob_vector"][level_index])
```

---

### [T-03] Исправить regex-баг в `node_extractor.py`
**Файл:** `backend/app/services/node_extractor.py:13`  
**Что сделать:**
- `r"[.!?\\n]+"` → `r"[.!?\n]+"` (убрать лишний обратный слеш)

```python
# Было:
SENT_SPLIT_RE = re.compile(r"[.!?\\n]+")

# Должно быть:
SENT_SPLIT_RE = re.compile(r"[.!?\n]+")
```

---

### [T-04] Зарегистрировать `vec` колонку в SQLAlchemy ORM
**Файл:** `backend/app/models/models.py`  
**Что сделать:**
- Установить `pip install pgvector` (если не установлен)
- Добавить `from pgvector.sqlalchemy import Vector`
- Объявить `vec = mapped_column(Vector(1536), nullable=True)` в `Embedding` и `KnowledgeNode`
- Убедиться, что Alembic-миграция создаёт `CREATE INDEX USING hnsw (vec vector_cosine_ops)`

```python
from pgvector.sqlalchemy import Vector

class KnowledgeNode(Base):
    ...
    vec: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)
```

---

### [T-05] Исправить умолчание провайдера эмбеддингов
**Файл:** `backend/app/services/embedding_provider.py:175`  
**Что сделать:**
- Изменить fallback с `"hash"` на `"local"`
- Добавить видимое предупреждение пользователю при fallback на hash (не только RuntimeWarning)

```python
# Было:
os.getenv("EMBEDDING_PROVIDER", "hash")

# Должно быть:
os.getenv("EMBEDDING_PROVIDER", "local")
```

---

### [T-06] Перенести `reindex_nodes` в Celery-задачу
**Файл:** `backend/app/routers/datasets.py:107-138`  
**Что сделать:**
- Обернуть логику в `@app.task` аналогично `index_dataset`
- Вернуть `job_id` из endpoint
- Фронтенд: показывать `JobStatus` для операции reindex

---

### [T-07] Вынести общие типы/константы в shared модуль фронтенда
**Файлы:** `frontend/pages/index.tsx:5-61`, `frontend/components/GraphView.tsx:5-45`  
**Что сделать:**
- Создать `frontend/lib/bloom-constants.ts`
- Перенести туда: `BloomLevel`, `BLOOM_LEVELS`, `LEVEL_LABELS`, `LEVEL_COLORS`, `LEVEL_BG`, `LEVEL_BORDER`, `LEVEL_SHAPES`
- Импортировать в оба файла

---

## 🟠 ВАЖНО — исправить до защиты

### [T-08] Унифицировать Bloom-классификатор: убрать `bloom_classifier.py`
**Что сделать:**
- Удалить `backend/app/services/bloom_classifier.py`
- `POST /analyze` endpoint переключить на `classify_bloom_multilabel` из `bloom.py`
- Убедиться, что `prob_vector` семантически одинаков во всех endpoints

---

### [T-09] Расширить контекст для Bloom-классификации
**Файл:** `backend/app/routers/analyze.py:127`  
**Что сделать:**
- Вместо `context_snippet` (240 символов) брать окно 500–1000 символов вокруг позиции узла
- Использовать `char_start`/`char_end` из `model_info` для извлечения расширенного контекста из исходного текста

---

### [T-10] Стандартизировать метрику расстояния: только `<=>` (cosine)
**Файлы:** `backend/app/tasks/tasks.py:204`, `backend/app/routers/nodes.py:99`  
**Что сделать:**
- Заменить `<->` (L2) на `<=>` (cosine) во всех vector-запросах
- Везде использовать `1.0 - (vec <=> query_vec)` как формулу similarity

---

### [T-11] Исправить градиентную заливку узлов для мульти-лейбл (требование ТЗ)
**Файл:** `frontend/components/GraphView.tsx:133-143`  
**Что сделать:**
- Cytoscape поддерживает `pie-*` стили для круговых сегментов
- Или: создать SVG-слой поверх canvas для кастомных градиентов
- Минимально: использовать `background-gradient-stop-colors` + `background-gradient-direction` из Cytoscape 3.x

```javascript
// Cytoscape pie chart approach для двух уровней:
'pie-size': '100%',
'pie-1-background-color': primaryColor,
'pie-1-background-size': `${primaryProb * 100}%`,
'pie-2-background-color': secondaryColor,
'pie-2-background-size': `${secondaryProb * 100}%`,
```

---

### [T-12] Применить Bloom-фильтры к вкладке «Анализ»
**Файл:** `frontend/pages/index.tsx:925`  
**Что сделать:**
- `filteredNodes` для грида на вкладке «Анализ» должен учитывать состояние `filters`
- Добавить `&& filters[getPrimaryLevel(node)]` к условию фильтрации

---

### [T-13] Исправить detail-карточку узла: sticky side panel вместо push layout
**Файл:** `frontend/pages/index.tsx:2126-2180`  
**Что сделать:**
- Перенести карточку в sidebar или сделать `position: fixed` overlay с кнопкой закрытия
- Добавить `×` кнопку для очистки `selectedNode`
- `mouseout` должен сбрасывать `hoveredNode`, но не `selectedNode` (sticky по клику)

---

### [T-14] Добавить `ErrorBoundary` вокруг `GraphView`
**Что сделать:**
- Создать `frontend/components/ErrorBoundary.tsx`
- Обернуть `<GraphView>` в `<ErrorBoundary fallback={<GraphErrorFallback />}>`
- `GraphErrorFallback` — простой блок с сообщением об ошибке и кнопкой «Перезагрузить граф»

---

### [T-15] Добавить responsive-стили
**Файл:** `frontend/styles/home.module.css`  
**Что сделать:**
- Добавить `@media (max-width: 1100px)` — скрыть aside, сделать nav collapsible
- `@media (max-width: 768px)` — стековый лейаут
- Минимально: aside должен скрываться, main должен занимать всю ширину

---

### [T-16] Добавить batching в `annotate_dataset`
**Файл:** `backend/app/tasks/tasks.py:102`  
**Что сделать:**
- Собрать все INSERT в список
- Использовать bulk INSERT: `db.execute(BloomAnnotation.__table__.insert(), records_list)`

---

### [T-17] Убрать N+1 запросы в `analyze_content`
**Файл:** `backend/app/routers/analyze.py:133`  
**Что сделать:**
- Загрузить все существующие `KnowledgeNode` по `dataset_id` одним запросом в dict
- Делать upsert батчем

---

### [T-18] Добавить AbortController на ключевые API-вызовы
**Файл:** `frontend/pages/index.tsx`  
**Что сделать:**
- `analyzeText`, `loadGraph`, `searchNodes` — добавить `AbortController`
- При повторном вызове отменять предыдущий: `controller.abort()`

---

## 🟡 ЖЕЛАТЕЛЬНО — перед презентацией

### [T-19] Добавить UI-кнопки zoom в/из для графа
**Файл:** `frontend/components/GraphView.tsx`  
Кнопки `+` / `-` / «По размеру» (`cy.fit()`) в правом нижнем углу canvas.

---

### [T-20] Исправить TypeScript типизацию в `JobStatus.tsx`
**Файл:** `frontend/components/JobStatus.tsx:11`  
```typescript
// Было: state: any
// Должно быть:
interface JobState {
  status: 'pending' | 'running' | 'done' | 'failed';
  task_id: string;
  celery?: { state: string; ready: boolean };
}
```

---

### [T-21] Перенести `dynamic()` на уровень модуля
**Файл:** `frontend/pages/index.tsx:507`  
```typescript
// Было: внутри useMemo
// Должно быть: на уровне модуля (top-level)
const GraphView = dynamic(() => import("../components/GraphView"), { ssr: false });
```

---

### [T-22] Исправить default `embedding_model` в ORM
**Файл:** `backend/app/models/models.py:44,58`  
```python
# Было:
server_default="text-embedding-3-small"

# Должно быть: нет жёсткого дефолта, значение приходит из провайдера
```

---

### [T-23] Добавить ограничение длины в `build_bloom_multilabel_prompt`
**Файл:** `backend/app/utils/prompt.py:42`  
```python
# Добавить перед вставкой текста:
text = text[:2000]  # Limit to avoid exceeding context window
```

---

### [T-24] Настроить ESLint
**Файл:** `frontend/package.json`  
- Заменить `"lint": "echo \"(lint placeholder)\""` на `"lint": "next lint"`
- Добавить `eslint`, `eslint-config-next` в devDependencies
- Добавить `.eslintrc.json`

---

### [T-25] Удалить мёртвую страницу `design-lab`
**Файл:** `frontend/pages/design-lab/main-section.tsx`  
Удалить или переместить в `/archive` если нужно сохранить историю.

---

### [T-26] Исправить `apiFetchJson` мемоизацией
**Файл:** `frontend/pages/index.tsx:596`  
Обернуть в `useCallback` или вынести в кастомный хук `useApi(apiBase)`.

---

### [T-27] Параллельный batch-upload
**Файл:** `frontend/pages/index.tsx:877`  
```typescript
// Было: sequential await in loop
// Должно быть:
await Promise.allSettled(files.map(f => uploadSingle(f)));
```

---

### [T-28] Задокументировать padding-шим для эмбеддингов
**Файл:** `backend/app/services/embedding_provider.py`  
Добавить комментарий: 1536-dim колонка — это shim для совместимости с OpenAI, `multilingual-e5-small` реально 384-dim.

---

## Очерёдность работ (рекомендуемая)

```
Неделя 1 (критично для качества диплома):
  T-01 Chunking fix
  T-03 Regex fix  
  T-02 Bloom scoring fix
  T-09 Расширить контекст классификации

Неделя 2 (архитектура и БД):
  T-04 vec в ORM
  T-05 Дефолт провайдера
  T-08 Унифицировать классификатор
  T-10 Стандартизировать cosine

Неделя 3 (фронтенд и ТЗ-требования):
  T-07 Shared types
  T-11 Градиент узлов
  T-12 Фильтры в Analysis tab
  T-13 Detail-карточка
  T-15 Responsive

Неделя 4 (стабилизация):
  T-06 reindex → Celery
  T-14 ErrorBoundary
  T-16, T-17 Performance
  T-18 AbortController
  T-19–T-28 Полировка
```
