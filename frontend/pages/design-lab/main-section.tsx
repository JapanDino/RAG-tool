import React from "react";
import Head from "next/head";
import Script from "next/script";
import styles from "../../styles/design-lab-main-section.module.css";

const sections = ["Overview", "Documents", "Analysis", "Graph", "Review"];

const lightMetrics = [
  { label: "Active courses", value: "24", detail: "+4 this week" },
  { label: "Knowledge nodes", value: "18.4k", detail: "Across 12 uploaded packs" },
  { label: "Review queue", value: "312", detail: "58 need manual check" },
];

const darkMetrics = [
  { label: "Graph coverage", value: "82%", detail: "Stable mapping on current set" },
  { label: "Bloom balance", value: "6/6", detail: "Every level represented" },
  { label: "Export status", value: "Ready", detail: "JSONL and CSV synced" },
];

const documents = [
  { title: "Case studies / Spring term.pdf", meta: "18 pages, OCR cleaned", state: "In analysis" },
  { title: "Lecture set / Module 04", meta: "7 files, semantic links found", state: "Mapped" },
  { title: "Exam prep / Taxonomy notes", meta: "Text + references", state: "Needs review" },
];

const graphLevels = [
  { label: "Remember", width: "72%", tone: "var(--blue-strong)" },
  { label: "Understand", width: "84%", tone: "var(--green-strong)" },
  { label: "Apply", width: "61%", tone: "var(--gold-strong)" },
  { label: "Analyze", width: "67%", tone: "var(--terracotta-strong)" },
  { label: "Evaluate", width: "44%", tone: "var(--violet-strong)" },
  { label: "Create", width: "39%", tone: "var(--teal-strong)" },
];

function BrandMark() {
  return (
    <svg viewBox="0 0 48 48" className={styles.brandMark} aria-hidden="true">
      <rect x="4" y="4" width="40" height="40" rx="14" fill="currentColor" opacity="0.11" />
      <path
        d="M15 31.5V16.5H23.3C28 16.5 30.7 18.9 30.7 22.7C30.7 26.5 28 28.9 23.3 28.9H18.5V31.5H15ZM18.5 26.1H23C25.8 26.1 27.1 24.9 27.1 22.7C27.1 20.5 25.8 19.3 23 19.3H18.5V26.1Z"
        fill="currentColor"
      />
      <circle cx="34.5" cy="16.5" r="3.5" fill="currentColor" />
    </svg>
  );
}

function ThemePreview({
  theme,
  title,
  caption,
  metrics,
}: {
  theme: "light" | "dark";
  title: string;
  caption: string;
  metrics: { label: string; value: string; detail: string }[];
}) {
  return (
    <section className={`${styles.themeCard} ${theme === "dark" ? styles.themeDark : styles.themeLight}`}>
      <header className={styles.themeHeader}>
        <div className={styles.brandCluster}>
          <BrandMark />
          <div>
            <div className={styles.themeName}>{title}</div>
            <div className={styles.themeCaption}>{caption}</div>
          </div>
        </div>
        <div className={styles.themeControls}>
          <span className={styles.themeMode}>{theme === "dark" ? "Dark theme" : "Light theme"}</span>
          <button className={styles.utilityButton}>Settings</button>
        </div>
      </header>

      <div className={styles.themeShell}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarLabel}>Workspace</div>
          <nav className={styles.sidebarNav}>
            {sections.map((item, index) => (
              <button key={item} className={index === 0 ? styles.navButtonActive : styles.navButton}>
                <span className={styles.navIndex}>0{index + 1}</span>
                <span>{item}</span>
              </button>
            ))}
          </nav>

          <div className={styles.sidebarPanel}>
            <div className={styles.panelEyebrow}>Quick rhythm</div>
            <p>
              One clear action per section, smaller cards, and color-coded meaning so the screen stays easy to read.
            </p>
          </div>
        </aside>

        <div className={styles.mainColumn}>
          <section className={styles.heroCard}>
            <div className={styles.heroTextBlock}>
              <div className={styles.eyebrow}>Main section concept</div>
              <h1 className={styles.heroTitle}>A calm command center for documents, analysis, graph work, and review.</h1>
              <p className={styles.heroText}>
                The layout is split into short sections with stable anchors, so the user does not have to scroll through a long landing page to reach the next action.
              </p>
            </div>
            <div className={styles.heroActions}>
              <button className={styles.primaryButton}>Start new analysis</button>
              <button className={styles.secondaryButton}>Open review queue</button>
            </div>
          </section>

          <section className={styles.metricRow}>
            {metrics.map((item) => (
              <article key={item.label} className={styles.metricCard}>
                <span className={styles.metricLabel}>{item.label}</span>
                <strong>{item.value}</strong>
                <span className={styles.metricDetail}>{item.detail}</span>
              </article>
            ))}
          </section>

          <section className={styles.contentGrid}>
            <article className={`${styles.panelCard} ${styles.panelWide}`}>
              <div className={styles.cardHead}>
                <div>
                  <div className={styles.cardEyebrow}>Documents</div>
                  <h2 className={styles.cardTitle}>Recent uploads are easy to scan and grouped by state.</h2>
                </div>
                <button className={styles.inlineButton}>Upload pack</button>
              </div>

              <div className={styles.documentList}>
                {documents.map((item) => (
                  <div key={item.title} className={styles.documentItem}>
                    <div>
                      <div className={styles.documentTitle}>{item.title}</div>
                      <div className={styles.documentMeta}>{item.meta}</div>
                    </div>
                    <span className={styles.documentState}>{item.state}</span>
                  </div>
                ))}
              </div>
            </article>

            <article className={styles.panelCard}>
              <div className={styles.cardEyebrow}>Actions</div>
              <div className={styles.quickActions}>
                <button className={styles.quickButton}><span>Create extraction run</span><span>{"->"}</span></button>
                <button className={styles.quickButton}><span>Review low-confidence nodes</span><span>{"->"}</span></button>
                <button className={styles.quickButton}><span>Export JSONL package</span><span>{"->"}</span></button>
              </div>
            </article>

            <article className={`${styles.panelCard} ${styles.panelWide}`}>
              <div className={styles.cardHead}>
                <div>
                  <div className={styles.cardEyebrow}>Graph</div>
                  <h2 className={styles.cardTitle}>Bloom balance and graph intensity stay visible without taking over the page.</h2>
                </div>
                <button className={styles.inlineButton}>Open graph</button>
              </div>

              <div className={styles.graphSplit}>
                <div className={styles.graphBars}>
                  {graphLevels.map((item) => (
                    <div key={item.label} className={styles.graphRow}>
                      <span>{item.label}</span>
                      <div className={styles.graphTrack}>
                        <div className={styles.graphFill} style={{ width: item.width, background: item.tone }} />
                      </div>
                    </div>
                  ))}
                </div>

                <div className={styles.insightCard}>
                  <div className={styles.insightLabel}>Orientation</div>
                  <p>
                    Blue points to data-heavy views, terracotta highlights items that need attention, and green anchors the main product actions.
                  </p>
                  <div className={styles.insightStat}>Pastel active states keep navigation visible without shouting.</div>
                </div>
              </div>
            </article>

            <article className={styles.panelCard}>
              <div className={styles.cardEyebrow}>Team</div>
              <div className={styles.noticeWarm}>
                <div className={styles.noticeTitle}>58 items need review</div>
                <p>Use terracotta as the shared attention color for queue items, moderation, and manual verification.</p>
              </div>
              <div className={styles.noticeCool}>
                <div className={styles.noticeTitle}>Theme switch ready</div>
                <p>The structure stays identical in both themes, so the user keeps the same spatial memory.</p>
              </div>
            </article>
          </section>
        </div>
      </div>
    </section>
  );
}

export default function DesignLabMainSection() {
  return (
    <>
      <Head>
        <title>Bloom Knowledge Studio - Dual Theme Concept</title>
      </Head>
      <Script src="https://mcp.figma.com/mcp/html-to-design/capture.js" strategy="afterInteractive" />
      <main className={styles.page}>
        <div className={styles.backdropGlow} />
        <section className={styles.intro}>
          <div className={styles.introEyebrow}>Draft direction</div>
          <h1 className={styles.introTitle}>Dual-theme concept with stronger color roles and a friendlier, lower-scroll layout.</h1>
          <p className={styles.introText}>
            This draft focuses on practical orientation: one stable navigation model, short sections, pastel active states, and meaningful accent colors instead of decorative gradients.
          </p>
        </section>

        <section className={styles.previewGrid}>
          <ThemePreview
            theme="light"
            title="Bloom Knowledge Studio"
            caption="Warm editorial product feel for everyday work"
            metrics={lightMetrics}
          />
          <ThemePreview
            theme="dark"
            title="Bloom Knowledge Studio"
            caption="Graphite dark theme with soft contrast and the same layout memory"
            metrics={darkMetrics}
          />
        </section>
      </main>
    </>
  );
}
