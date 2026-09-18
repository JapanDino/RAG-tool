import { expect, test } from "@playwright/test";

const API_BASE = `http://localhost:${process.env.CANVAS_SIMULATOR_E2E_BACKEND_PORT || "8000"}`;

const baseReadiness = {
  schema_version: 1,
  available: true,
  recovery_action: null,
  window_minutes: 30,
  counts: { total: 5, succeeded: 5, fallback: 0, failed: 0, p95_latency_ms: 840 },
  last_invocation_at: "2026-08-02T08:30:00Z",
};

test.beforeAll(async ({ request }) => {
  const response = await request.post(
    `${API_BASE}/identity/development/bootstrap`,
    { data: {} },
  );
  expect(response.ok()).toBeTruthy();
});

test("administrator sees a bounded school-model route", async ({ page }, testInfo) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.goto("/workspace");
  await page.evaluate(() => window.localStorage.setItem("rag-dev-user", "admin@local.test"));
  await page.goto("/workspace/integrations/lti");

  const panel = page.getByRole("region", { name: "Готовность AI-функций в Canvas" });
  await expect(panel).toBeVisible();
  await expect(panel.getByText("Курс Canvas", { exact: true })).toBeVisible();
  await expect(panel.getByText("AI-помощник", { exact: true })).toBeVisible();
  await expect(panel.getByText("Школьный AI-сервис", { exact: true })).toBeVisible();
  await expect(panel.getByText("AI-функции отключены", { exact: true })).toBeVisible();
  await expect(panel.getByText(/не содержит текстов диалогов/)).toBeVisible();
  await expect(panel.getByText("Не выполнено", { exact: true })).toBeVisible();

  await panel.scrollIntoViewIfNeeded();
  await panel.screenshot({ path: testInfo.outputPath("agent-model-readiness.png") });

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBe(0);
  expect(browserErrors).toEqual([]);
});

test("readiness variants keep one plain-language recovery action", async ({ page }, testInfo) => {
  await page.addInitScript(() => window.localStorage.setItem("rag-dev-user", "admin@local.test"));
  let responseBody: Record<string, unknown> = {
    ...baseReadiness,
    state: "configured",
    label: "AI-сервис настроен, но не проверен",
    detail: "Безопасная конфигурация сохранена, но рабочие вызовы ещё не выполнялись.",
    recovery_action: "check_model_host",
  };
  await page.route("**/organizations/*/agent-model/readiness", async (route) => {
    await route.fulfill({ json: responseBody });
  });

  const variants = [
    {
      state: "configured",
      label: "AI-сервис настроен, но не проверен",
      detail: "Безопасная конфигурация сохранена, но рабочие вызовы ещё не выполнялись.",
      recovery_action: "check_model_host",
      action: "Проверьте доступность школьного AI-сервиса.",
    },
    {
      state: "ready",
      label: "AI-функции работают",
      detail: "Последние проверенные вызовы завершаются штатно.",
      recovery_action: null,
      action: "AI-помощник доступен в разрешённых сценариях Canvas.",
    },
    {
      state: "degraded",
      label: "AI-функции работают нестабильно",
      detail: "Часть последних вызовов завершилась безопасным резервным сценарием.",
      recovery_action: "wait_and_retry",
      action: "Повторите проверку после восстановления школьного AI-сервиса.",
    },
    {
      state: "misconfigured",
      label: "Настройка AI требует проверки",
      detail: "Сервер отклонил небезопасную или некорректную настройку AI-функций.",
      recovery_action: "configure_model_host",
      action: "Передайте настройки школьного AI-сервиса системному администратору.",
    },
  ];

  for (const variant of variants) {
    const { action, ...apiVariant } = variant;
    responseBody = { ...baseReadiness, ...apiVariant };
    await page.goto("/workspace/integrations/lti");
    const panel = page.getByRole("region", { name: "Готовность AI-функций в Canvas" });
    await expect(panel.getByText(variant.label, { exact: true })).toBeVisible();
    await expect(panel.getByText(action, { exact: true })).toBeVisible();
    await panel.screenshot({ path: testInfo.outputPath(`agent-readiness-${variant.state}.png`) });
  }
});

test("readiness failure preserves Canvas and offers a keyboard retry", async ({ page }, testInfo) => {
  await page.addInitScript(() => window.localStorage.setItem("rag-dev-user", "admin@local.test"));
  await page.route("**/organizations/*/agent-model/readiness", async (route) => {
    await route.fulfill({ status: 503, json: { detail: "provider detail must stay hidden" } });
  });
  await page.goto("/workspace/integrations/lti");

  await expect(page.getByRole("heading", { name: "Проверка временно недоступна" })).toBeVisible();
  await expect(page.getByText(/Подключение Canvas и работа курсов не затронуты/)).toBeVisible();
  const retry = page.getByRole("button", { name: "Проверить снова" });
  await retry.focus();
  await expect(retry).toBeFocused();
  await expect(page.getByText(/provider detail/)).toHaveCount(0);
  await page.getByRole("region", { name: "Проверка временно недоступна" }).screenshot({
    path: testInfo.outputPath("agent-readiness-error.png"),
  });
});

test("failed refresh labels retained readiness as previous data", async ({ page }, testInfo) => {
  await page.addInitScript(() => window.localStorage.setItem("rag-dev-user", "admin@local.test"));
  let refreshFails = false;
  await page.route("**/organizations/*/agent-model/readiness", async (route) => {
    if (refreshFails) {
      await route.fulfill({ status: 503, json: { detail: "hidden provider failure" } });
      return;
    }
    await route.fulfill({
      json: {
        ...baseReadiness,
        state: "ready",
        label: "AI-функции работают",
        detail: "Последние проверенные вызовы завершаются штатно.",
      },
    });
  });
  await page.goto("/workspace/integrations/lti");
  await expect(page.getByText("AI-функции работают", { exact: true })).toBeVisible();

  refreshFails = true;
  await page.getByRole("button", { name: "Проверить готовность" }).click();
  await expect(page.getByText("Показаны предыдущие данные", { exact: true })).toBeVisible();
  await expect(page.getByText(/Подключение Canvas и работа курсов не затронуты/)).toBeVisible();
  await expect(page.getByText(/Последнее успешное обновление:/)).toBeVisible();
  await expect(page.getByText(/hidden provider failure/)).toHaveCount(0);
  await page.getByRole("region", { name: "Готовность AI-функций в Canvas" }).screenshot({
    path: testInfo.outputPath("agent-readiness-stale.png"),
  });
});
