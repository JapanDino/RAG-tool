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
        code: `REVIEW-${testInfo.project.name.toUpperCase()}`,
        title: `Ветка решений ${testInfo.project.name}`,
        description: "Пустая карта для проверки безопасного переключения.",
      },
    },
  );
  if (![201, 409].includes(second.status())) {
    throw new Error(`review program bootstrap failed: ${second.status()}`);
  }
});

async function openReviewDesk(
  page: import("@playwright/test").Page,
  identity = "designer@local.test",
) {
  await page.addInitScript((email) => {
    window.localStorage.setItem("rag-dev-user", email);
  }, identity);
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
  const desk = page.getByRole("region", { name: "Зафиксировать следующий шаг" });
  await expect(desk).toBeVisible();
  return { desk, select, demoValue };
}

test("author reviews evidence and explicitly saves one human decision", async ({ page }, testInfo) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  const { desk } = await openReviewDesk(page);
  await desk.getByRole("button", { name: "Подготовить заметку решения" }).click();
  await expect(desk.getByText("Уверенность правила", { exact: true })).toBeVisible();
  await expect(desk.getByText("Статус проверки", { exact: true })).toBeVisible();
  const editor = desk.getByRole("textbox", { name: "Заметка автора программы" });
  await editor.fill(
    `На совете программы проверить владельца пробела, срок и доступные основания до изменения карты. Проверка ${testInfo.project.name}.`,
  );
  await desk.getByLabel("В работу").check();
  await expect(desk.getByText("Несохранённые изменения", { exact: true })).toBeVisible();
  await desk.getByRole("button", { name: "Сохранить решение" }).click();
  const confirmation = desk.getByRole("group", { name: "Подтверждение решения" });
  await expect(confirmation).toBeFocused();
  await expect(confirmation).toContainText("Canvas не изменятся");
  await confirmation.getByRole("button", { name: "Подтвердить и сохранить" }).click();
  const receipt = desk.getByRole("status").filter({ hasText: "Решение записано" });
  await expect(receipt).toBeFocused();
  await expect(receipt).toContainText(/Сохранено · v\d+/);
  await desk.screenshot({ path: testInfo.outputPath("program-review-note-saved.png") });

  const overflow = await page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    return Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .map((element) => Math.ceil(element.getBoundingClientRect().right))
      .filter((right) => right > width + 1);
  });
  expect(overflow).toEqual([]);
  expect(browserErrors).toEqual([]);
});

test("program switch keeps a dirty note when the author cancels", async ({ page }) => {
  const { desk, select, demoValue } = await openReviewDesk(page);
  await desk.getByRole("button", { name: "Подготовить заметку решения" }).click();
  const editor = desk.getByRole("textbox", { name: "Заметка автора программы" });
  const retainedText = "Несохранённая редакция должна остаться после отмены переключения программы.";
  await editor.fill(retainedText);
  const otherValue = await select.locator("option").evaluateAll(
    (options, current) =>
      options
        .map((option) => (option as HTMLOptionElement).value)
        .find((value) => value !== current) ?? "",
    demoValue,
  );

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("несохранённые изменения");
    await dialog.dismiss();
  });
  await select.selectOption(otherValue);
  await expect(select).toHaveValue(demoValue);
  await expect(editor).toHaveValue(retainedText);
});

test("failed confirmed program switch restores the unchanged dirty note", async ({ page }) => {
  const { desk, select, demoValue } = await openReviewDesk(page);
  await desk.getByRole("button", { name: "Подготовить заметку решения" }).click();
  const editor = desk.getByRole("textbox", { name: "Заметка автора программы" });
  const retainedText = "Сетевая ошибка после подтверждения не должна уничтожить эту редакцию.";
  await editor.fill(retainedText);
  const otherValue = await select.locator("option").evaluateAll(
    (options, current) =>
      options
        .map((option) => (option as HTMLOptionElement).value)
        .find((value) => value !== current) ?? "",
    demoValue,
  );
  await page.route(`**/programs/${otherValue}/map`, async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Временная ошибка загрузки карты." }),
    });
  }, { times: 1 });
  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });

  await select.selectOption(otherValue);
  await expect(select).toHaveValue(demoValue);
  await expect(editor).toHaveValue(retainedText);
  await expect(desk.getByText("Несохранённые изменения", { exact: true })).toBeVisible();
});

test("methodologist sees the evidence workspace without an authoring control", async ({ page }) => {
  const { desk } = await openReviewDesk(page, "methodologist@local.test");
  await expect(desk.getByText("Решение сохраняет архитектор программы или администратор")).toBeVisible();
  await expect(desk.getByRole("button", { name: "Подготовить заметку решения" })).toHaveCount(0);
});
