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
  const route = page.getByRole("region", {
    name: "Как долго хранятся данные помощника",
  });
  await expect(route).toBeVisible();
  return route;
}

type MutablePolicyPayload = {
  status?: string;
  user_state?: { label?: string; recovery_action?: string };
  response?: {
    mode?: string;
    organization_name?: string;
    overall_state?: string;
    headline?: string;
    retention?: Record<string, unknown>;
    policy_versions?: unknown[];
    purge_status?: Record<string, unknown>;
  } | null;
};

function applyCurrentReceipt(payload: MutablePolicyPayload) {
  if (payload.status !== "completed" || payload.response?.mode !== "admin_policy_status") return;
  payload.response.overall_state = "ready";
  payload.response.headline = "Текущая политика и последняя квитанция сопоставлены";
  payload.response.retention = {
    state: "available",
    source: "organization",
    retention_days: 180,
    agent_metadata_retention_days: 30,
    automatic_purge: true,
    student_self_delete: true,
    label: "Учебные данные — до 180 дней",
    detail: "Действует сохранённая политика этой организации.",
  };
  payload.response.policy_versions = [
    {
      kind: "tutor_data",
      label: "Данные учебного помощника",
      version: "организация · v3",
      detail: "Сохранённая версия действует для этой организации.",
    },
    {
      kind: "agent_runtime",
      label: "Правила ИИ-агента",
      version: "role-policy.v1",
      detail: "Версия серверных ролевых и инструментальных границ агента.",
    },
  ];
  payload.response.purge_status = {
    state: "current",
    label: "Автоматическая очистка",
    detail: "Квитанция создана по текущей версии политики хранения.",
    recorded_at: "2026-08-03T08:30:00Z",
    policy_version: 3,
    facts: [
      "Ответов удалено: 12",
      "Сигналов обратной связи удалено: 4",
      "Запусков агента удалено: 7",
    ],
    evidence_window: "Последняя безопасная квитанция · 2026-08-03",
  };
}

async function mockCurrentReceipt(page: import("@playwright/test").Page) {
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    applyCurrentReceipt(payload);
    await route.fulfill({ response, json: payload });
  });
}

test("default policy tells the truth about a missing receipt and reveals boundaries", async ({ page }, testInfo) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  const route = await openAdminPage(page);
  await expect(route).toContainText("политика, Canvas и данные останутся без изменений");
  const run = route.getByRole("button", { name: "Проверить хранение" });
  await run.focus();
  await page.keyboard.press("Enter");
  await expect(
    route.getByRole("heading", {
      name: "Политика известна; удалений с квитанцией пока не было",
    }),
  ).toBeFocused();
  await expect(route.getByRole("img", { name: /до 30 дней.*до 90 дней/ })).toBeVisible();
  await expect(route.getByText("Удалений не зафиксировано", { exact: true })).toBeVisible();
  await expect(route).toContainText("Это не означает, что очистка не запускалась");
  await route.screenshot({ path: testInfo.outputPath("admin-data-custody-default.png") });

  await route.getByRole("button", { name: "Показать границы очистки" }).click();
  const detail = route.locator("#admin-data-custody-detail");
  await expect(detail).toBeFocused();
  await expect(detail).toContainText("Не доказывает и не показывает");
  await expect(detail).toContainText("если удалять было нечего");

  const overflow = await page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth;
    return Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .map((element) => Math.ceil(element.getBoundingClientRect().right))
      .filter((right) => right > viewportWidth + 1);
  });
  expect(overflow).toEqual([]);
  expect(browserErrors).toEqual([]);
});

test("current receipt renders a scaled ruler and content-free ledger", async ({ page }, testInfo) => {
  await mockCurrentReceipt(page);
  const route = await openAdminPage(page);
  await route.getByRole("button", { name: "Проверить хранение" }).click();
  await expect(
    route.getByRole("heading", {
      name: "Текущая политика и последняя квитанция сопоставлены",
    }),
  ).toBeFocused();
  await expect(route.getByRole("img", { name: /до 30 дней.*до 180 дней/ })).toBeVisible();
  await expect(route.getByText("организация · v3", { exact: true })).toBeVisible();
  await expect(route.getByText("Текущая версия", { exact: true })).toBeVisible();
  await expect(route.getByText("Ответов удалено: 12", { exact: true })).toBeVisible();
  await expect(route).not.toContainText("admin@local.test");
  await expect(route).not.toContainText("course_id");
  await expect(route).not.toContainText("subject_user_id");
  await route.screenshot({ path: testInfo.outputPath("admin-data-custody-current.png") });
});

test("partial result preserves the policy when the receipt source is unavailable", async ({ page }) => {
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (payload.status === "completed" && payload.response?.mode === "admin_policy_status") {
      payload.response.overall_state = "partial";
      payload.response.headline = "Часть границ хранения временно недоступна";
      payload.response.purge_status = {
        state: "unavailable",
        label: "Журнал очистки временно недоступен",
        detail: "Политика прочитана отдельно, но квитанцию получить не удалось.",
        recorded_at: null,
        policy_version: null,
        facts: ["Статус квитанции не получен"],
        evidence_window: "Текущая проверка источника завершилась частично",
      };
    }
    await route.fulfill({ response, json: payload });
  });
  const route = await openAdminPage(page);
  await route.getByRole("button", { name: "Проверить хранение" }).click();
  await expect(
    route.getByRole("heading", { name: "Часть границ хранения временно недоступна" }),
  ).toBeFocused();
  await expect(route.getByText("Источник недоступен", { exact: true })).toBeVisible();
  await expect(route.getByText("90 дней", { exact: true })).toBeVisible();
});

test("temporary failure is focused and retry keeps the workflow read-only", async ({ page }) => {
  await mockCurrentReceipt(page);
  await page.route("**/agent/v1/admin-organization?**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "Проверка хранения временно недоступна." } }),
    });
  }, { times: 1 });
  const route = await openAdminPage(page);
  await route.getByRole("button", { name: "Проверить хранение" }).click();
  const alert = route.getByRole("alert");
  await expect(alert).toBeFocused();
  await expect(alert).toContainText("Политика и данные не изменены");
  await expect(route.getByRole("button")).toHaveCount(1);
  await alert.getByRole("button", { name: "Повторить проверку" }).click();
  await expect(
    route.getByRole("heading", {
      name: "Текущая политика и последняя квитанция сопоставлены",
    }),
  ).toBeFocused();
});

test("stale result requires a fresh policy check", async ({ page }) => {
  let returnStale = true;
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload: MutablePolicyPayload = await response.json();
    if (
      returnStale &&
      payload.status === "completed" &&
      payload.response?.mode === "admin_policy_status"
    ) {
      returnStale = false;
      payload.status = "abstained";
      payload.response = null;
      payload.user_state = {
        label: "Политика или журнал очистки изменились — проверьте заново",
        recovery_action: "choose_supported_task",
      };
    } else {
      applyCurrentReceipt(payload);
    }
    await route.fulfill({ response, json: payload });
  });
  const route = await openAdminPage(page);
  await route.getByRole("button", { name: "Проверить хранение" }).click();
  const alert = route.getByRole("alert");
  await expect(alert).toBeFocused();
  await expect(alert).toContainText("Проверка устарела");
  await expect(route.getByRole("button")).toHaveCount(1);
  await alert.getByRole("button", { name: "Повторить проверку" }).click();
  await expect(
    route.getByRole("heading", {
      name: "Текущая политика и последняя квитанция сопоставлены",
    }),
  ).toBeFocused();
});
