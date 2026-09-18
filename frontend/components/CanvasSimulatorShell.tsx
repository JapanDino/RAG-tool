import Link from "next/link";
import React, { ReactNode, useEffect, useRef, useState } from "react";

import type {
  CanvasDemoCourse,
  CanvasDemoItemType,
} from "../lib/canvas-simulator-data";
import styles from "../styles/canvas-simulator.module.css";

type IconName =
  | "account"
  | "dashboard"
  | "courses"
  | "calendar"
  | "inbox"
  | "history"
  | "library"
  | "help"
  | "menu"
  | "home"
  | "assignment"
  | "discussion"
  | "grades"
  | "people"
  | "page"
  | "file"
  | "syllabus"
  | "modules"
  | "assistant"
  | "external"
  | "chevron"
  | "more";

const ICON_PATHS: Record<IconName, ReactNode> = {
  account: <><circle cx="12" cy="8" r="3.5"/><path d="M5 20c.7-4 3.1-6 7-6s6.3 2 7 6"/></>,
  dashboard: <><path d="M4 15a8 8 0 1 1 16 0"/><path d="m12 15 4-5"/><path d="M6 18h12"/></>,
  courses: <><path d="M5 4h14v16H5z"/><path d="M8 8h8M8 12h8M8 16h5"/></>,
  calendar: <><rect x="4" y="5" width="16" height="15" rx="1"/><path d="M8 3v4M16 3v4M4 10h16M8 14h2M14 14h2"/></>,
  inbox: <><path d="M5 4h14l2 10v6H3v-6z"/><path d="M3 14h5l1 2h6l1-2h5"/></>,
  history: <><circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/></>,
  library: <><path d="M5 5h3v15H5zM10 3h3v17h-3zM15 6h3v14h-3z"/><path d="M3 20h18"/></>,
  help: <><circle cx="12" cy="12" r="9"/><path d="M9.8 9a2.4 2.4 0 1 1 3.7 2c-1 .7-1.5 1.1-1.5 2.5M12 17h.01"/></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16"/>,
  home: <><path d="m4 11 8-7 8 7"/><path d="M6 10v10h12V10M10 20v-6h4v6"/></>,
  assignment: <><path d="M7 4h10v16H7z"/><path d="M9 8h6M9 12h6M9 16h4"/><path d="M10 4V2h4v2"/></>,
  discussion: <><path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/></>,
  grades: <><path d="M5 20V9M10 20V4M15 20v-7M20 20V7"/><path d="M3 20h19"/></>,
  people: <><circle cx="9" cy="8" r="3"/><circle cx="17" cy="10" r="2.5"/><path d="M3 20c.5-4 2.5-6 6-6s5.5 2 6 6M15 15c3.2 0 5 1.7 5.5 5"/></>,
  page: <><path d="M6 3h9l3 3v15H6z"/><path d="M14 3v4h4M9 11h6M9 15h6"/></>,
  file: <><path d="M5 5h6l2 2h6v13H5z"/><path d="M8 12h8M8 16h5"/></>,
  syllabus: <><path d="M4 5h7v15H4zM13 5h7v15h-7z"/><path d="M7 9h2M7 13h2M16 9h2M16 13h2"/></>,
  modules: <><rect x="4" y="4" width="16" height="5"/><rect x="4" y="11" width="16" height="4"/><rect x="4" y="17" width="16" height="3"/></>,
  assistant: <><path d="M5 5h14v11H9l-4 4z"/><path d="M9 10h.01M12 10h.01M15 10h.01"/></>,
  external: <><path d="M13 5h6v6M19 5l-8 8"/><path d="M17 14v5H5V7h5"/></>,
  chevron: <path d="m9 6 6 6-6 6"/>,
  more: <><circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/></>,
};

export function CanvasIcon({ name, size = 24 }: { name: IconName; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      className={styles.icon}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {ICON_PATHS[name]}
    </svg>
  );
}

const GLOBAL_NAV: { key: IconName; label: string; href: string }[] = [
  { key: "account", label: "Аккаунт", href: "/canvas-simulator?panel=account" },
  { key: "dashboard", label: "Панель", href: "/canvas-simulator" },
  { key: "courses", label: "Курсы", href: "/canvas-simulator?panel=courses" },
  { key: "calendar", label: "Календарь", href: "/canvas-simulator?panel=calendar" },
  { key: "inbox", label: "Входящие", href: "/canvas-simulator?panel=inbox" },
  { key: "history", label: "История", href: "/canvas-simulator?panel=history" },
  { key: "library", label: "Библиотека", href: "/canvas-simulator?panel=library" },
  { key: "help", label: "Справка", href: "/canvas-simulator?panel=help" },
];

export type CanvasCourseView = "home" | "assignments" | "syllabus" | "modules" | "assistant";

const COURSE_NAV: { key: IconName; label: string; view: CanvasCourseView | "disabled" }[] = [
  { key: "home", label: "Домашняя страница", view: "home" },
  { key: "assignment", label: "Задания", view: "assignments" },
  { key: "discussion", label: "Обсуждения", view: "disabled" },
  { key: "grades", label: "Оценки", view: "disabled" },
  { key: "people", label: "Пользователи", view: "disabled" },
  { key: "page", label: "Страницы", view: "disabled" },
  { key: "file", label: "Файлы", view: "disabled" },
  { key: "syllabus", label: "Программа обучения", view: "syllabus" },
  { key: "modules", label: "Модули", view: "modules" },
  { key: "assistant", label: "Помощник курса", view: "assistant" },
];

export function CanvasArtwork({ course }: { course: CanvasDemoCourse }) {
  return (
    <div className={styles.courseArtwork} data-art={course.illustration} style={{ "--course-color": course.color } as React.CSSProperties}>
      <span className={styles.artOrb} />
      <span className={styles.artLine} />
      <span className={styles.artTile}>AI</span>
      <span className={styles.artSpark}>✦</span>
    </div>
  );
}

export function CanvasSimulatorShell({
  children,
  activeGlobal = "dashboard",
  course,
  activeCourse,
}: {
  children: ReactNode;
  activeGlobal?: IconName;
  course?: CanvasDemoCourse;
  activeCourse?: CanvasCourseView;
}) {
  const [mobileMenu, setMobileMenu] = useState(false);
  const mobileMenuButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!mobileMenu) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileMenu(false);
        mobileMenuButton.current?.focus();
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [mobileMenu]);

  const closeMobileMenu = () => {
    setMobileMenu(false);
    mobileMenuButton.current?.focus();
  };
  return (
    <div className={styles.canvasApp} data-simulator="canvas-letovo">
      <header className={styles.mobileHeader}>
        <button ref={mobileMenuButton} type="button" aria-label={mobileMenu ? "Закрыть меню Canvas" : "Открыть меню Canvas"} aria-expanded={mobileMenu} onClick={() => setMobileMenu((value) => !value)}>
          <CanvasIcon name="menu" />
        </button>
        <strong>{course?.title || "Панель информации"}</strong>
        <span className={styles.mobileAvatar}>А</span>
      </header>

      {mobileMenu && <button className={styles.mobileBackdrop} type="button" aria-label="Закрыть меню Canvas" onClick={closeMobileMenu} />}

      <aside className={`${styles.globalRail} ${mobileMenu ? styles.globalRailOpen : ""}`} aria-label="Глобальная навигация Canvas">
        <div className={styles.letovoMark} aria-label="Локальный Canvas simulator"><span /><span /><span /></div>
        <nav>
          {GLOBAL_NAV.map((item) => (
            <Link
              href={item.href}
              key={item.key}
              className={activeGlobal === item.key ? styles.globalActive : ""}
              aria-current={activeGlobal === item.key ? "page" : undefined}
              onClick={() => setMobileMenu(false)}
            >
              {item.key === "account" ? <span className={styles.avatar}>А</span> : <CanvasIcon name={item.key} size={29} />}
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>
        <button className={styles.railCollapse} type="button" aria-label="Свернуть глобальную навигацию">‹</button>
      </aside>

      <div className={styles.canvasBody}>
        {course ? (
          <>
            <header className={styles.courseTopbar}>
              <button className={styles.courseMenuButton} type="button" aria-label="Открыть меню курса" onClick={() => setMobileMenu((value) => !value)}>
                <CanvasIcon name="menu" />
              </button>
              <Link href={`/canvas-simulator/courses/${course.id}?view=home`}>{course.title}</Link>
              <CanvasIcon name="chevron" size={17} />
              <strong>{COURSE_NAV.find((item) => item.view === activeCourse)?.label || "Курс"}</strong>
              <span className={styles.demoFlag}>Локальный демо-курс</span>
            </header>
            <div className={styles.courseLayout}>
              <aside className={styles.courseSidebar}>
                <span>{course.term}</span>
                <nav aria-label="Навигация курса">
                  {COURSE_NAV.map((item, index) => {
                    const disabled = item.view === "disabled";
                    if (disabled) {
                      return <span key={`${item.key}-${index}`} aria-disabled="true"><CanvasIcon name={item.key} size={18}/>{item.label}</span>;
                    }
                    return (
                      <Link
                        key={`${item.key}-${item.view}`}
                        href={`/canvas-simulator/courses/${course.id}?view=${item.view}`}
                        className={activeCourse === item.view ? styles.courseActive : ""}
                        aria-current={activeCourse === item.view ? "page" : undefined}
                      >
                        <CanvasIcon name={item.key} size={18}/>{item.label}
                      </Link>
                    );
                  })}
                </nav>
              </aside>
              <main className={styles.courseMain}>{children}</main>
            </div>
          </>
        ) : (
          <main className={styles.dashboardMain}>{children}</main>
        )}
      </div>
    </div>
  );
}

export function CanvasItemIcon({ type }: { type: CanvasDemoItemType }) {
  const icon: IconName = type === "assignment" ? "assignment" : type === "file" ? "file" : type === "external" ? "external" : type === "section" ? "modules" : "page";
  return <CanvasIcon name={icon} size={20} />;
}

export { styles as canvasSimulatorStyles };
