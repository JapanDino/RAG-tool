import { expect, test } from "@playwright/test";

const API_BASE = `http://localhost:${process.env.CANVAS_SIMULATOR_E2E_BACKEND_PORT || "8000"}`;

test.beforeEach(async ({ request }) => {
  const response = await request.post(
    `${API_BASE}/identity/development/bootstrap`,
    { data: {} },
  );
  expect(response.ok()).toBeTruthy();
});

test("administrator gets one operations route and opens its first control", async ({ page }, testInfo) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await page.addInitScript(() => {
    window.localStorage.setItem("rag-dev-user", "admin@local.test");
  });
  await page.goto("/workspace/integrations/lti");

  const assistant = page.getByRole("region", {
    name: "Что проверить перед следующим запуском",
  });
  await expect(assistant).toBeVisible();
  await expect(assistant.getByText(/не обращается к школьному Canvas/)).toBeVisible();
  const runButton = assistant.getByRole("button", { name: "Собрать маршрут действий" });
  await runButton.focus();
  await page.keyboard.press("Enter");
  await expect(assistant.getByRole("status")).toContainText("четыре агрегированных сигнала");

  const heading = assistant.getByRole("heading", {
    name: /Сначала устраните блокер|Сначала разберите|Сначала подтвердите|Основные границы готовы|Часть сигналов недоступна/,
  });
  await expect(heading).toBeFocused();
  const stationRoute = assistant.getByRole("list", {
    name: "Станции операционного маршрута",
  });
  await expect(stationRoute.locator(":scope > li")).toHaveCount(4);
  await expect(assistant.getByText("Пакет LTI", { exact: true })).toBeVisible();
  await expect(assistant.getByText("Запуски Canvas", { exact: true })).toBeVisible();
  await expect(assistant.getByText("Школьный AI", { exact: true })).toBeVisible();
  await expect(assistant.getByText("Хранение данных", { exact: true })).toBeVisible();
  await expect(assistant).not.toContainText("client_id");
  await expect(assistant).not.toContainText("deployment_id");
  await expect(assistant).not.toContainText("admin@local.test");
  await assistant.screenshot({ path: testInfo.outputPath("admin-operations-route.png") });

  const primaryAction = assistant.getByRole("button", { name: /^Открыть / });
  const rebuildAction = assistant.getByRole("button", {
    name: "Собрать маршрут действий заново",
  });
  const [primaryBackground, rebuildBackground] = await Promise.all([
    primaryAction.evaluate((element) => getComputedStyle(element).backgroundColor),
    rebuildAction.evaluate((element) => getComputedStyle(element).backgroundColor),
  ]);
  expect(rebuildBackground).not.toBe(primaryBackground);
  await primaryAction.click();
  await expect(page.locator("#registration-package")).toBeFocused();

  const overflow = await page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth;
    return Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .map((element) => ({
        right: Math.ceil(element.getBoundingClientRect().right),
        tag: element.tagName,
      }))
      .filter((element) => element.right > viewportWidth + 1);
  });
  expect(overflow).toEqual([]);
  expect(browserErrors).toEqual([]);
});

test("operations route failure is focused, safe, and retryable", async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("rag-dev-user", "admin@local.test");
  });
  await page.route("**/agent/v1/admin-organization?**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        contract_version: "agent.v1",
        error: { message: "Маршрут временно недоступен." },
      }),
    });
  }, { times: 1 });
  await page.goto("/workspace/integrations/lti");
  const assistant = page.getByRole("region", {
    name: "Что проверить перед следующим запуском",
  });
  await assistant.getByRole("button", { name: "Собрать маршрут действий" }).click();
  const alert = assistant.getByRole("alert");
  await expect(alert).toBeFocused();
  await expect(alert).toContainText("Canvas и настройки организации не изменены");
  await alert.screenshot({ path: testInfo.outputPath("admin-operations-route-error.png") });
  await alert.getByRole("button", { name: "Попробовать снова" }).click();
  await expect(
    assistant.getByRole("heading", {
      name: /Сначала устраните блокер|Сначала разберите|Сначала подтвердите|Основные границы готовы|Часть сигналов недоступна/,
    }),
  ).toBeFocused();
});

test("changed operations signal requires a fresh route", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("rag-dev-user", "admin@local.test");
  });
  let returnStale = true;
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (returnStale && payload.status === "completed") {
      returnStale = false;
      payload.status = "abstained";
      payload.response = null;
      payload.user_state = {
        label: "Операционное состояние изменилось — соберите маршрут заново",
        recovery_action: "choose_supported_task",
      };
    }
    await route.fulfill({ response, json: payload });
  });
  await page.goto("/workspace/integrations/lti");
  const assistant = page.getByRole("region", {
    name: "Что проверить перед следующим запуском",
  });
  await assistant.getByRole("button", { name: "Собрать маршрут действий" }).click();
  const alert = assistant.getByRole("alert");
  await expect(alert).toBeFocused();
  await expect(alert).toContainText("Операционное состояние изменилось");
  await alert.getByRole("button", { name: "Обновить маршрут" }).click();
  await expect(
    assistant.getByRole("heading", {
      name: /Сначала устраните блокер|Сначала разберите|Сначала подтвердите|Основные границы готовы|Часть сигналов недоступна/,
    }),
  ).toBeFocused();
});

test("partial route keeps available stations and honestly reveals retention details", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("rag-dev-user", "admin@local.test");
  });
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (payload.status === "completed" && payload.response?.mode === "admin_operations_brief") {
      payload.response.overall_state = "partial";
      payload.response.headline = "Часть сигналов недоступна — начните с доступного маршрута";
      payload.response.stations = payload.response.stations.map(
        (station: { kind: string }) => station.kind === "model_runtime"
          ? {
              ...station,
              state: "unavailable",
              label: "Состояние AI недоступно",
              detail: "Один источник не ответил. Остальные станции маршрута сохранены.",
              facts: ["Данные этой станции не получены"],
              evidence_window: "Агрегат за 30 минут не получен",
            }
          : station,
      );
      payload.response.priorities = [
        {
          kind: "data_retention",
          attention: "review",
          title: "Политику хранения нужно проверить",
          detail: "Проверьте действующий срок и обязательные защиты.",
          evidence_label: "Текущая политика организации",
          action_target: "retention",
          action_label: "Показать сведения политики",
        },
      ];
    }
    await route.fulfill({ response, json: payload });
  });
  await page.goto("/workspace/integrations/lti");
  const assistant = page.getByRole("region", {
    name: "Что проверить перед следующим запуском",
  });
  await assistant.getByRole("button", { name: "Собрать маршрут действий" }).click();
  await expect(
    assistant.getByRole("heading", { name: /Часть сигналов недоступна/ }),
  ).toBeFocused();
  await expect(assistant.getByText("Нет данных", { exact: true })).toBeVisible();
  await expect(assistant.getByText("Пакет LTI", { exact: true })).toBeVisible();
  await assistant.getByRole("button", { name: "Показать сведения политики" }).click();
  const detail = assistant.getByRole("region", { name: "Сведения политики хранения" });
  await expect(detail).toBeFocused();
  await expect(detail).toContainText("маршрут их не запускает");
});
