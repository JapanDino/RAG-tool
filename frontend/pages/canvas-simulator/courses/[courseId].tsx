import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { FormEvent, useMemo, useState } from "react";

import {
  CanvasCourseView,
  CanvasIcon,
  CanvasItemIcon,
  CanvasSimulatorShell,
  canvasSimulatorStyles as styles,
} from "../../../components/CanvasSimulatorShell";
import {
  CanvasDemoCourse,
  CanvasDemoItem,
  getCanvasDemoCourse,
} from "../../../lib/canvas-simulator-data";
import { canvasSimulatorServerProps } from "../../../lib/canvas-simulator-server";

export const getServerSideProps = canvasSimulatorServerProps;

const VIEW_SET = new Set<CanvasCourseView>(["home", "assignments", "syllabus", "modules", "assistant"]);
const ITEM_LABELS: Record<CanvasDemoItem["type"], string> = {
  page: "Страница",
  assignment: "Задание",
  file: "Файл",
  external: "Внешний источник",
  section: "Раздел",
};

type DemoAnswer = {
  kind: "supported" | "abstained";
  text: string;
};

const SUPPORTED_DEMO_ANSWERS: Record<string, { keywords: string[]; text: string }> = {
  "rag-pipeline": {
    keywords: ["rag", "поиск", "пайплайн", "фрагмент", "документ"],
    text: "Сначала система ищет подходящие фрагменты курса, а уже затем формирует объяснение с опорой на них. Эти два шага проверяют отдельно: хороший текст ответа не доказывает, что поиск нашёл правильный материал.",
  },
  evidence: {
    keywords: ["ответ", "модел", "доказ", "довер", "уверен", "источник"],
    text: "Ответ модели — это формулировка, а не доказательство. Доверие появляется, когда рядом виден конкретный материал курса, он действительно поддерживает вывод, а помощник честно обозначает границы уверенности.",
  },
  "red-team": {
    keywords: ["границ", "безопас", "ошиб", "провер", "атака"],
    text: "Проверка границ специально ищет случаи, где помощник должен отказаться, попросить уточнение или признать нехватку материала. Это помогает обнаружить уверенные, но неподтверждённые ответы до запуска для учеников.",
  },
  criteria: {
    keywords: ["критери", "рецензи", "аргумент", "оцен"],
    text: "Сильная рецензия отделяет наблюдение от интерпретации и оценки, формулирует позицию автора и подкрепляет каждый вывод конкретным фрагментом произведения.",
  },
};

type DemoBoundaryState = "loading" | "unavailable" | "expired" | "wrong-course" | "wrong-role" | "error" | "empty" | "unsupported";

const DEMO_BOUNDARY_COPY: Record<Exclude<DemoBoundaryState, "loading">, { eyebrow: string; title: string; detail: string; action: string }> = {
  unavailable: { eyebrow: "Материал недоступен", title: "Этот материал пока нельзя открыть", detail: "Он может быть ещё не опубликован или закрыт преподавателем. Другие опубликованные материалы курса остаются доступны.", action: "Вернуться к модулям" },
  expired: { eyebrow: "Сеанс завершён", title: "Откройте помощника из курса ещё раз", detail: "В целях безопасности просроченный запуск не восстанавливается автоматически. Данные курса не были показаны.", action: "Вернуться на панель" },
  "wrong-course": { eyebrow: "Не удалось открыть курс", title: "Запуск не совпадает с текущим курсом", detail: "Помощник ничего не открыл. Вернитесь в нужный курс и запустите его оттуда.", action: "Вернуться на панель" },
  "wrong-role": { eyebrow: "Доступ не подтверждён", title: "Помощник не открыл материалы", detail: "Для этого запуска нет подходящего доступа. Содержимое курса и сведения о пользователях не показаны.", action: "Вернуться на панель" },
  error: { eyebrow: "Временная ошибка", title: "Курс сейчас не загрузился", detail: "Ничего не потеряно и Canvas не изменён. Попробуйте открыть опубликованные модули ещё раз.", action: "Повторить" },
  empty: { eyebrow: "Нет поддерживаемых материалов", title: "Помощнику пока не на что опереться", detail: "В курсе не найдено опубликованных страниц, файлов или заданий, которые можно безопасно использовать.", action: "Вернуться к курсу" },
  unsupported: { eyebrow: "Формат не поддерживается", title: "Этот объект нельзя использовать как источник", detail: "Объект сохранён в структуре курса, но помощник не будет трактовать его как обычную страницу.", action: "Вернуться к модулям" },
};

function CourseBoundary({ course, state }: { course?: CanvasDemoCourse | null; state: DemoBoundaryState }) {
  if (state === "loading") {
    return <section className={styles.courseBoundary} role="status" aria-live="polite"><span>Локальное демо</span><h1>Загружаем курс…</h1><p>Проверяем контекст и доступные опубликованные материалы.</p></section>;
  }
  const copy = DEMO_BOUNDARY_COPY[state];
  const returnToCourse = course && !["expired", "wrong-course", "wrong-role"].includes(state);
  const href = returnToCourse ? `/canvas-simulator/courses/${course.id}?view=modules` : "/canvas-simulator";
  return (
    <section className={styles.courseBoundary} role="alert">
      <span>{copy.eyebrow}</span><h1>{copy.title}</h1><p>{copy.detail}</p><Link href={href}>{copy.action}</Link>
    </section>
  );
}

function CourseEmpty({ course }: { course: CanvasDemoCourse }) {
  return (
    <section className={styles.courseEmpty}>
      <span>Синтетический курс</span>
      <h1>{course.title}</h1>
      <p>Для этой карточки подготовлен только dashboard-сценарий. Полный маршрут доступен в курсе «Проектная лаборатория: ИИ-сервисы».</p>
      <Link href="/canvas-simulator/courses/demo-ai?view=modules">Открыть полный демо-курс</Link>
    </section>
  );
}

function CourseHome({ course, syllabusOnly = false }: { course: CanvasDemoCourse; syllabusOnly?: boolean }) {
  return (
    <div className={styles.courseColumns}>
      <article className={styles.syllabus}>
        <div className={styles.syllabusCover}>
          <span>{course.code}</span>
          <strong>{course.homeTitle}</strong>
          <i aria-hidden="true">✦</i>
        </div>
        <p className={styles.syntheticLabel}>Локальный синтетический курс · реальные данные Canvas не используются</p>
        <h1>{syllabusOnly ? "Программа обучения" : course.title}</h1>
        <p className={styles.lead}>{course.intro}</p>
        <h2>В этом курсе вы научитесь</h2>
        <ul className={styles.objectiveList}>
          {course.objectives.map((objective) => <li key={objective}>{objective}</li>)}
        </ul>
        <h2>Итоговые работы</h2>
        <div className={styles.assessmentTable} role="table" aria-label="Итоговые работы курса">
          <div role="row"><strong role="columnheader">Работа</strong><strong role="columnheader">Срок</strong><strong role="columnheader">Баллы</strong></div>
          {course.assignments.map((assignment) => (
            <div role="row" key={assignment.id}>
              <span role="cell">{assignment.title}</span><span role="cell">{assignment.due}</span><span role="cell">{assignment.points}</span>
            </div>
          ))}
        </div>
      </article>
      <aside className={styles.courseUtilities} aria-label="Инструменты курса">
        <Link href={`/canvas-simulator/courses/${course.id}?view=modules`}><CanvasIcon name="modules"/><span><strong>Просмотреть модули</strong><small>{course.modules.length} раздела курса</small></span></Link>
        <Link href={`/canvas-simulator/courses/${course.id}?view=assignments`}><CanvasIcon name="calendar"/><span><strong>Просмотреть задания</strong><small>{course.assignments.length} активных работы</small></span></Link>
        <Link href={`/canvas-simulator/courses/${course.id}?view=assistant`} className={styles.utilityAssistant}><CanvasIcon name="assistant"/><span><strong>Открыть помощника курса</strong><small>Ответы только по материалам курса</small></span></Link>
        <section><span>Дело</span><strong>Практикум: нарезка и поиск</strong><small>24 июля, 18:00</small></section>
      </aside>
    </div>
  );
}

function CourseModules({ course }: { course: CanvasDemoCourse }) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const allCollapsed = collapsed.size === course.modules.length;
  const toggle = (moduleId: string) => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(moduleId)) next.delete(moduleId); else next.add(moduleId);
      return next;
    });
  };
  return (
    <div className={styles.moduleColumns}>
      <section className={styles.modulesPanel} aria-labelledby="modules-title">
        <header>
          <div><span>{course.code}</span><h1 id="modules-title">Модули курса</h1></div>
          <button type="button" onClick={() => setCollapsed(allCollapsed ? new Set() : new Set(course.modules.map((module) => module.id)))}>
            {allCollapsed ? "Развернуть все" : "Свернуть все"}
          </button>
        </header>
        {course.modules.map((module) => {
          const isCollapsed = collapsed.has(module.id);
          return (
            <article className={styles.moduleBlock} key={module.id}>
              <button type="button" onClick={() => toggle(module.id)} aria-expanded={!isCollapsed}>
                <span aria-hidden="true">{isCollapsed ? "▸" : "▾"}</span>{module.title}<small>{module.items.filter((item) => item.type !== "section").length} материалов</small>
              </button>
              {!isCollapsed && (
                <ul>
                  {module.items.map((item) => item.type === "section" ? (
                    <li id={`canvas-item-${item.id}`} className={styles.moduleSectionLabel} key={item.id}><span>{item.title}</span></li>
                  ) : (
                    <li id={`canvas-item-${item.id}`} key={item.id}>
                      <CanvasItemIcon type={item.type}/>
                      <div><Link href={`/canvas-simulator/courses/${course.id}?view=assistant&source=${item.id}`}>{item.title}</Link><small>{ITEM_LABELS[item.type]}{item.detail ? ` · ${item.detail}` : ""}{item.due ? ` · ${item.due}` : ""}</small></div>
                      {item.external && <span className={styles.externalBadge}><CanvasIcon name="external" size={14}/> вне Canvas</span>}
                    </li>
                  ))}
                </ul>
              )}
            </article>
          );
        })}
      </section>
      <aside className={styles.courseUtilities} aria-label="Инструменты курса">
        <Link href={`/canvas-simulator/courses/${course.id}?view=home`}><CanvasIcon name="home"/><span><strong>Домашняя страница</strong><small>Цели и итоговые работы</small></span></Link>
        <Link href={`/canvas-simulator/courses/${course.id}?view=assistant`} className={styles.utilityAssistant}><CanvasIcon name="assistant"/><span><strong>Спросить по материалам</strong><small>Выберите источник или задайте вопрос</small></span></Link>
        <section><span>Последние отзывы</span><strong>Сейчас ничего</strong><small>В симуляторе нет сообщений учеников</small></section>
      </aside>
    </div>
  );
}

function CourseAssignments({ course }: { course: CanvasDemoCourse }) {
  const [query, setQuery] = useState("");
  const filtered = course.assignments.filter((assignment) => assignment.title.toLocaleLowerCase("ru").includes(query.toLocaleLowerCase("ru")));
  return (
    <section className={styles.assignmentsPanel}>
      <h1>Задания</h1>
      <div className={styles.assignmentTools}>
        <label><span>Поиск заданий</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Найти задание"/></label>
        <fieldset><legend>Показывать по</legend><label><input type="radio" name="group" defaultChecked/> дате</label><label><input type="radio" name="group"/> типу</label></fieldset>
      </div>
      <article className={styles.assignmentGroup}>
        <header><span>▾</span><strong>Предстоящие задания</strong><small>{filtered.length}</small></header>
        {filtered.length ? <ul>{filtered.map((assignment) => (
          <li key={assignment.id}>
            <CanvasIcon name="assignment"/>
            <div><strong>{assignment.title}</strong><span>{assignment.group} · срок {assignment.due}</span></div>
            <span>{assignment.points} бал.</span>
          </li>
        ))}</ul> : <p className={styles.assignmentEmpty}>По этому запросу заданий нет. Измените текст поиска.</p>}
      </article>
      <p className={styles.demoBoundary}>Это локальный интерфейсный тест. Отправка работ и изменение сроков отключены.</p>
    </section>
  );
}

function CourseAssistant({ course, initialSource }: { course: CanvasDemoCourse; initialSource?: string }) {
  const items = useMemo(() => course.modules.flatMap((module) => module.items.filter((item) => item.type !== "section").map((item) => ({ ...item, moduleTitle: module.title }))), [course]);
  const defaultItem = items.find((item) => item.id === initialSource) || items.find((item) => item.id === "rag-pipeline") || items[0];
  const [selectedId, setSelectedId] = useState(defaultItem?.id || "");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<DemoAnswer | null>(null);
  const selected = items.find((item) => item.id === selectedId) || defaultItem;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    const candidate = selected ? SUPPORTED_DEMO_ANSWERS[selected.id] : undefined;
    const normalizedQuestion = question.trim().toLocaleLowerCase("ru");
    if (candidate && candidate.keywords.some((keyword) => normalizedQuestion.includes(keyword))) {
      setAnswer({ kind: "supported", text: candidate.text });
      return;
    }
    setAnswer({
      kind: "abstained",
      text: "В выбранном материале недостаточно опоры для уверенного ответа на этот вопрос. Выберите другой источник или переформулируйте вопрос ближе к содержанию материала.",
    });
  };

  return (
    <section className={styles.companion} aria-labelledby="companion-title">
      <header className={styles.companionHero}>
        <div><span>Вы в курсе</span><h1 id="companion-title">{course.title}</h1><p>Продолжайте по знакомому маршруту Canvas или спросите по опубликованным материалам этого курса.</p></div>
        <div className={styles.companionStamp}><strong>Контур</strong><span>Помощник курса</span><small>Локальное демо</small></div>
      </header>
      <div className={styles.companionRoute} aria-label="Путь от Canvas к помощи">
        <span><i>К</i><strong>Курс Canvas</strong><small>контекст подтверждён</small></span><b aria-hidden="true">→</b>
        <span><i>М</i><strong>{selected?.moduleTitle.replace(/^\d+\.\s*/, "") || "Материал"}</strong><small>источник выбран</small></span><b aria-hidden="true">→</b>
        <span><i>?</i><strong>Помощник</strong><small>объясняет с опорой</small></span>
      </div>
      <div className={styles.companionWorkspace}>
        <aside className={styles.sourcePicker}>
          <span>Материалы курса</span>
          <h2>Выберите опору</h2>
          <div>
            {items.map((item) => (
              <button key={item.id} type="button" onClick={() => { setSelectedId(item.id); setAnswer(null); }} aria-pressed={selectedId === item.id}>
                <CanvasItemIcon type={item.type}/><span><strong>{item.title}</strong><small>{item.moduleTitle}</small></span>
              </button>
            ))}
          </div>
        </aside>
        <div className={styles.askDesk}>
          <div className={styles.selectedSource}>
            <span>Текущий источник · {selected ? ITEM_LABELS[selected.type] : "Материал"}</span>
            <h2>{selected?.title || "Материал не выбран"}</h2>
            <p>{selected?.detail || selected?.due || "Опубликованный материал демо-курса"}</p>
            <div>
              <Link href={`/canvas-simulator/courses/${course.id}?view=modules`}>Продолжить по курсу</Link>
              <Link href={`/canvas-simulator/courses/${course.id}?view=modules#canvas-item-${selected?.id || "course"}`}>Открыть источник</Link>
            </div>
          </div>
          <form onSubmit={submit} className={styles.askForm}>
            <label htmlFor="demo-question">Спросить по материалам</label>
            <div><textarea id="demo-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Например: почему качество поиска нужно проверять отдельно?"/><button type="submit" disabled={!question.trim()}>Спросить</button></div>
            <p>Помощник не видит оценки, работы учеников и скрытые материалы.</p>
          </form>
          <div className={styles.answerArea} aria-live="polite">
            {answer ? (
              <article>
                <span>{answer.kind === "supported" ? "Ответ по материалам курса" : "Недостаточно материала"}</span>
                <h2>{answer.kind === "supported" ? "Коротко и с проверяемой опорой" : "Лучше не угадывать"}</h2>
                <p>{answer.text}</p>
                {answer.kind === "supported" ? (
                  <footer>
                    <strong>Источник</strong>
                    <Link href={`/canvas-simulator/courses/${course.id}?view=modules#canvas-item-${selected?.id || "course"}`}>{selected?.title}</Link>
                    <small>Высокая опора · синтетический материал</small>
                  </footer>
                ) : (
                  <footer className={styles.abstentionFooter}><strong>Статус</strong><span>Ответ не сформирован</span><small>Нужна подтверждённая опора в материале курса</small></footer>
                )}
              </article>
            ) : (
              <div><i aria-hidden="true">?</i><strong>Здесь появится объяснение</strong><p>Выберите материал и задайте вопрос. Готовый ответ не подменяет выполнение задания.</p></div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function SignedCourseLaunch({
  course,
  launchUrl,
  actor,
}: {
  course: CanvasDemoCourse;
  launchUrl: string;
  actor: "learner" | "instructor";
}) {
  return (
    <section className={styles.signedLaunch} aria-labelledby="signed-launch-title">
      <header>
        <span>Локальная безопасная проверка</span>
        <h1 id="signed-launch-title">Помощник курса · {course.title}</h1>
        <p>Внутри рамки повторяется подписанный запуск для точного синтетического курса. Школьный Canvas и его данные не используются.</p>
      </header>
      <nav className={styles.simulatorRoleSwitch} aria-label="Роль локальной проверки">
        <span>Проверить как</span>
        <Link
          href={`/canvas-simulator/courses/${course.id}?view=assistant&actor=learner`}
          aria-current={actor === "learner" ? "page" : undefined}
        >
          Ученик
        </Link>
        <Link
          href={`/canvas-simulator/courses/${course.id}?view=assistant&actor=instructor`}
          aria-current={actor === "instructor" ? "page" : undefined}
        >
          Преподаватель
        </Link>
        <strong role="status">
          Сейчас: {actor === "learner" ? "ученический помощник" : "рабочее место преподавателя"}
        </strong>
      </nav>
      <iframe
        src={launchUrl}
        title={`Подписанный запуск: ${actor === "learner" ? "ученик" : "преподаватель"} — ${course.title}`}
      />
    </section>
  );
}

export default function CanvasSimulatorCoursePage({
  ltiLaunchUrl = null,
  simulatorActor = "learner",
  simulatorLaunchState = "unavailable",
}: {
  ltiLaunchUrl?: string | null;
  simulatorActor?: "learner" | "instructor";
  simulatorLaunchState?: "ready" | "unavailable" | "preview";
}) {
  const router = useRouter();
  const rawCourseId = router.query.courseId;
  const courseId = Array.isArray(rawCourseId) ? rawCourseId[0] : rawCourseId;
  const course = getCanvasDemoCourse(courseId);
  const rawView = Array.isArray(router.query.view) ? router.query.view[0] : router.query.view;
  const view: CanvasCourseView = rawView && VIEW_SET.has(rawView as CanvasCourseView) ? rawView as CanvasCourseView : "modules";
  const rawSource = Array.isArray(router.query.source) ? router.query.source[0] : router.query.source;
  const rawState = Array.isArray(router.query.state) ? router.query.state[0] : router.query.state;
  const boundaryState = rawState && rawState in DEMO_BOUNDARY_COPY ? rawState as DemoBoundaryState : rawState === "loading" ? "loading" : null;

  if (!router.isReady) return <CanvasSimulatorShell><CourseBoundary state="loading" /></CanvasSimulatorShell>;
  if (!course) {
    return (
      <CanvasSimulatorShell>
        <section className={styles.courseNotFound}><span>Курс не найден</span><h1>В симуляторе нет такого курса</h1><Link href="/canvas-simulator">Вернуться на панель</Link></section>
      </CanvasSimulatorShell>
    );
  }

  if (boundaryState) {
    const discloseCourse = !["expired", "wrong-course", "wrong-role"].includes(boundaryState);
    return (
      <CanvasSimulatorShell course={discloseCourse ? course : undefined} activeGlobal="courses" activeCourse={view}>
        <CourseBoundary course={discloseCourse ? course : null} state={boundaryState} />
      </CanvasSimulatorShell>
    );
  }

  const hasFullCourse = course.modules.length > 0;
  return (
    <>
      <Head><title>{`${course.title} — Canvas simulator`}</title><meta name="robots" content="noindex,nofollow"/></Head>
      <CanvasSimulatorShell course={course} activeGlobal="courses" activeCourse={view}>
        {!hasFullCourse ? <CourseEmpty course={course}/> : view === "home" ? <CourseHome course={course}/> : view === "syllabus" ? <CourseHome course={course} syllabusOnly/> : view === "assignments" ? <CourseAssignments course={course}/> : view === "assistant" && simulatorLaunchState === "ready" && ltiLaunchUrl ? <SignedCourseLaunch course={course} launchUrl={ltiLaunchUrl} actor={simulatorActor}/> : view === "assistant" && simulatorLaunchState === "preview" ? <CourseAssistant course={course} initialSource={rawSource}/> : view === "assistant" ? <CourseBoundary course={course} state="unavailable"/> : <CourseModules course={course}/>}
      </CanvasSimulatorShell>
    </>
  );
}
