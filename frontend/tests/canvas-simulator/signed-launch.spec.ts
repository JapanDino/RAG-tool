import { expect, test } from "@playwright/test";

const BACKEND_PORT = process.env.CANVAS_SIMULATOR_E2E_BACKEND_PORT || "8000";
const FRONTEND_PORT = process.env.CANVAS_SIMULATOR_E2E_FRONTEND_PORT || "3000";
const API_BASE = `http://localhost:${BACKEND_PORT}`;
const APP_BASE = `http://localhost:${FRONTEND_PORT}`;

type Fixture = {
  id: "demo-ai" | "demo-review";
  course: string;
  module: string;
  item: string;
  question: string;
  source: string;
};

const fixtures: Fixture[] = [
  {
    id: "demo-ai",
    course: "Проектная лаборатория: ИИ-сервисы",
    module: "01. Данные и поиск",
    item: "Как устроен RAG-пайплайн Страница",
    question: "Как RAG использует найденные фрагменты?",
    source: "Как устроен RAG-пайплайн",
  },
  {
    id: "demo-review",
    course: "Русский язык: мастерская рецензии",
    module: "Неделя 2. Собираем текст",
    item: "Критерии итоговой рецензии Страница",
    question: "Какие критерии делают рецензию аргументированной?",
    source: "Критерии итоговой рецензии",
  },
];

const courseIds = new Map<Fixture["id"], number>();

test.beforeAll(async ({ request }) => {
  const response = await request.post(
    `${API_BASE}/integrations/lti/development/simulator/bootstrap`,
    {
      data: {
        canvas_base_url: APP_BASE,
        lti_base_url: API_BASE,
      },
    },
  );
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(payload.courses).toHaveLength(2);
  for (const course of payload.courses) {
    courseIds.set(course.fixture_id, course.course_id);
  }
});

for (const fixture of fixtures) {
  test(`${fixture.id}: signed launch keeps exact course and module scope`, async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (["error", "warning"].includes(message.type())) consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    await page.goto("/canvas-simulator");
    await page.getByRole("link", { name: `Помощник курса — ${fixture.course}` }).click();
    const tool = page.frameLocator("iframe");
    await expect(tool.getByRole("heading", { name: "Запуск подтверждён" })).toBeVisible();
    await expect(tool.getByText(fixture.course, { exact: true })).toBeVisible();
    await tool.getByRole("link", { name: "Открыть курс" }).click();

    await expect(tool.getByRole("heading", { name: fixture.course, exact: true })).toBeVisible();
    await expect(tool.getByRole("heading", { name: "Идите по знакомому порядку" })).toBeVisible();
    await expect(tool.getByText("Страница", { exact: true }).first()).toBeVisible();
    await expect(tool.getByText("Задание", { exact: true }).first()).toBeVisible();
    await expect(tool.getByText("Файл", { exact: true }).first()).toBeVisible();
    await expect(tool.getByText("Внешний источник", { exact: true }).first()).toBeVisible();
    await expect(tool.getByText("Раздел", { exact: true }).first()).toBeVisible();

    await page.evaluate(() => {
      document.documentElement.style.scrollBehavior = "auto";
      window.scrollTo(0, 0);
    });
    await tool.locator("html").evaluate((element) => { element.scrollTop = 0; });
    await page.screenshot({ path: testInfo.outputPath(`${fixture.id}-course-map.png`) });

    await tool.getByRole("button", { name: fixture.item }).click();
    const ask = testInfo.project.name === "mobile"
      ? tool.getByRole("link", { name: `Задать вопрос по выбранному разделу ${fixture.module}` })
      : tool.getByRole("link", { name: `Задать вопрос здесь Помощник уже ограничен разделом «${fixture.module}»` });
    await expect(ask).toHaveAttribute("href", "#course-assistant");
    await ask.click();

    await expect(tool.locator("#course-assistant").getByText(fixture.source, { exact: true })).toBeVisible();
    await expect(tool.getByText(`Поиск ограничен разделом «${fixture.module}». Если опоры не хватит, помощник так и скажет.`)).toBeVisible();
    await tool.getByRole("textbox", { name: "Что нужно разобрать?" }).fill(fixture.question);
    await page.route("**/agent/v1/messages", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 500));
      await route.continue();
    }, { times: 1 });
    await tool.getByRole("button", { name: "Разобраться" }).click();
    await expect(tool.getByRole("button", { name: "Ищем опору в курсе…" })).toBeVisible();
    await expect(tool.locator('button[aria-pressed="false"]').first()).toBeDisabled();
    await expect(tool.getByRole("button", { name: "Удалить мою историю помощника" })).toBeDisabled();
    await page.screenshot({ path: testInfo.outputPath(`${fixture.id}-embedded-agent-loading.png`) });
    const answerHeading = tool.getByRole("heading", { name: "Объяснение готово" });
    await expect(answerHeading).toBeVisible();
    await expect(tool.getByRole("heading", { name: "Опора в курсе" })).toBeVisible();
    await expect(tool.getByRole("button", { name: "Разобраться" })).toBeVisible();
    const citations = tool.locator("blockquote");
    const citationCount = await citations.count();
    expect(citationCount).toBeGreaterThan(0);
    const citationText = await citations.allTextContents();
    expect(citationText.every((value) => value.includes(fixture.module))).toBeTruthy();
    const citationSource = citations.first().getByRole("link", { name: /^Открыть/ });
    await expect(citationSource).toBeVisible();
    await citationSource.focus();
    await expect(citationSource).toBeFocused();
    const citationSourceHref = await citationSource.getAttribute("href");
    expect(citationSourceHref).toBeTruthy();
    const citationRedirect = await page.context().request.get(citationSourceHref!, {
      maxRedirects: 0,
    });
    expect(citationRedirect.status()).toBe(303);
    expect(citationRedirect.headers()["referrer-policy"]).toBe("no-referrer");

    const courseId = courseIds.get(fixture.id);
    expect(courseId).toBeTruthy();
    const teacherBoundary = await page.context().request.get(
      `${API_BASE}/courses/${courseId}/teacher-workspace`,
    );
    expect(teacherBoundary.status()).toBe(404);

    await page.evaluate(() => {
      document.documentElement.style.scrollBehavior = "auto";
      window.scrollTo(0, 0);
    });
    await answerHeading.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`${fixture.id}-embedded-agent-answer.png`) });

    const alternateMaterial = tool.locator('button[aria-pressed="false"]').first();
    await alternateMaterial.click();
    await expect(answerHeading).toHaveCount(0);
    await expect(tool.locator("button[aria-pressed]").filter({ hasText: fixture.question })).toBeVisible();
    await tool.getByRole("button", { name: fixture.item }).click();

    await tool.getByRole("button", { name: "Получить подсказку", exact: true }).click();
    const hintHeading = tool.getByRole("heading", { name: "Подсказка готова" });
    await expect(hintHeading).toBeVisible({ timeout: 45_000 });
    await expect(tool.getByText("Подсказка без готового ответа", { exact: true })).toBeVisible();
    await expect(tool.getByRole("heading", { name: "Опора в курсе" })).toBeVisible();
    await hintHeading.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`${fixture.id}-embedded-agent-hint.png`) });

    const sourceTask = tool.locator("#course-assistant").getByRole("button", {
      name: "Открыть источник",
      exact: true,
    });
    await expect(sourceTask).toBeEnabled();
    await sourceTask.click();
    const sourceHeading = tool.getByRole("heading", { name: "Источник готов к открытию" });
    await expect(sourceHeading).toBeVisible();
    const safeSource = tool.locator("#course-assistant").getByRole("link", { name: /^Открыть/ });
    const safeSourceHref = await safeSource.getAttribute("href");
    expect(safeSourceHref).toBeTruthy();
    const redirect = await page.context().request.get(safeSourceHref!, { maxRedirects: 0 });
    expect(redirect.status()).toBe(303);
    expect(redirect.headers().location).toBeTruthy();
    await sourceHeading.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`${fixture.id}-embedded-agent-source.png`) });

    const selfCheckTask = tool.locator("#course-assistant").getByRole("button", {
      name: "Проверить себя",
      exact: true,
    });
    await selfCheckTask.click();
    const selfCheckHeading = tool.getByRole("heading", { name: "Самопроверка готова" });
    await expect(selfCheckHeading).toBeVisible({ timeout: 30_000 });
    await expect(tool.getByText("Самопроверка без оценки", { exact: true })).toBeVisible();
    await expect(tool.getByText("Проверьте понимание без оценки и готовых ответов:", { exact: false })).toBeVisible();
    await expect(tool.getByRole("heading", { name: "Опора в курсе" })).toBeVisible();
    await selfCheckHeading.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`${fixture.id}-embedded-agent-self-check.png`) });

    const helpful = tool.getByRole("button", { name: "Да, помогло" });
    await helpful.click();
    await expect(helpful).toHaveAttribute("aria-pressed", "true");
    await tool.getByRole("textbox", { name: "Что нужно разобрать?" }).fill("Какая погода сейчас на Марсе?");
    await tool.getByRole("button", { name: "Разобраться" }).click();
    const abstentionHeading = tool.getByRole("heading", { name: "В материалах курса недостаточно информации" });
    await expect(abstentionHeading).toBeVisible();
    await expect(tool.getByText("Нужна другая опора", { exact: true })).toBeVisible();
    await abstentionHeading.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`${fixture.id}-embedded-agent-abstention.png`) });
    await tool.getByRole("button", { name: "Удалить мою историю помощника" }).click();
    await expect(tool.getByText("Удалить вопросы, ответы и оценки этого курса?", { exact: true })).toBeVisible();
    await tool.getByRole("button", { name: "Да, удалить" }).click();
    await expect(tool.getByRole("status")).toHaveText("История помощника удалена.");
    const history = await page.context().request.get(
      `${API_BASE}/courses/${courseIds.get(fixture.id)}/qa`,
    );
    expect(history.status()).toBe(200);
    expect(await history.json()).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`${fixture.id}-embedded-agent-history-deleted.png`) });

    const outerOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    const innerOverflow = await tool.locator("html").evaluate(
      (element) => element.scrollWidth - element.clientWidth,
    );
    expect(outerOverflow).toBe(0);
    expect(innerOverflow).toBe(0);

    if (testInfo.project.name === "mobile") {
      const menu = page.getByRole("button", { name: "Открыть меню Canvas" });
      await menu.click();
      const closeMenu = page.getByRole("button", { name: "Закрыть меню Canvas" }).first();
      await expect(closeMenu).toHaveAttribute("aria-expanded", "true");
      await page.keyboard.press("Escape");
      await expect(menu).toBeFocused();
    }

    expect(consoleErrors).toEqual([]);
  });
}

test("learner conversation reuses grouping without hidden turn replay", async ({ page }, testInfo) => {
  const fixture = fixtures[0];
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.goto("/canvas-simulator");
  await page.getByRole("link", { name: `Помощник курса — ${fixture.course}` }).click();
  const tool = page.frameLocator("iframe");
  await tool.getByRole("link", { name: "Открыть курс" }).click();
  await expect(tool.getByRole("heading", { name: fixture.course, exact: true })).toBeVisible();
  await tool.getByRole("button", { name: fixture.item }).click();

  const messageBodies: Array<{ message: string; conversation_id?: string }> = [];
  const executeBodies: Array<{ message: string; conversation_id?: string }> = [];
  const acceptedConversationIds: string[] = [];
  await page.route("**/agent/v1/messages", async (route) => {
    messageBodies.push(route.request().postDataJSON());
    const response = await route.fetch();
    const body = await response.body();
    const payload = JSON.parse(body.toString()) as { conversation_id: string };
    acceptedConversationIds.push(payload.conversation_id);
    await route.fulfill({
      status: response.status(),
      headers: response.headers(),
      body,
    });
  });
  await page.route("**/agent/v1/runs/*/execute", async (route) => {
    executeBodies.push(route.request().postDataJSON());
    await route.continue();
  });

  const firstQuestion = "Как RAG использует найденные фрагменты?";
  const secondQuestion = "Почему найденные фрагменты нужно проверять перед ответом?";
  const textbox = tool.getByRole("textbox", { name: "Что нужно разобрать?" });
  await textbox.fill(firstQuestion);
  await tool.getByRole("button", { name: "Разобраться" }).click();
  await expect(tool.getByRole("heading", { name: "Объяснение готово" })).toBeVisible();

  await textbox.fill(secondQuestion);
  await tool.getByRole("button", { name: "Разобраться" }).click();
  const secondTurn = tool.locator("button[aria-pressed]").filter({ hasText: secondQuestion });
  await expect(secondTurn).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  expect(messageBodies).toHaveLength(2);
  expect(messageBodies[0]).toEqual(expect.objectContaining({ message: firstQuestion }));
  expect(messageBodies[0].conversation_id).toBeUndefined();
  expect(messageBodies[1]).toEqual(expect.objectContaining({
    message: secondQuestion,
    conversation_id: acceptedConversationIds[0],
  }));
  expect(acceptedConversationIds[1]).toBe(acceptedConversationIds[0]);
  const firstExecuteBodies = executeBodies.filter((body) => body.message === firstQuestion);
  const secondExecuteBodies = executeBodies.filter((body) => body.message === secondQuestion);
  expect(firstExecuteBodies.length).toBeGreaterThan(0);
  expect(secondExecuteBodies.length).toBeGreaterThan(0);
  expect(firstExecuteBodies.every((body) => body.conversation_id === undefined)).toBeTruthy();
  expect(secondExecuteBodies.every(
    (body) => body.conversation_id === acceptedConversationIds[0],
  )).toBeTruthy();
  expect(executeBodies.every(
    (body) => body.message === firstQuestion || body.message === secondQuestion,
  )).toBeTruthy();
  await expect(tool.getByText("Предыдущий текст не отправляется модели скрыто.", { exact: false })).toBeVisible();

  const firstTurn = tool.locator("button[aria-pressed]").filter({ hasText: firstQuestion });
  await firstTurn.click();
  await expect(firstTurn).toHaveAttribute("aria-pressed", "true");
  await expect(secondTurn).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await expect(tool.getByRole("heading", { name: "Опора в курсе" })).toBeVisible();
  await firstTurn.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("learner-conversation.png") });
  const outerOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  const innerOverflow = await tool.locator("html").evaluate(
    (element) => element.scrollWidth - element.clientWidth,
  );
  expect(outerOverflow).toBe(0);
  expect(innerOverflow).toBe(0);
  expect(consoleErrors).toEqual([]);
});

test("unsupported material cannot start learner generation", async ({ page }) => {
  const fixture = fixtures[0];
  await page.goto("/canvas-simulator");
  await page.getByRole("link", { name: `Помощник курса — ${fixture.course}` }).click();
  const tool = page.frameLocator("iframe");
  await page.route("**/course-map", async (route) => {
    const response = await route.fetch();
    const payload = await response.json() as {
      modules: Array<{ items: Array<{ title: string; item_type: string; supported: boolean }> }>;
    };
    const item = payload.modules.flatMap((module) => module.items)
      .find((candidate) => candidate.title === fixture.source);
    expect(item).toBeTruthy();
    item!.item_type = "unsupported";
    item!.supported = false;
    await route.fulfill({ response, json: payload });
  }, { times: 1 });
  await tool.getByRole("link", { name: "Открыть курс" }).click();
  await tool.getByRole("button", { name: new RegExp(fixture.source) }).click();
  await expect(tool.getByText("Тип пока не поддерживается", { exact: true })).toBeVisible();

  let messageRequests = 0;
  await page.route("**/agent/v1/messages", async (route) => {
    messageRequests += 1;
    await route.continue();
  });
  const hint = tool.getByRole("button", { name: "Получить подсказку", exact: true });
  await expect(hint).toBeDisabled();
  await hint.evaluate((button) => {
    button.removeAttribute("disabled");
    button.click();
  });
  await page.waitForTimeout(250);
  expect(messageRequests).toBe(0);
  await expect(tool.getByRole("textbox", { name: "Что нужно разобрать?" })).toBeDisabled();
});

test("reopened failed turn retries its immutable request scope", async ({ page }) => {
  const fixture = fixtures[0];
  await page.goto("/canvas-simulator");
  await page.getByRole("link", { name: `Помощник курса — ${fixture.course}` }).click();
  const tool = page.frameLocator("iframe");
  await tool.getByRole("link", { name: "Открыть курс" }).click();
  await tool.getByRole("button", { name: fixture.item }).click();

  const messageBodies: Array<{
    message: string;
    selection?: { module_ref: string; evidence_ref?: string };
  }> = [];
  let conversationId = "";
  await page.route("**/agent/v1/messages", async (route) => {
    messageBodies.push(route.request().postDataJSON());
    const response = await route.fetch();
    const body = await response.body();
    const payload = JSON.parse(body.toString()) as { conversation_id: string };
    conversationId ||= payload.conversation_id;
    await route.fulfill({ status: response.status(), headers: response.headers(), body });
  });
  let failNextExecute = true;
  await page.route("**/agent/v1/runs/*/execute", async (route) => {
    if (!failNextExecute) {
      await route.continue();
      return;
    }
    failNextExecute = false;
    const runId = route.request().url().match(/\/runs\/([^/]+)\/execute/)?.[1];
    expect(runId).toBeTruthy();
    const now = new Date().toISOString();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        contract_version: "agent.v1",
        run_id: runId,
        conversation_id: conversationId,
        workflow: "open_authoritative_source",
        status: "failed",
        route_state: "routed",
        user_state: { label: "Источник временно не подготовился", recovery_action: "clarify_request" },
        response: null,
        review: null,
        created_at: now,
        updated_at: now,
      }),
    });
  });

  await tool.getByRole("button", { name: "Открыть источник", exact: true }).click();
  await expect(tool.getByRole("heading", { name: "Источник временно не подготовился" })).toBeVisible();
  const failedTurn = tool.locator("button[aria-pressed]").filter({
    hasText: "Открой источник этого материала",
  });
  await expect(failedTurn).toBeVisible();

  const secondQuestion = "Почему найденные фрагменты нужно проверять?";
  await tool.getByRole("textbox", { name: "Что нужно разобрать?" }).fill(secondQuestion);
  await tool.getByRole("button", { name: "Разобраться" }).click();
  await expect(tool.getByRole("heading", { name: "Объяснение готово" })).toBeVisible();
  await failedTurn.click();
  await expect(failedTurn).toHaveAttribute("aria-pressed", "true");
  await tool.getByRole("button", { name: "Повторить этот запрос" }).click();
  await expect(tool.getByRole("heading", { name: "Источник готов к открытию" })).toBeVisible();

  expect(messageBodies).toHaveLength(3);
  expect(messageBodies[2].message).toBe(messageBodies[0].message);
  expect(messageBodies[2].selection).toEqual(messageBodies[0].selection);
  expect(messageBodies[2].selection).not.toEqual(messageBodies[1].selection);
  expect(messageBodies[2].selection?.evidence_ref).toBeTruthy();
});

test("learner quick action retries the exact failed request", async ({ page }, testInfo) => {
  const fixture = fixtures[0];
  await page.goto("/canvas-simulator");
  await page.getByRole("link", { name: `Помощник курса — ${fixture.course}` }).click();
  const tool = page.frameLocator("iframe");
  await tool.getByRole("link", { name: "Открыть курс" }).click();
  await expect(tool.getByRole("heading", { name: fixture.course, exact: true })).toBeVisible();
  await tool.getByRole("button", { name: fixture.item }).click();

  const requests: string[] = [];
  await page.route("**/agent/v1/messages", async (route) => {
    const body = route.request().postDataJSON() as { message: string };
    requests.push(body.message);
    if (requests.length === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          contract_version: "agent.v1",
          error: {
            code: "TEMPORARY_FAILURE",
            message: "Сервис временно недоступен.",
            retryable: true,
            recovery_action: "retry_later",
            request_id: "req_retry_test",
          },
        }),
      });
      return;
    }
    await route.continue();
  });

  await tool.getByRole("button", { name: "Проверить себя", exact: true }).click();
  const failedAlert = tool.getByRole("alert").filter({ hasText: "Ответ не подготовился" });
  await expect(failedAlert).toContainText("Ответ не подготовился");
  await expect(tool.getByRole("textbox", { name: "Что нужно разобрать?" })).toHaveValue("");
  await expect(tool.getByRole("button", { name: "Разобраться" })).toBeDisabled();
  await failedAlert.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("embedded-agent-request-failed.png") });
  const retryButton = tool.getByRole("button", { name: "Попробовать снова" });
  await retryButton.focus();
  await expect(retryButton).toBeFocused();
  await retryButton.click();
  const retryHeading = tool.getByRole("heading", { name: "Самопроверка готова" });
  await expect(retryHeading).toBeVisible();
  expect(requests).toHaveLength(2);
  expect(requests[1]).toBe(requests[0]);
  expect(requests[1]).toContain("Проверь меня");
  await retryHeading.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("embedded-agent-exact-retry.png") });

  const helpful = tool.getByRole("button", { name: "Да, помогло" });
  await page.route("**/agent/v1/runs/*/feedback", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "Оценка временно не сохранилась." } }),
    });
  }, { times: 1 });
  await helpful.click();
  await expect(tool.getByText("Оценка не сохранилась", { exact: true })).toBeVisible();
  await tool.getByRole("button", { name: "Попробовать снова" }).click();
  await expect(helpful).toHaveAttribute("aria-pressed", "true");

  await tool.getByRole("button", { name: "Удалить мою историю помощника" }).click();
  await page.route("**/courses/*/qa/history", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "Удаление временно недоступно." } }),
    });
  }, { times: 1 });
  await tool.getByRole("button", { name: "Да, удалить" }).click();
  await expect(tool.getByText("История не удалилась", { exact: true })).toBeVisible();
  await tool.getByRole("button", { name: "Отмена", exact: true }).click();
  await expect(tool.getByText("История не удалилась", { exact: true })).toHaveCount(0);
  await expect(tool.getByRole("button", { name: "Попробовать снова" })).toHaveCount(0);
  await tool.getByRole("button", { name: "Удалить мою историю помощника" }).click();
  await tool.getByRole("button", { name: "Да, удалить" }).click();
  await expect(tool.getByRole("status")).toHaveText("История помощника удалена.");
});

for (const boundary of [
  { status: 401, heading: "Откройте помощника ещё раз из курса Canvas", name: "expired" },
  { status: 404, heading: "Вернитесь в текущий курс Canvas", name: "permission" },
]) {
  test(`agent ${boundary.status} response hides course context`, async ({ page }, testInfo) => {
    const fixture = fixtures[0];
    await page.goto("/canvas-simulator");
    await page.getByRole("link", { name: `Помощник курса — ${fixture.course}` }).click();
    const tool = page.frameLocator("iframe");
    await tool.getByRole("link", { name: "Открыть курс" }).click();
    await expect(tool.getByRole("heading", { name: fixture.course, exact: true })).toBeVisible();
    await tool.getByRole("button", { name: fixture.item }).click();
    await tool.getByRole("textbox", { name: "Что нужно разобрать?" }).fill(fixture.question);
    await page.route("**/agent/v1/runs/*/execute", async (route) => {
      await route.fulfill({
        status: boundary.status,
        contentType: "application/json",
        body: JSON.stringify({
          contract_version: "agent.v1",
          error: {
            code: boundary.status === 401 ? "SESSION_EXPIRED" : "ACCESS_DENIED",
            message: "Контекст больше недоступен.",
            retryable: false,
            recovery_action: "relaunch_from_canvas",
            request_id: `req_${boundary.name}_test`,
          },
        }),
      });
    }, { times: 1 });
    await tool.getByRole("button", { name: "Разобраться" }).click();
    await expect(tool.getByRole("heading", { name: boundary.heading })).toBeVisible();
    await expect(tool.getByText(fixture.course, { exact: true })).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath(`embedded-agent-${boundary.name}.png`) });
  });
}

for (const fixture of fixtures) {
  test(`${fixture.id}: instructor launch opens exact protected workspace`, async ({ page }, testInfo) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (["error", "warning"].includes(message.type())) consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    await page.goto("/canvas-simulator");
    await page.getByRole("link", { name: `Помощник курса — ${fixture.course}` }).click();
    const instructorChoice = page.getByRole("link", { name: "Преподаватель", exact: true });
    await instructorChoice.click();
    await expect(page.getByRole("link", { name: "Преподаватель", exact: true })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(page.getByRole("status")).toContainText("рабочее место преподавателя");

    const tool = page.frameLocator("iframe");
    await expect(tool.getByRole("heading", { name: "Запуск подтверждён" })).toBeVisible();
    await expect(tool.getByText("Преподаватель", { exact: true })).toBeVisible();
    await expect(tool.getByText(fixture.course, { exact: true })).toBeVisible();
    await tool.getByRole("link", { name: "Открыть курс" }).click();

    await expect(tool.getByRole("heading", { name: fixture.course, exact: true })).toBeVisible();
    await expect(tool.getByText("Очередь внимания преподавателя", { exact: true })).toBeVisible();
    await expect(tool.getByText("Доступ через Canvas", { exact: true })).toBeVisible();
    await expect(tool.getByText("Что сейчас непонятно?", { exact: true })).toHaveCount(0);

    const reviewBrief = tool.locator("section").filter({
      has: tool.getByRole("heading", { name: "С чего начать проверку" }),
    });
    await expect(reviewBrief).toBeVisible();

    const improvementLoop = tool.locator("section").filter({
      has: tool.getByRole("heading", { name: "Где ученикам не хватает опоры" }),
    });
    await expect(improvementLoop).toBeVisible();
    await expect(improvementLoop.getByText("Только общий сигнал", { exact: true })).toBeVisible();
    await expect(improvementLoop).not.toContainText("Алина Соколова");
    await expect(improvementLoop).not.toContainText("Синтетический вопрос");
    const findGaps = improvementLoop.getByRole("button", {
      name: "Найти повторяющиеся трудности",
      exact: true,
    });
    await findGaps.click();
    await expect(
      improvementLoop.getByRole("button", { name: "Проверяем общий сигнал…", exact: true }),
    ).toBeVisible();
    await expect(
      improvementLoop.getByRole("heading", { name: "Есть общий сигнал для улучшения" }),
    ).toBeFocused({ timeout: 60_000 });
    await expect(improvementLoop.getByText("Охват группы", { exact: true })).toBeVisible();
    await expect(improvementLoop.getByText("3–5", { exact: true })).toHaveCount(2);
    await improvementLoop.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`${fixture.id}-course-improvement-signal.png`) });

    if (fixture.id === "demo-review") {
      await page.route("**/agent/v1/gaps/*/draft", async (route) => {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ error: { message: "Материал временно недоступен." } }),
        });
      }, { times: 1 });
    }
    if (fixture.id === "demo-ai" || fixture.id === "demo-review") {
      await improvementLoop.getByRole("button", { name: "Подготовить материал", exact: true }).click();
      if (fixture.id === "demo-review") {
        const preparationError = improvementLoop.getByRole("alert").filter({
          hasText: "Материал не подготовился",
        });
        await expect(preparationError).toBeVisible();
        await preparationError.getByRole("button", { name: "Попробовать снова" }).click();
      }
      const interventionEditor = improvementLoop.getByRole("textbox", { name: "Текст материала" });
      await expect(interventionEditor).toBeVisible({ timeout: 60_000 });
      const interventionSheet = interventionEditor.locator("xpath=ancestor::article[1]");
      await expect(interventionSheet.getByRole("heading")).toBeFocused();
      await interventionEditor.fill(`${await interventionEditor.inputValue()}\n\nПроверено преподавателем.`);
      await interventionSheet.getByRole("heading").evaluate((heading) => {
        heading.scrollIntoView({ behavior: "auto", block: "start" });
      });
      await page.waitForTimeout(100);
      await page.screenshot({
        path: testInfo.outputPath(`${fixture.id}-course-improvement-draft.png`),
      });
      const decision = fixture.id === "demo-ai" ? "Принять после проверки" : "Отклонить";
      const decisionStatus = fixture.id === "demo-ai" ? "Принято" : "Отклонено";
      await improvementLoop.getByRole("button", { name: decision, exact: true }).click();
      await expect(improvementLoop.getByRole("status", { name: decisionStatus })).toBeFocused();
      await expect(improvementLoop.getByText("Canvas не изменён", { exact: true })).toBeVisible();
    }

    const priorityButton = reviewBrief.getByRole("button", { name: "Проверить приоритет" });
    await priorityButton.scrollIntoViewIfNeeded();
    await page.route("**/agent/v1/messages", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 350));
      await route.continue();
    }, { times: 1 });
    await priorityButton.click();
    await expect(reviewBrief.getByRole("button", { name: "Собираем сводку…" })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`${fixture.id}-instructor-agent-loading.png`) });
    await expect(reviewBrief.getByText("Рекомендация на сейчас", { exact: true })).toBeVisible();
    const openEvidence = reviewBrief.getByRole("button", { name: "Открыть доказательства" }).first();
    await expect(openEvidence).toBeVisible();
    await reviewBrief.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`${fixture.id}-instructor-agent-summary.png`) });
    await openEvidence.click();
    await expect(reviewBrief.getByRole("button", { name: "Проверяем доказательства…" })).toBeVisible();
    await expect(openEvidence).toBeVisible();
    await expect(tool.locator("#review-workbench")).toBeVisible();
    await expect(tool.locator("#review-workbench article h2").first()).toBeFocused();
    if (fixture.id === "demo-ai") {
      await tool.getByRole("button", { name: "Подтвердить", exact: true }).click();
      const prepareDraft = tool.getByRole("button", {
        name: /^Подготовить (черновик|новый вариант)$/,
      });
      await expect(prepareDraft).toBeEnabled();
      await prepareDraft.click();
      const draftEditor = tool.getByRole("textbox", { name: "Текст черновика" });
      await expect(draftEditor).toBeVisible({ timeout: 60_000 });
      await expect(tool.locator("#review-workbench article h4").first()).toBeFocused();
      await draftEditor.scrollIntoViewIfNeeded();
      await page.screenshot({ path: testInfo.outputPath("demo-ai-instructor-agent-draft.png") });
      await tool.getByRole("button", { name: "Принять после проверки", exact: true }).click();
      await expect(tool.getByText("Принят", { exact: true })).toBeVisible();
      await expect(
        tool.getByRole("heading", { name: "Как это будет выглядеть в Canvas" }),
      ).toBeFocused();
      const previewButton = tool.getByRole("button", {
        name: "Показать изменения для Canvas",
        exact: true,
      });
      await expect(previewButton).toBeEnabled();
      await previewButton.click();
      await expect(
        tool.getByRole("button", { name: "Собираем предпросмотр…", exact: true }),
      ).toBeVisible();
      await expect(tool.getByText("Предпросмотр · без публикации", { exact: true })).toBeVisible({
        timeout: 60_000,
      });
      const previewSection = tool
        .getByRole("heading", { name: "Как это будет выглядеть в Canvas" })
        .locator("xpath=ancestor::section[1]");
      await previewSection.scrollIntoViewIfNeeded();
      await page.screenshot({ path: testInfo.outputPath("demo-ai-instructor-agent-preview.png") });
      await previewSection.screenshot({
        path: testInfo.outputPath("demo-ai-instructor-agent-preview-detail.png"),
      });
    }

    const courseId = courseIds.get(fixture.id);
    expect(courseId).toBeTruthy();
    const teacherWorkspace = await page.context().request.get(
      `${API_BASE}/courses/${courseId}/teacher-workspace`,
    );
    expect(teacherWorkspace.status()).toBe(200);
    const learnerBoundary = await page.context().request.get(`${API_BASE}/course-map`);
    expect(learnerBoundary.status()).toBe(404);

    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: testInfo.outputPath(`${fixture.id}-instructor-workspace.png`) });
    const outerOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    const innerOverflow = await tool.locator("html").evaluate(
      (element) => element.scrollWidth - element.clientWidth,
    );
    expect(outerOverflow).toBe(0);
    expect(innerOverflow).toBe(0);
    const unexpectedConsoleErrors = consoleErrors.filter(
      (message) => !(fixture.id === "demo-review" && message.includes("503 (Service Unavailable)")),
    );
    expect(unexpectedConsoleErrors).toEqual([]);
  });
}

test("bounded simulator states fail closed", async ({ page }) => {
  const states = [
    ["loading", "Загружаем курс…", "status"],
    ["unavailable", "Этот материал пока нельзя открыть", "alert"],
    ["expired", "Откройте помощника из курса ещё раз", "alert"],
    ["wrong-course", "Запуск не совпадает с текущим курсом", "alert"],
    ["wrong-role", "Помощник не открыл материалы", "alert"],
    ["error", "Курс сейчас не загрузился", "alert"],
    ["empty", "Помощнику пока не на что опереться", "alert"],
    ["unsupported", "Этот объект нельзя использовать как источник", "alert"],
  ] as const;

  for (const [state, heading, role] of states) {
    await page.goto(`/canvas-simulator/courses/demo-ai?view=assistant&state=${state}`);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await expect(page.locator(`main section[role="${role}"]`)).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBe(0);
  }
});

test("signed resolver denial never falls back to the unsigned assistant", async ({ page, request }) => {
  const moveAway = await request.post(
    `${API_BASE}/integrations/lti/development/simulator/bootstrap`,
    {
      data: {
        canvas_base_url: APP_BASE,
        lti_base_url: `http://127.0.0.1:${BACKEND_PORT}`,
      },
    },
  );
  expect(moveAway.ok()).toBeTruthy();
  try {
    await page.goto("/canvas-simulator/courses/demo-ai?view=assistant&actor=instructor");
    await expect(page.getByRole("heading", { name: "Этот материал пока нельзя открыть" })).toBeVisible();
    await expect(page.locator("iframe")).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "Спросить по материалам" })).toHaveCount(0);
  } finally {
    const restore = await request.post(
      `${API_BASE}/integrations/lti/development/simulator/bootstrap`,
      {
        data: {
          canvas_base_url: APP_BASE,
          lti_base_url: API_BASE,
        },
      },
    );
    expect(restore.ok()).toBeTruthy();
  }
});
