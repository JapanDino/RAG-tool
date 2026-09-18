import Head from "next/head";
import Link from "next/link";
import { useRef, useState } from "react";

import styles from "../../styles/workshop-workspace.module.css";

type Course = {
  id: number;
  title: string;
  description: string;
  attention: string;
  action: string;
};

const COURSES: Course[] = [
  {
    id: 1,
    title: "Демо: алгоритмы сортировки",
    description: "Проблемный учебный модуль для проверки связей и рекомендаций.",
    attention: "3 связи требуют просмотра",
    action: "Открыть очередь внимания",
  },
  {
    id: 2,
    title: "Основы исследовательского проекта",
    description: "Маршрут от исследовательского вопроса до защищаемого результата.",
    attention: "Маршрут собран",
    action: "Открыть карту курса",
  },
];

function CourseRoute({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={`${styles.courseRoute} ${compact ? styles.courseRouteCompact : ""}`}
      aria-label="Цель связана с материалом и проверкой"
    >
      <span className={styles.routeStation}>
        <i />
        <strong>Цель</strong>
      </span>
      <span className={styles.routeLine} aria-hidden="true" />
      <span className={styles.routeStation}>
        <i />
        <strong>Материал</strong>
      </span>
      <span className={styles.routeLine} aria-hidden="true" />
      <span className={styles.routeStation}>
        <i />
        <strong>Проверка</strong>
      </span>
    </div>
  );
}

export default function WorkshopWorkspacePage() {
  const [selectedId, setSelectedId] = useState(1);
  const detailRef = useRef<HTMLElement | null>(null);
  const selectedCourse = COURSES.find((course) => course.id === selectedId) || COURSES[0];

  const selectCourse = (courseId: number) => {
    setSelectedId(courseId);
    if (window.matchMedia("(max-width: 900px)").matches) {
      window.requestAnimationFrame(() => {
        detailRef.current?.scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto"
            : "smooth",
          block: "start",
        });
      });
    }
  };

  return (
    <>
      <Head>
        <title>Маршрут мастерской — полная страница «Контура»</title>
        <meta
          name="description"
          content="Полноэкранный дизайн-прототип рабочего пространства в направлении Маршрут мастерской"
        />
      </Head>

      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.brandBlock}>
            <Link href="/workspace" className={styles.brandMark} aria-label="Контур обучения">
              К
            </Link>
            <div>
              <strong>Контур</strong>
              <span>рабочая карта школы</span>
            </div>
          </div>

          <div className={styles.headerRoute} aria-label="Состояние учебного маршрута">
            <span>Карта открыта</span>
            <CourseRoute compact />
          </div>

          <div className={styles.roleBlock}>
            <span>Рабочая роль</span>
            <strong>Ольга Белова · Администратор</strong>
          </div>
        </header>

        <div className={styles.shell}>
          <aside className={styles.sidebar}>
            <div className={styles.sidebarTape} aria-hidden="true" />
            <span className={styles.sidebarEyebrow}>Вы работаете как</span>
            <h2>Администратор</h2>
            <nav aria-label="Разделы рабочего пространства">
              <a href="#overview" className={styles.navActive}>
                <i />
                <span>Обзор маршрута</span>
                <small>сейчас</small>
              </a>
              <span className={styles.navPending}>
                <i />
                <span>Доступы</span>
                <small>скоро</small>
              </span>
              <span className={styles.navPending}>
                <i />
                <span>Состояние системы</span>
                <small>скоро</small>
              </span>
            </nav>

            <div className={styles.organizationNote}>
              <span>Организация</span>
              <strong>Локальная школа</strong>
              <small>Демонстрационные данные</small>
            </div>

            <Link href="/design-lab/workspace-hero-variants" className={styles.backLink}>
              ← К пяти вариантам
            </Link>
          </aside>

          <main className={styles.main} id="overview">
            <section className={styles.hero} aria-labelledby="workshop-title">
              <span className={styles.heroTape} aria-hidden="true" />
              <span className={styles.heroMarker} aria-hidden="true" />

              <div className={styles.heroCopy}>
                <span className={styles.eyebrow}>Контур организации</span>
                <h1 id="workshop-title">Доступы и качество — в разных слоях</h1>
                <p>
                  Управляйте назначениями отдельно от учебной аналитики и переходите
                  к курсу только в рамках рабочей необходимости.
                </p>
                <div className={styles.heroActionGroup}>
                  <div className={styles.heroActions} aria-label="Основные направления">
                    <button type="button" className={styles.primaryAction} disabled>
                      Открыть обзор программ
                    </button>
                    <button type="button" className={styles.secondaryAction} disabled>
                      Подключить Canvas
                    </button>
                  </div>
                  <span className={styles.prototypeHint}>Недоступно в дизайн-прототипе</span>
                </div>
              </div>

              <div className={styles.heroMap}>
                <span className={styles.mapLabel}>Живой маршрут</span>
                <div className={styles.roleNote}>
                  <small>Ваш контур</small>
                  <strong>Администратор</strong>
                </div>
                <CourseRoute />
              </div>
            </section>

            <section className={styles.courseSection} aria-labelledby="courses-title">
              <div className={styles.sectionHeading}>
                <div>
                  <span>Следующая остановка</span>
                  <h2 id="courses-title">Назначенные курсы</h2>
                </div>
                <div className={styles.courseCount}>{COURSES.length} маршрута</div>
              </div>

              <div className={styles.courseList}>
                {COURSES.map((course, index) => {
                  const selected = course.id === selectedId;
                  return (
                    <button
                      type="button"
                      key={course.id}
                      className={`${styles.courseCard} ${selected ? styles.courseCardSelected : ""}`}
                      aria-pressed={selected}
                      aria-controls="workshop-current-course"
                      onClick={() => selectCourse(course.id)}
                    >
                      <span className={styles.coursePin}>{String(index + 1).padStart(2, "0")}</span>
                      <span className={styles.courseCopy}>
                        <strong>{course.title}</strong>
                        <small>{course.description}</small>
                      </span>
                      <CourseRoute compact />
                      <span className={styles.courseStatus}>{course.attention}</span>
                      <span className={styles.courseAction}>
                        {selected ? "Выбран" : "Показать действия"}
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>

            <aside className={styles.safetyNote}>
              <span>Граница страницы</span>
              <strong>Здесь нет рейтингов преподавателей или учеников</strong>
              <p>
                Административный обзор показывает только рабочие маршруты и
                агрегированные связи.
              </p>
            </aside>
          </main>

          <aside
            className={styles.detailPanel}
            id="workshop-current-course"
            ref={detailRef}
            aria-live="polite"
          >
            <div className={styles.detailTape} aria-hidden="true" />
            <span className={styles.detailEyebrow}>Текущий курс</span>
            <h2>{selectedCourse.title}</h2>
            <span className={styles.roleTag}>Администратор</span>

            <div className={styles.detailRoute}>
              <CourseRoute />
            </div>

            <div className={styles.detailStatus}>
              <span>Состояние маршрута</span>
              <strong>{selectedCourse.attention}</strong>
            </div>

            <p className={styles.detailText}>
              Контекст доступа проверен. Действия относятся только к выбранному
              курсу и не изменяют Canvas автоматически.
            </p>

            <button type="button" className={styles.detailAction} disabled>
              {selectedCourse.action}
            </button>
            <span className={styles.prototypeHint}>Недоступно в дизайн-прототипе</span>

            <div className={styles.detailHint}>
              <strong>Сначала доказательство</strong>
              <span>Каждая рекомендация открывается вместе с источником и статусом проверки.</span>
            </div>
          </aside>
        </div>
      </div>
    </>
  );
}
