import { expect, test } from "@playwright/test";

const API_BASE = `http://localhost:${process.env.CANVAS_SIMULATOR_E2E_BACKEND_PORT || "8000"}`;

test.beforeEach(async ({ request }, testInfo) => {
  const bootstrap = await request.post(
    `${API_BASE}/identity/development/bootstrap`,
    { data: {} },
  );
  expect(bootstrap.ok()).toBeTruthy();
  const organizationId = (await bootstrap.json()).organization.id;
  const demo = await request.post(
    `${API_BASE}/organizations/${organizationId}/programs/demo`,
    { headers: { "X-Dev-User": "designer@local.test" }, data: {} },
  );
  expect(demo.ok()).toBeTruthy();
  const second = await request.post(
    `${API_BASE}/organizations/${organizationId}/programs`,
    {
      headers: { "X-Dev-User": "designer@local.test" },
      data: {
        code: `EVIDENCE-${testInfo.project.name.toUpperCase()}`,
        title: `Пустая ветка ${testInfo.project.name}`,
        description: "Пустая карта для безопасного состояния развилки.",
      },
    },
  );
  if (![201, 409].includes(second.status())) {
    throw new Error(`evidence program bootstrap failed: ${second.status()}`);
  }
});

async function openProgramFork(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("rag-dev-user", "methodologist@local.test");
  });
  await page.goto("/workspace/programs");
  const select = page.getByRole("combobox", { name: "Программа" });
  await expect(select).toBeVisible();
  const demoValue = await select.locator("option").evaluateAll((options) =>
    options
      .map((option) => ({
        label: option.textContent ?? "",
        value: (option as HTMLOptionElement).value,
      }))
      .find((option) => option.label.includes("CS-FOUND"))?.value ?? "",
  );
  expect(demoValue).not.toBe("");
  await select.selectOption(demoValue);
  const fork = page.getByRole("region", { name: "Какой вопрос проверить сейчас" });
  await expect(fork).toBeVisible();
  return { fork, select, demoValue };
}

async function ensureExplicitPrerequisite(request: import("@playwright/test").APIRequestContext) {
  const bootstrap = await request.post(
    `${API_BASE}/identity/development/bootstrap`,
    { data: {} },
  );
  const organizationId = (await bootstrap.json()).organization.id;
  const programs = await request.get(
    `${API_BASE}/organizations/${organizationId}/programs`,
    { headers: { "X-Dev-User": "designer@local.test" } },
  );
  const program = (await programs.json()).find((item: { code: string }) => item.code === "CS-FOUND");
  const mapResponse = await request.get(
    `${API_BASE}/programs/${program.id}/map`,
    { headers: { "X-Dev-User": "designer@local.test" } },
  );
  const map = await mapResponse.json();
  if (map.prerequisites.length) return;
  const created = await request.put(
    `${API_BASE}/programs/${program.id}/prerequisites`,
    {
      headers: { "X-Dev-User": "designer@local.test" },
      data: {
        expected_version: map.program.version,
        prerequisite_competency_id: map.competencies[0].id,
        target_competency_id: map.competencies[1].id,
        rationale: "Сначала проверяется анализ, затем развивается выбор структуры.",
      },
    },
  );
  expect(created.ok()).toBeTruthy();
}

test("gap branch returns one candidate and opens exact audit evidence", async ({ page }, testInfo) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  const { fork } = await openProgramFork(page);
  await expect(fork.getByRole("button", { name: /Пробелы/ })).toHaveAttribute("aria-pressed", "true");
  const run = fork.getByRole("button", { name: "Проверить выбранный вопрос" });
  await run.focus();
  await page.keyboard.press("Enter");
  await expect(fork.getByRole("status")).toContainText("Сверяем роль");
  await expect(
    fork.getByRole("heading", { name: "Начните с первого доказательного пробела" }),
  ).toBeFocused();
  await expect(fork.getByText("Автоматический сигнал · ещё не проверен", { exact: true })).toBeVisible();
  await expect(fork).not.toContainText("expected_answer");
  await fork.screenshot({ path: testInfo.outputPath("program-evidence-gap.png") });
  await fork.getByRole("button", { name: "Открыть доказательства пробела" }).click();
  const audit = page.getByLabel("Проверка доказательств программы");
  await expect(audit).toBeFocused();
  await expect(audit.getByText("Контрольная рейка", { exact: true })).toBeVisible();

  const overflow = await page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    return Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .map((element) => Math.ceil(element.getBoundingClientRect().right))
      .filter((right) => right > width + 1);
  });
  expect(overflow).toEqual([]);
  expect(browserErrors).toEqual([]);
});

test("prerequisite branch uses an explicit relation and opens its existing lines", async ({ page, request }, testInfo) => {
  await ensureExplicitPrerequisite(request);
  const { fork } = await openProgramFork(page);
  await fork.getByRole("button", { name: /Предпосылки/ }).click();
  await expect(fork.getByText(/ещё не читала карту/)).toBeVisible();
  await fork.getByRole("button", { name: "Проверить выбранный вопрос" }).click();
  await expect(
    fork.getByRole("heading", { name: "Сначала сверьте порядок объявленной связи" }),
  ).toBeFocused();
  await expect(fork.getByText("Обоснование автора карты", { exact: true })).toBeVisible();
  await expect(fork.getByRole("listitem")).toHaveCount(2);
  await fork.screenshot({ path: testInfo.outputPath("program-evidence-prerequisite.png") });
  await fork.getByRole("button", { name: "Открыть линии предпосылок" }).click();
  const prerequisites = page.getByLabel("Явные линии предпосылок программы");
  await expect(prerequisites).toBeFocused();
  await expect(prerequisites.getByRole("heading", { name: "Линии предпосылок" })).toBeVisible();
});

test("program switch clears the previous result and reports an empty map honestly", async ({ page }) => {
  const { fork, select, demoValue } = await openProgramFork(page);
  await fork.getByRole("button", { name: "Проверить выбранный вопрос" }).click();
  await expect(fork.getByRole("heading", { name: "Начните с первого доказательного пробела" })).toBeFocused();
  const emptyValue = await select.locator("option").evaluateAll(
    (options, current) =>
      options.map((option) => (option as HTMLOptionElement).value).find((value) => value !== current) ?? "",
    demoValue,
  );
  await select.selectOption(emptyValue);
  await expect(fork.getByText(/ещё не читала карту/)).toBeVisible();
  await fork.getByRole("button", { name: "Проверить выбранный вопрос" }).click();
  await expect(
    fork.getByRole("heading", { name: "Карта пока не содержит компетенций для этой проверки" }),
  ).toBeFocused();
  await expect(fork.getByText("Ветка пока пуста", { exact: true })).toBeVisible();
});

test("partial result never presents an all-clear", async ({ page }) => {
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (payload.status === "completed" && payload.response?.mode === "program_evidence_route") {
      payload.response.state = "partial";
      payload.response.headline = "Проверена только часть карты — нужен ручной просмотр";
      payload.response.candidate = null;
      payload.response.analysis_truncated = true;
    }
    await route.fulfill({ response, json: payload });
  });
  const { fork } = await openProgramFork(page);
  await fork.getByRole("button", { name: "Проверить выбранный вопрос" }).click();
  await expect(
    fork.getByRole("heading", { name: "Проверена только часть карты — нужен ручной просмотр" }),
  ).toBeFocused();
  await expect(fork.getByRole("status")).toContainText("Проверена не вся карта");
  await expect(fork).not.toContainText("Явного пробела по этим правилам сейчас не найдено");
});

test("clear state remains a review route instead of a quality verdict", async ({ page }) => {
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (payload.status === "completed" && payload.response?.mode === "program_evidence_route") {
      payload.response.state = "clear";
      payload.response.headline = "No deterministic gap signal was found";
      payload.response.candidate = null;
      payload.response.analysis_truncated = false;
    }
    await route.fulfill({ response, json: payload });
  });
  const { fork } = await openProgramFork(page);
  await fork.locator("header button").click();
  const result = fork.locator('article[data-state="clear"]');
  await expect(result).toBeVisible();
  await expect(result.locator("h3")).toBeFocused();
  await expect(result.locator("ol")).toHaveCount(0);
  await expect(result.locator("footer button")).toHaveCount(1);
});

test("keyboard route selection respects reduced-motion preference", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const { fork } = await openProgramFork(page);
  const routeButtons = fork.locator('button[aria-pressed]');
  await routeButtons.nth(1).focus();
  await page.keyboard.press("Space");
  await expect(routeButtons.nth(1)).toHaveAttribute("aria-pressed", "true");
  await fork.locator("header button").focus();
  await page.keyboard.press("Enter");
  await expect(fork.locator("article h3")).toBeFocused();
});

test("revoked access leaves the program in a non-disclosing terminal state", async ({ page }) => {
  const { fork } = await openProgramFork(page);
  await page.route("**/agent/v1/programs?**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "ACCESS_DENIED", message: "resource not found" } }),
    });
  }, { times: 1 });
  await fork.locator("header button").click();
  await expect(page.getByRole("heading", { name: "Карта программы недоступна" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Вернуться в рабочее пространство" })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("CS-FOUND");
});

test("route failure is focused and retryable", async ({ page }) => {
  await page.route("**/agent/v1/programs?**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "Выбранная проверка временно недоступна." } }),
    });
  }, { times: 1 });
  const { fork } = await openProgramFork(page);
  await fork.getByRole("button", { name: "Проверить выбранный вопрос" }).click();
  const alert = fork.getByRole("alert");
  await expect(alert).toBeFocused();
  await expect(alert).toContainText("Карта и данные не изменены");
  await alert.getByRole("button", { name: "Попробовать снова" }).click();
  await expect(fork.getByRole("heading", { name: "Начните с первого доказательного пробела" })).toBeFocused();
});

test("stale program requires refresh before a new evidence route", async ({ page }) => {
  const { fork } = await openProgramFork(page);
  await page.route("**/agent/v1/programs?**", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.programs = payload.programs.map((program: { version: number }) => ({
      ...program,
      version: program.version + 1,
    }));
    await route.fulfill({ response, json: payload });
  }, { times: 1 });
  await fork.getByRole("button", { name: "Проверить выбранный вопрос" }).click();
  const alert = fork.getByRole("alert");
  await expect(alert).toBeFocused();
  await expect(alert).toContainText("Версия карты изменилась");
  await alert.getByRole("button", { name: "Обновить карту программы" }).click();
  await expect(alert).toHaveCount(0);
  await expect(fork.getByText(/ещё не читала карту/)).toBeVisible();
});
