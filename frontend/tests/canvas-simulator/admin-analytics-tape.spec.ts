import { expect, test } from "@playwright/test";

const API_BASE = `http://localhost:${process.env.CANVAS_SIMULATOR_E2E_BACKEND_PORT || "8000"}`;

test.beforeEach(async ({ request }) => {
  const response = await request.post(
    `${API_BASE}/identity/development/bootstrap`,
    { data: {} },
  );
  expect(response.ok()).toBeTruthy();
});

async function openAdminPage(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("rag-dev-user", "admin@local.test");
  });
  await page.goto("/workspace/integrations/lti");
  const tape = page.getByRole("region", {
    name: "Используют ли сервис — и выдерживает ли AI нагрузку",
  });
  await expect(tape).toBeVisible();
  return tape;
}

type MutableAnalyticsPayload = {
  status?: string;
  response?: {
    mode?: string;
    overall_state?: string;
    headline?: string;
    segments?: unknown[];
  };
};

function applyNoActivityTape(payload: MutableAnalyticsPayload) {
  if (payload.status !== "completed" || payload.response?.mode !== "admin_analytics_brief") return;
  payload.response.overall_state = "no_activity";
  payload.response.headline = "Активность ещё не сформировала операционный след";
  payload.response.segments = [
    {
      kind: "adoption",
      state: "no_activity",
      label: "Использование пока не зафиксировано",
      detail: "За текущее окно нет завершённых запусков помощника вне административных сводок.",
      current_window: "Последние 28 дней",
      comparison_window: "Предыдущие 28 дней",
      trend: "not_comparable",
      current_facts: ["Завершённых запусков: 0", "Административные сводки не учитываются"],
      previous_facts: ["Сравнение не строится без текущей активности"],
      action_target: "integration",
      action_label: "Открыть проверку подключения",
    },
    {
      kind: "runtime",
      state: "no_activity",
      label: "Вызовов школьного AI пока нет",
      detail: "За последние сутки модельный шлюз не записал ни одного вызова для организации.",
      current_window: "Последние 24 часа",
      comparison_window: "Предыдущие 24 часа",
      trend: "not_comparable",
      current_facts: ["Вызовов: 0", "Токены и задержка не измерялись"],
      previous_facts: ["Сравнение не строится без текущих вызовов"],
      action_target: null,
      action_label: null,
    },
    {
      kind: "cost",
      state: "no_activity",
      label: "Оценка стоимости пока не нужна",
      detail: "В текущем окне нет модельных вызовов, поэтому оценивать нечего.",
      current_window: "Последние 24 часа",
      comparison_window: "Предыдущие 24 часа",
      trend: "not_comparable",
      current_facts: ["Оценка не рассчитана: вызовов нет"],
      previous_facts: [],
      action_target: null,
      action_label: null,
    },
  ];
}

async function mockNoActivityTape(page: import("@playwright/test").Page) {
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    applyNoActivityTape(payload);
    await route.fulfill({ response, json: payload });
  });
}

test("no-activity tape stays useful and opens the existing integration control", async ({ page }, testInfo) => {
  await mockNoActivityTape(page);
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  const tape = await openAdminPage(page);
  await expect(tape).toContainText("ничего не меняет в Canvas или на AI-хосте");
  const run = tape.getByRole("button", { name: "Собрать контрольную ленту" });
  await run.focus();
  await page.keyboard.press("Enter");
  await expect(tape.getByRole("status")).toContainText("28 дней");
  await expect(
    tape.getByRole("heading", { name: "Активность ещё не сформировала операционный след" }),
  ).toBeFocused();
  const segments = tape.getByRole("list", {
    name: "Контрольная лента использования и нагрузки",
  }).locator(":scope > li");
  await expect(segments).toHaveCount(3);
  await expect(tape.getByText("Использование", { exact: true })).toBeVisible();
  await expect(tape.getByText("Работа AI", { exact: true })).toBeVisible();
  await expect(tape.getByText("Оценка стоимости", { exact: true })).toBeVisible();
  await tape.screenshot({ path: testInfo.outputPath("admin-analytics-tape.png") });
  await tape.getByRole("button", { name: "Открыть проверку подключения" }).click();
  await expect(page.locator("#registration-package")).toBeFocused();

  const overflow = await page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth;
    return Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .map((element) => Math.ceil(element.getBoundingClientRect().right))
      .filter((right) => right > viewportWidth + 1);
  });
  expect(overflow).toEqual([]);
  expect(browserErrors).toEqual([]);
});

test("runtime attention gets the only operational handoff", async ({ page }, testInfo) => {
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (payload.status === "completed" && payload.response?.mode === "admin_analytics_brief") {
      payload.response.overall_state = "attention";
      payload.response.headline = "Сначала проверьте работу школьного AI";
      payload.response.segments = [
        {
          kind: "adoption",
          state: "available",
          label: "Агрегат использования доступен",
          detail: "Показаны только общие завершённые запуски организации.",
          current_window: "Последние 28 дней",
          comparison_window: "Предыдущие 28 дней",
          trend: "up",
          current_facts: ["Активных пользователей: 18", "Всего запусков: 126", "Завершено: 113"],
          previous_facts: ["Ранее активных пользователей: 15", "Ранее запусков: 98"],
          action_target: null,
          action_label: null,
        },
        {
          kind: "runtime",
          state: "attention",
          label: "Runtime требует операционной проверки",
          detail: "Доля резервов/ошибок или p95 задержка достигла заданного порога проверки.",
          current_window: "Последние 24 часа",
          comparison_window: "Предыдущие 24 часа",
          trend: "up",
          current_facts: ["Вызовов: 52; успешно: 39", "Резервов: 11; ошибок: 2", "p95 задержка: 8430 мс"],
          previous_facts: ["Ранее вызовов: 31", "Ранее резервов и ошибок: 2"],
          action_target: "model",
          action_label: "Открыть состояние AI",
        },
        {
          kind: "cost",
          state: "available",
          label: "Ориентировочная стоимость рассчитана",
          detail: "Техническая оценка по единым серверным ставкам и токенам.",
          current_window: "Последние 24 часа",
          comparison_window: "Предыдущие 24 часа",
          trend: "up",
          current_facts: ["Оценка: 0,4182 USD", "Токены вход/выход: 104200/52450"],
          previous_facts: ["Предыдущая оценка: 0,2261 USD"],
          action_target: null,
          action_label: null,
        },
      ];
    }
    await route.fulfill({ response, json: payload });
  });
  const tape = await openAdminPage(page);
  await tape.getByRole("button", { name: "Собрать контрольную ленту" }).click();
  await expect(
    tape.getByRole("heading", { name: "Сначала проверьте работу школьного AI" }),
  ).toBeFocused();
  await expect(tape.getByRole("button", { name: "Открыть состояние AI" })).toHaveCount(1);
  await tape.screenshot({ path: testInfo.outputPath("admin-analytics-tape-attention.png") });
  await tape.getByRole("button", { name: "Открыть состояние AI" }).click();
  await expect(page.locator("#agent-model-route")).toBeFocused();
});

test("privacy suppression and unconfigured cost reveal no low counts or fake price", async ({ page }) => {
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (payload.status === "completed" && payload.response?.mode === "admin_analytics_brief") {
      const adoption = payload.response.segments.find((item: { kind: string }) => item.kind === "adoption");
      Object.assign(adoption, {
        state: "suppressed",
        label: "Агрегат скрыт порогом приватности",
        detail: "Текущее окно не достигло минимального размера группы.",
        trend: "not_comparable",
        current_facts: ["Числа текущего окна скрыты полностью", "Порог: не менее 5 разных пользователей"],
        previous_facts: ["Предыдущее окно не раскрывается без сравнимой текущей группы"],
        action_target: null,
        action_label: null,
      });
      const cost = payload.response.segments.find((item: { kind: string }) => item.kind === "cost");
      Object.assign(cost, {
        state: "unconfigured",
        label: "Оценочные ставки не настроены",
        detail: "Токены измерены, но стоимость без серверных ставок не рассчитывается.",
        trend: "not_comparable",
        current_facts: ["Токенов всего: 2400", "Стоимость не рассчитана"],
        previous_facts: ["Сравнение стоимости недоступно без ставок"],
        action_target: null,
        action_label: null,
      });
    }
    await route.fulfill({ response, json: payload });
  });
  const tape = await openAdminPage(page);
  await tape.getByRole("button", { name: "Собрать контрольную ленту" }).click();
  await expect(tape.getByText("Скрыто для приватности", { exact: true })).toBeVisible();
  await expect(tape.getByText("Не настроено", { exact: true })).toBeVisible();
  await expect(tape).not.toContainText("4 пользователя");
  await expect(tape).not.toContainText("admin@local.test");
  await expect(tape).not.toContainText("USD");
  await expect(tape.getByText("Стоимость не рассчитана", { exact: true })).toBeVisible();
});

test("partial tape preserves available runtime facts", async ({ page }) => {
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (payload.status === "completed" && payload.response?.mode === "admin_analytics_brief") {
      payload.response.overall_state = "partial";
      payload.response.headline = "Часть контрольной ленты недоступна — доступные факты сохранены";
      payload.response.segments[0] = {
        kind: "adoption",
        state: "unavailable",
        label: "Агрегат использования недоступен",
        detail: "Один источник не ответил. Остальные участки контрольной ленты сохранены.",
        current_window: "Последние 28 дней",
        comparison_window: "Предыдущие 28 дней",
        trend: "not_comparable",
        current_facts: ["Данные этого участка не получены"],
        previous_facts: [],
        action_target: null,
        action_label: null,
      };
    }
    await route.fulfill({ response, json: payload });
  });
  const tape = await openAdminPage(page);
  await tape.getByRole("button", { name: "Собрать контрольную ленту" }).click();
  await expect(
    tape.getByRole("heading", { name: "Часть контрольной ленты недоступна — доступные факты сохранены" }),
  ).toBeFocused();
  await expect(tape.getByText("Источник недоступен", { exact: true })).toBeVisible();
  await expect(tape.getByText("Работа AI", { exact: true })).toBeVisible();
});

test("tape failure is focused and retryable", async ({ page }) => {
  await mockNoActivityTape(page);
  await page.route("**/agent/v1/admin-organization?**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "Контрольная лента временно недоступна." } }),
    });
  }, { times: 1 });
  const tape = await openAdminPage(page);
  await tape.getByRole("button", { name: "Собрать контрольную ленту" }).click();
  const alert = tape.getByRole("alert");
  await expect(alert).toBeFocused();
  await expect(alert).toContainText("Canvas, AI-хост и настройки организации не изменены");
  await alert.getByRole("button", { name: "Попробовать снова" }).click();
  await expect(
    tape.getByRole("heading", { name: "Активность ещё не сформировала операционный след" }),
  ).toBeFocused();
});

test("changed analytics require a fresh tape", async ({ page }) => {
  let returnStale = true;
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (returnStale && payload.status === "completed" && payload.response?.mode === "admin_analytics_brief") {
      returnStale = false;
      payload.status = "abstained";
      payload.response = null;
      payload.user_state = {
        label: "Данные контрольной ленты изменились — соберите её заново",
        recovery_action: "choose_supported_task",
      };
    } else {
      applyNoActivityTape(payload);
    }
    await route.fulfill({ response, json: payload });
  });
  const tape = await openAdminPage(page);
  await tape.getByRole("button", { name: "Собрать контрольную ленту" }).click();
  const alert = tape.getByRole("alert");
  await expect(alert).toBeFocused();
  await expect(alert).toContainText("Лента устарела");
  await alert.getByRole("button", { name: "Собрать свежую ленту" }).click();
  await expect(
    tape.getByRole("heading", { name: "Активность ещё не сформировала операционный след" }),
  ).toBeFocused();
});
