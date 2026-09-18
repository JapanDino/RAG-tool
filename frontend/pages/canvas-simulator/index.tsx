import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";

import {
  CanvasArtwork,
  CanvasIcon,
  CanvasSimulatorShell,
  canvasSimulatorStyles as styles,
} from "../../components/CanvasSimulatorShell";
import { CANVAS_DEMO_COURSES } from "../../lib/canvas-simulator-data";
import { canvasSimulatorServerProps } from "../../lib/canvas-simulator-server";

export const getServerSideProps = canvasSimulatorServerProps;

const PANEL_COPY: Record<string, { title: string; description: string }> = {
  account: { title: "Аккаунт", description: "В демо-режиме профиль не содержит персональных данных." },
  courses: { title: "Курсы", description: "Все синтетические курсы уже показаны на панели." },
  calendar: { title: "Календарь", description: "Сроки демо-заданий появятся здесь после следующего среза." },
  inbox: { title: "Входящие", description: "Сообщения отключены: симулятор ничего не отправляет." },
  history: { title: "История", description: "История браузера и реального Canvas не читается." },
  library: { title: "Библиотека", description: "Библиотека будет проверяться отдельным синтетическим курсом." },
  help: { title: "Справка", description: "Откройте демо-курс и выберите «Помощник курса»." },
};

export default function CanvasSimulatorDashboard() {
  const router = useRouter();
  const rawPanel = router.query.panel;
  const panel = Array.isArray(rawPanel) ? rawPanel[0] : rawPanel;
  const panelCopy = panel ? PANEL_COPY[panel] : null;

  return (
    <>
      <Head>
        <title>Панель информации — Canvas simulator</title>
        <meta name="robots" content="noindex,nofollow" />
      </Head>
      <CanvasSimulatorShell activeGlobal={panel === "courses" ? "courses" : "dashboard"}>
        <header className={styles.dashboardHeader}>
          <div>
            <span>Canvas Letovo · локальная среда</span>
            <h1>Панель информации</h1>
          </div>
          <button type="button" aria-label="Опции панели информации"><CanvasIcon name="more" /></button>
        </header>

        {panelCopy && (
          <section className={styles.demoNotice} aria-label={panelCopy.title}>
            <div><strong>{panelCopy.title}</strong><p>{panelCopy.description}</p></div>
            <Link href="/canvas-simulator">Вернуться к курсам</Link>
          </section>
        )}

        <section className={styles.courseDashboard} aria-labelledby="published-courses">
          <header>
            <div>
              <h2 id="published-courses">Опубликованные курсы ({CANVAS_DEMO_COURSES.length})</h2>
              <p>Все названия и материалы синтетические. Школьный Canvas не подключён.</p>
            </div>
            <span>Демо-среда</span>
          </header>
          <div className={styles.courseGrid}>
            {CANVAS_DEMO_COURSES.map((course) => (
              <article className={styles.courseCard} key={course.id}>
                <CanvasArtwork course={course} />
                <button type="button" aria-label={`Опции курса ${course.title}`}><CanvasIcon name="more" /></button>
                <div>
                  <Link href={`/canvas-simulator/courses/${course.id}?view=${course.id === "demo-review" || !course.modules.length ? "home" : "modules"}`}>
                    <strong>{course.title}</strong>
                    <span>{course.code}</span>
                    <small>{course.term}</small>
                  </Link>
                  <nav aria-label={`Быстрые действия курса ${course.title}`}>
                    <Link href={`/canvas-simulator/courses/${course.id}?view=assistant`} aria-label={`Помощник курса — ${course.title}`}><CanvasIcon name="assistant" /></Link>
                    <Link href={`/canvas-simulator/courses/${course.id}?view=assignments`} aria-label={`Задания — ${course.title}`}><CanvasIcon name="assignment" /></Link>
                    <Link href={`/canvas-simulator/courses/${course.id}?view=modules`} aria-label={`Модули — ${course.title}`}><CanvasIcon name="file" /></Link>
                  </nav>
                </div>
              </article>
            ))}
          </div>
        </section>
      </CanvasSimulatorShell>
    </>
  );
}
