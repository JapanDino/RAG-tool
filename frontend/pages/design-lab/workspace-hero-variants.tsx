import Head from "next/head";
import Link from "next/link";
import { useState } from "react";

import styles from "../../styles/workspace-hero-variants.module.css";

type VariantId = "orbit" | "workshop" | "layers" | "portal" | "fold";

type Variant = {
  id: VariantId;
  number: string;
  name: string;
  note: string;
};

const VARIANTS: Variant[] = [
  {
    id: "orbit",
    number: "01",
    name: "Орбитальный атлас",
    note: "Живая система связей вокруг текущей роли",
  },
  {
    id: "workshop",
    number: "02",
    name: "Маршрут мастерской",
    note: "Тактильная карта, собранная из учебных ориентиров",
  },
  {
    id: "layers",
    number: "03",
    name: "Слои программы",
    note: "Глубина и прозрачность вместо набора карточек",
  },
  {
    id: "portal",
    number: "04",
    name: "Учебный портал",
    note: "Иммерсивный вход в рабочее пространство",
  },
  {
    id: "fold",
    number: "05",
    name: "Складная карта",
    note: "Маршрутный лист с выразительной геометрией",
  },
];

const VARIANT_CLASS: Record<VariantId, string> = {
  orbit: styles.orbit,
  workshop: styles.workshop,
  layers: styles.layers,
  portal: styles.portal,
  fold: styles.fold,
};

function CourseRoute() {
  return (
    <div className={styles.courseRoute} aria-label="Цель связана с материалом и проверкой">
      <span className={styles.routeNode}>
        <i />
        <strong>Цель</strong>
      </span>
      <span className={styles.routeLine} aria-hidden="true" />
      <span className={styles.routeNode}>
        <i />
        <strong>Материал</strong>
      </span>
      <span className={styles.routeLine} aria-hidden="true" />
      <span className={styles.routeNode}>
        <i />
        <strong>Проверка</strong>
      </span>
    </div>
  );
}

function HeroVariant({
  variant,
  selected,
  onSelect,
}: {
  variant: Variant;
  selected: boolean;
  onSelect: (variant: VariantId) => void;
}) {
  const headingId = `variant-${variant.id}`;

  return (
    <article
      className={`${styles.preview} ${VARIANT_CLASS[variant.id]} ${
        selected ? styles.previewSelected : ""
      }`}
      id={variant.id}
      aria-labelledby={headingId}
    >
      <header className={styles.conceptHeader}>
        <div className={styles.conceptIdentity}>
          <span>{variant.number}</span>
          <div>
            <h2 id={headingId}>{variant.name}</h2>
            <p>{variant.note}</p>
          </div>
        </div>
        <label className={styles.choice}>
          <input
            type="radio"
            name="workspace-hero-variant"
            value={variant.id}
            aria-label={`Выбрать вариант ${variant.number}: ${variant.name}`}
            checked={selected}
            onChange={() => onSelect(variant.id)}
          />
          <span>{selected ? "Выбран" : "Выбрать этот вариант"}</span>
        </label>
      </header>

      <section className={styles.heroBlock} aria-label={`Пример: ${variant.name}`}>
        <span className={`${styles.shape} ${styles.shapeOne}`} aria-hidden="true" />
        <span className={`${styles.shape} ${styles.shapeTwo}`} aria-hidden="true" />

        <div className={styles.heroCopy}>
          <span className={styles.eyebrow}>Контур организации</span>
          <h3>Доступы и качество — в разных слоях</h3>
          <p>
            Управляйте назначениями отдельно от учебной аналитики и переходите к
            курсу только в рамках рабочей необходимости.
          </p>
          <div className={styles.actions} aria-label="Доступные действия">
            <span className={styles.primaryAction}>Открыть обзор программ</span>
            <span className={styles.secondaryAction}>Подключить Canvas</span>
          </div>
        </div>

        <div className={styles.visual}>
          <span className={styles.visualLabel}>Живой маршрут</span>
          <div className={styles.roleCard}>
            <small>Ваш контур</small>
            <strong>Администратор</strong>
          </div>
          <CourseRoute />
        </div>
      </section>
    </article>
  );
}

export default function WorkspaceHeroVariantsPage() {
  const [selected, setSelected] = useState<VariantId | null>(null);
  const selectedVariant = VARIANTS.find((variant) => variant.id === selected);

  return (
    <>
      <Head>
        <title>Пять направлений рабочего пространства — Контур</title>
        <meta
          name="description"
          content="Сравнение пяти визуальных направлений одного блока рабочего пространства"
        />
      </Head>

      <main className={styles.page}>
        <header className={styles.reviewHeader}>
          <div className={styles.reviewTopline}>
            <Link href="/workspace">← Рабочее пространство</Link>
            <span>Design lab · UX02</span>
          </div>
          <div className={styles.reviewIntro}>
            <div>
              <span className={styles.reviewEyebrow}>Один блок · пять характеров</span>
              <h1>Выберите визуальный язык «Контура»</h1>
              <p>
                Текст, действия и смысл везде одинаковые. Меняется только то, как
                продукт объясняет себя через пространство, типографику и нить курса.
              </p>
            </div>
            <div className={styles.selectionSummary}>
              <small>Ваш выбор</small>
              <strong>{selectedVariant?.name || "Пока не выбран"}</strong>
              <span>
                {selectedVariant
                  ? `Вариант ${selectedVariant.number} отмечен для следующего этапа.`
                  : "Просмотрите все пять направлений ниже."}
              </span>
            </div>
          </div>
          <nav className={styles.variantNav} aria-label="Быстрый переход к вариантам">
            {VARIANTS.map((variant) => (
              <a key={variant.id} href={`#${variant.id}`}>
                <span>{variant.number}</span>
                {variant.name}
              </a>
            ))}
          </nav>
        </header>

        <div className={styles.stickyChoice} aria-live="polite">
          <span>Выбранный вариант</span>
          <strong>{selectedVariant ? `${selectedVariant.number} · ${selectedVariant.name}` : "—"}</strong>
        </div>

        <section className={styles.previewList} aria-label="Варианты дизайна">
          {VARIANTS.map((variant) => (
            <HeroVariant
              key={variant.id}
              variant={variant}
              selected={selected === variant.id}
              onSelect={setSelected}
            />
          ))}
        </section>
      </main>
    </>
  );
}
