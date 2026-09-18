export type CanvasDemoItemType =
  | "page"
  | "assignment"
  | "file"
  | "external"
  | "section";

export type CanvasDemoItem = {
  id: string;
  title: string;
  type: CanvasDemoItemType;
  detail?: string;
  due?: string;
  external?: boolean;
};

export type CanvasDemoModule = {
  id: string;
  title: string;
  items: CanvasDemoItem[];
};

export type CanvasDemoAssignment = {
  id: string;
  title: string;
  group: string;
  due: string;
  points: number;
  status: "upcoming" | "submitted" | "open";
};

export type CanvasDemoCourse = {
  id: string;
  title: string;
  code: string;
  term: string;
  color: string;
  illustration: "ai" | "language" | "math" | "science" | "community";
  homeTitle: string;
  intro: string;
  objectives: string[];
  modules: CanvasDemoModule[];
  assignments: CanvasDemoAssignment[];
};

export const CANVAS_DEMO_COURSES: CanvasDemoCourse[] = [
  {
    id: "demo-ai",
    title: "Проектная лаборатория: ИИ-сервисы",
    code: "IT 10 · проектный трек",
    term: "2026/27 уч.год",
    color: "#b34f88",
    illustration: "ai",
    homeTitle: "Создаём полезного ИИ-помощника",
    intro:
      "Демо-курс показывает полный путь от идеи и данных до проверяемого прототипа. Все материалы синтетические и созданы только для локального тестирования интеграции.",
    objectives: [
      "отличать полезный образовательный сценарий от чат-бота ради чат-бота",
      "собирать небольшой корпус и строить проверяемый поиск по источникам",
      "оценивать качество ответа, границы уверенности и риски для пользователя",
      "представлять работающий прототип и объяснять принятые решения",
    ],
    modules: [
      {
        id: "orientation",
        title: "00. Старт проекта",
        items: [
          { id: "brief", title: "Как устроен курс и что мы создадим", type: "page", detail: "8 мин" },
          { id: "cases", title: "Галерея полезных ИИ-сервисов", type: "external", detail: "Внешний источник", external: true },
          { id: "map", title: "Карта проектного маршрута.pdf", type: "file", detail: "PDF · 1,4 МБ" },
        ],
      },
      {
        id: "rag",
        title: "01. Данные и поиск",
        items: [
          { id: "rag-section", title: "От документа к ответу", type: "section" },
          { id: "rag-pipeline", title: "Как устроен RAG-пайплайн", type: "page", detail: "12 мин" },
          { id: "chunking", title: "Практикум: нарезка и поиск", type: "assignment", due: "до 24 июля" },
          { id: "retrieval", title: "Визуальный разбор retrieval", type: "external", detail: "Внешний источник", external: true },
        ],
      },
      {
        id: "quality",
        title: "02. Качество и безопасность",
        items: [
          { id: "evidence", title: "Ответ, доказательство и уверенность", type: "page", detail: "10 мин" },
          { id: "red-team", title: "Проверка границ помощника", type: "assignment", due: "до 31 июля" },
          { id: "rubric", title: "Критерии качества прототипа.pdf", type: "file", detail: "PDF · 620 КБ" },
        ],
      },
      {
        id: "defense",
        title: "03. Защита проекта",
        items: [
          { id: "story", title: "Как объяснить ценность продукта", type: "page", detail: "7 мин" },
          { id: "demo", title: "Демо и защита ИИ-сервиса", type: "assignment", due: "до 7 августа" },
        ],
      },
    ],
    assignments: [
      { id: "chunking", title: "Практикум: нарезка и поиск", group: "Проектные работы", due: "24 июля, 18:00", points: 10, status: "upcoming" },
      { id: "red-team", title: "Проверка границ помощника", group: "Проектные работы", due: "31 июля, 18:00", points: 15, status: "open" },
      { id: "demo", title: "Демо и защита ИИ-сервиса", group: "Итоговая работа", due: "7 августа, 16:00", points: 30, status: "open" },
    ],
  },
  {
    id: "demo-review",
    title: "Русский язык: мастерская рецензии",
    code: "РЯ 10 · юнит 4",
    term: "2026/27 уч.год",
    color: "#b85149",
    illustration: "language",
    homeTitle: "Рецензия как аргументированный разговор",
    intro:
      "Синтетический syllabus-first курс: цели, критерии и итоговые работы собраны на стартовой странице, а модули используются как недельный маршрут.",
    objectives: [
      "выделять позицию автора и проверять силу аргумента",
      "различать наблюдение, интерпретацию и оценку",
      "собирать рецензию по прозрачным критериям",
    ],
    modules: [
      {
        id: "reading",
        title: "Неделя 1. Читаем как рецензенты",
        items: [
          { id: "reading-section", title: "От наблюдения к аргументу", type: "section" },
          { id: "lens", title: "Три оптики внимательного чтения", type: "page", detail: "9 мин" },
          { id: "sample", title: "Аннотированный пример рецензии.pdf", type: "file", detail: "PDF · 840 КБ" },
          { id: "notes", title: "Черновик аналитических заметок", type: "assignment", due: "до 22 июля" },
        ],
      },
      {
        id: "writing",
        title: "Неделя 2. Собираем текст",
        items: [
          { id: "criteria", title: "Критерии итоговой рецензии", type: "page", detail: "6 мин" },
          { id: "museum", title: "Цифровая коллекция музея", type: "external", detail: "Внешний источник", external: true },
          { id: "review", title: "Итоговая рецензия", type: "assignment", due: "до 29 июля" },
        ],
      },
    ],
    assignments: [
      { id: "notes", title: "Черновик аналитических заметок", group: "Подготовка", due: "22 июля, 20:00", points: 5, status: "upcoming" },
      { id: "review", title: "Итоговая рецензия", group: "Итоговая работа", due: "29 июля, 20:00", points: 20, status: "open" },
    ],
  },
  {
    id: "demo-math",
    title: "Математическое моделирование",
    code: "Математика 10",
    term: "2026/27 уч.год",
    color: "#3f8794",
    illustration: "math",
    homeTitle: "Модели и данные",
    intro: "Синтетический курс для dashboard-состояния.",
    objectives: [],
    modules: [],
    assignments: [],
  },
  {
    id: "demo-science",
    title: "Биология: эксперимент и доказательство",
    code: "БИО 10 · ФГОС",
    term: "2026/27 уч.год",
    color: "#7c8395",
    illustration: "science",
    homeTitle: "Эксперимент и доказательство",
    intro: "Синтетический курс для dashboard-состояния.",
    objectives: [],
    modules: [],
    assignments: [],
  },
  {
    id: "demo-community",
    title: "Проектная среда Летово",
    code: "Сообщество",
    term: "БЕССРОЧНО",
    color: "#725c9b",
    illustration: "community",
    homeTitle: "Проектная среда",
    intro: "Синтетический курс для dashboard-состояния.",
    objectives: [],
    modules: [],
    assignments: [],
  },
];

export function getCanvasDemoCourse(courseId: string | undefined) {
  return CANVAS_DEMO_COURSES.find((course) => course.id === courseId) || null;
}
