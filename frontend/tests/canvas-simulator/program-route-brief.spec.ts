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
        code: `SECOND-${testInfo.project.name.toUpperCase()}`,
        title: `Вторая траектория ${testInfo.project.name}`,
        description: "Пустая программа для проверки безопасного переключения контекста.",
      },
    },
  );
  if (![201, 409].includes(second.status())) {
    throw new Error(`second program bootstrap failed: ${second.status()}`);
  }
});

test("methodologist gets one bounded route and opens evidence review", async ({ page }, testInfo) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await page.addInitScript(() => {
    window.localStorage.setItem("rag-dev-user", "methodologist@local.test");
  });
  await page.goto("/workspace/programs");

  const select = page.getByRole("combobox", { name: "Программа" });
  await expect(select).toBeVisible();
  const demoProgram = await select.locator("option").evaluateAll((options) => {
    const candidate = options
      .map((option) => ({
        label: option.textContent ?? "",
        value: (option as HTMLOptionElement).value,
      }))
      .find((option) => option.label.includes("CS-FOUND"));
    return candidate?.value ?? "";
  });
  expect(demoProgram).not.toBe("");
  await select.selectOption(demoProgram);

  const assistant = page.getByRole("region", { name: "С чего начать проверку программы" });
  await expect(assistant).toBeVisible();
  await expect(assistant.getByText(/без оценок людей и данных учеников/)).toBeVisible();
  const runButton = assistant.getByRole("button", { name: "Собрать маршрут проверки" });
  await runButton.focus();
  await page.keyboard.press("Enter");
  await expect(assistant.getByRole("status")).toContainText("Проверяем роль");
  const resultHeading = assistant.getByRole("heading", {
    name: /Начните с первого разрыва|Сначала добавьте первую компетенцию/,
  });
  await expect(resultHeading).toBeFocused();
  await expect(assistant.getByText("Факт по сохранённой карте", { exact: true })).toBeVisible();
  await expect(assistant).not.toContainText("student@local.test");
  await expect(assistant).not.toContainText("оценки учеников");
  await assistant.screenshot({ path: testInfo.outputPath("program-route-brief.png") });

  await assistant.getByRole("button", { name: "Открыть проверку доказательств" }).click();
  const auditRegion = page.getByLabel("Проверка доказательств программы");
  await expect(auditRegion).toBeFocused();
  await expect(auditRegion.getByText("Контрольная рейка", { exact: true })).toBeVisible();

  const values = await select.locator("option").evaluateAll((options) =>
    options.map((option) => (option as HTMLOptionElement).value),
  );
  const current = await select.inputValue();
  const other = values.find((value) => value !== current);
  expect(other).toBeTruthy();
  await select.selectOption(other!);
  await expect(assistant.getByRole("heading", { name: /Начните с первого разрыва/ })).toHaveCount(0);
  await expect(assistant.getByText(/Помощник пока ничего не анализировал/)).toBeVisible();
  await assistant.getByRole("button", { name: "Собрать маршрут проверки" }).click();
  await expect(
    assistant.getByRole("heading", { name: "Сначала добавьте первую компетенцию и свяжите её с курсом" }),
  ).toBeFocused();
  await expect(assistant.getByText(/Передайте её архитектору программы/)).toBeVisible();
  await expect(
    assistant.getByRole("button", { name: "Открыть проверку доказательств" }),
  ).toHaveCount(0);

  const overflow = await page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth;
    return Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .map((element) => ({
        className: element.className,
        right: Math.ceil(element.getBoundingClientRect().right),
        tag: element.tagName,
      }))
      .filter((element) => element.right > viewportWidth + 1);
  });
  expect(overflow).toEqual([]);
  expect(browserErrors).toEqual([]);
});

test("route failure is visible, focused, and retryable", async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("rag-dev-user", "methodologist@local.test");
  });
  await page.route("**/agent/v1/programs?**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        contract_version: "agent.v1",
        error: { message: "Маршрут временно недоступен." },
      }),
    });
  }, { times: 1 });
  await page.goto("/workspace/programs");
  const assistant = page.getByRole("region", { name: "С чего начать проверку программы" });
  await assistant.getByRole("button", { name: "Собрать маршрут проверки" }).click();
  const alert = assistant.getByRole("alert");
  await expect(alert).toBeFocused();
  await expect(alert).toContainText("Маршрут временно недоступен");
  await alert.screenshot({ path: testInfo.outputPath("program-route-brief-error.png") });
  await alert.getByRole("button", { name: "Попробовать снова" }).click();
  await expect(assistant.getByRole("heading", { name: /Начните с первого разрыва|Сначала добавьте первую компетенцию/ })).toBeFocused();
});

test("stale map offers refresh before a successful rerun", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("rag-dev-user", "methodologist@local.test");
  });
  await page.goto("/workspace/programs");
  const assistant = page.getByRole("region", { name: "С чего начать проверку программы" });
  await expect(assistant).toBeVisible();
  await page.route(
    "**/agent/v1/programs?**",
    async (route) => {
      const response = await route.fetch();
      const payload = await response.json();
      payload.programs = payload.programs.map((program: { version: number }) => ({
        ...program,
        version: program.version + 1,
      }));
      await route.fulfill({ response, json: payload });
    },
    { times: 1 },
  );
  await assistant.getByRole("button", { name: "Собрать маршрут проверки" }).click();
  const alert = assistant.getByRole("alert");
  await expect(alert).toBeFocused();
  await expect(alert).toContainText("Версия карты изменилась");
  await alert.getByRole("button", { name: "Обновить карту программы" }).click();
  await expect(alert).toHaveCount(0);
  await expect(assistant.getByText(/Помощник пока ничего не анализировал/)).toBeVisible();
  await assistant.getByRole("button", { name: "Собрать маршрут проверки" }).click();
  await expect(
    assistant.getByRole("heading", { name: /Начните с первого разрыва|Сначала добавьте первую компетенцию/ }),
  ).toBeFocused();
});

test("truncated analysis never looks like an all-clear", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("rag-dev-user", "methodologist@local.test");
  });
  await page.route("**/agent/v1/runs/**/execute", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (payload.status === "completed" && payload.response?.mode === "program_route_brief") {
      payload.response.analysis_truncated = true;
      payload.response.findings_truncated = false;
      payload.response.priorities = [];
      payload.response.headline =
        "Карта проверена не полностью — начните с ручной проверки доказательств";
    }
    await route.fulfill({ response, json: payload });
  });
  await page.goto("/workspace/programs");
  const assistant = page.getByRole("region", { name: "С чего начать проверку программы" });
  await assistant.getByRole("button", { name: "Собрать маршрут проверки" }).click();
  await expect(
    assistant.getByRole("heading", {
      name: "Карта проверена не полностью — начните с ручной проверки доказательств",
    }),
  ).toBeFocused();
  await expect(assistant.getByRole("status")).toContainText("Проверена не вся карта");
  await expect(assistant).not.toContainText("Явных разрывов базовой карты сейчас не видно");
});
