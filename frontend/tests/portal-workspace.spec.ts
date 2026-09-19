import { expect, test } from "@playwright/test";

test("returning to chat refreshes policy without restoring withdrawn consent or losing drafts", async ({
    page,
}) => {
    await page.addInitScript(() =>
        sessionStorage.setItem("canvas_portal_token", "workspace-test"),
    );
    let enabled = true;
    let unavailable = false;
    let title = "Первая версия";
    await page.route("**/api-proxy/portal/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith("/preferences") && unavailable)
            return route.fulfill({ status: 503, json: {} });
        return route.fulfill({
            json: path.endsWith("/session")
                ? {
                      title: "Биология",
                      role: "student",
                      storage_scope: "policy-audit",
                  }
                : path.endsWith("/preferences")
                  ? { quality_enabled: enabled }
                  : path.endsWith("/materials")
                    ? [
                          {
                              document_id: 1,
                              title,
                              published: true,
                              kind: "literature",
                          },
                      ]
                    : {},
        });
    });
    await page.goto("/portal");
    const consent = page.getByRole("checkbox", {
        name: "Добавлять мои вопросы и ответы в журнал качества",
    });
    await consent.check();
    await page
        .getByRole("textbox", { name: "Ваш вопрос", exact: true })
        .fill("Как связаны фазы фотосинтеза?");
    await page.getByRole("button", { name: "Материалы", exact: true }).click();
    await expect(
        page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    title = "Обновлённая версия";
    await page
        .getByRole("button", { name: "Обновить материалы", exact: true })
        .click();
    await expect(
        page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    enabled = false;
    await page.getByRole("button", { name: "Чат", exact: true }).click();
    await expect(consent).toHaveCount(0);
    await expect(
        page.getByRole("textbox", { name: "Ваш вопрос", exact: true }),
    ).toHaveValue("Как связаны фазы фотосинтеза?");
    await page.getByRole("button", { name: "Материалы", exact: true }).click();
    enabled = true;
    await page.getByRole("button", { name: "Чат", exact: true }).click();
    await expect(consent).not.toBeChecked();
    await page.getByRole("button", { name: "Материалы", exact: true }).click();
    unavailable = true;
    await page.getByRole("button", { name: "Чат", exact: true }).click();
    await expect(
        page.getByRole("button", { name: "Отправить", exact: true }),
    ).toBeDisabled();
    await expect(
        page
            .getByRole("alert")
            .filter({ hasText: "Не удалось обновить настройки курса" }),
    ).toBeVisible();
    unavailable = false;
    await page
        .getByRole("button", { name: "Загрузить настройки повторно" })
        .click();
    await expect(consent).not.toBeChecked();
    await expect(
        page.getByRole("button", { name: "Отправить", exact: true }),
    ).toBeEnabled();
});

test("reading context, learning attempts, consent and private notes", async ({
    page,
}, info) => {
    page.on("pageerror", (error) => {
        throw error;
    });
    await page.addInitScript(() =>
        sessionStorage.setItem("canvas_portal_token", "workspace-test"),
    );
    const citation = {
        document_id: 1,
        chunk_id: 11,
        title: "Глава 1",
        quote: "Хлорофилл поглощает свет.",
        page: 2,
    };
    let requests: any[] = [];
    let attempts = 0;
    let interruptAttempt = true;
    const exercise = () => ({
        id: "exercise",
        question: "Что поглощает хлорофилл?",
        attempts,
        correct: attempts > 1,
        feedback: attempts ? "Попробуйте ещё раз" : null,
        hint: attempts ? "Вспомните источник энергии" : null,
        can_reveal: attempts >= 2,
        citations: [citation],
    });
    await page.route("**/api-proxy/portal/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith("/attempt") && interruptAttempt) {
            interruptAttempt = false;
            return route.abort("failed");
        }
        const data = path.endsWith("/session")
            ? {
                  title: "Биология",
                  role: "student",
                  storage_scope: "learner-course-one",
              }
            : path.endsWith("/preferences")
              ? {
                    quality_enabled: true,
                    allow_solutions: true,
                    solution_after_attempts: 2,
                }
              : path.endsWith("/materials")
                ? [
                      {
                          document_id: 1,
                          title: "Глава 1",
                          published: true,
                          kind: "literature",
                      },
                  ]
                : path.endsWith("/materials/1")
                  ? {
                        title: "Глава 1",
                        document_id: 1,
                        published: true,
                        chunks: [{ id: 11, text: citation.quote, page: 2 }],
                    }
                  : path.endsWith("/study")
                    ? exercise()
                    : path.endsWith("/attempt")
                      ? (++attempts, exercise())
                      : path.endsWith("/solution")
                        ? {
                              answer: "Свет",
                              explanation: "Хлорофилл поглощает свет.",
                          }
                        : { saved: true };
        if (path.endsWith("/chat/stream")) {
            requests.push(route.request().postDataJSON());
            return route.fulfill({
                contentType: "application/x-ndjson",
                body:
                    JSON.stringify({
                        event: "result",
                        result: {
                            answer: "Хлорофилл поглощает энергию света.",
                            citations: [citation],
                        },
                    }) + "\n",
            });
        }
        return route.fulfill({ json: data });
    });
    await page.goto("/portal");
    await expect(page.getByLabel("Добавлять мои вопросы")).not.toBeChecked();
    await page.getByRole("button", { name: "Материалы", exact: true }).click();
    await page.getByRole("button", { name: "Читать", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Разобрать фрагмент" }).click();
    await dialog
        .getByRole("button", { name: "Объяснить", exact: true })
        .click();
    await dialog
        .getByRole("button", { name: "Отправить", exact: true })
        .click();
    await expect(dialog.getByRole("log")).toContainText(
        "Хлорофилл поглощает энергию света.",
    );
    expect(requests[0].context).toEqual({
        document_id: 1,
        chunk_id: 11,
        quote: citation.quote,
    });
    expect(requests[0].share_for_review).toBe(false);
    await dialog.getByRole("button", { name: "Проверь понимание" }).click();
    await expect(
        dialog.getByRole("region", { name: "Учебное упражнение" }),
    ).toBeVisible();
    await expect(
        dialog.getByRole("button", { name: "Показать решение" }),
    ).toHaveCount(0);
    await dialog.getByLabel("Ваш ответ", { exact: true }).fill("Воду");
    await dialog
        .getByRole("button", { name: "Проверить ответ", exact: true })
        .click();
    await expect(
        dialog
            .getByRole("region", { name: "Учебное упражнение" })
            .getByRole("alert"),
    ).toContainText("Нет связи с сервисом");
    await expect(dialog.getByLabel("Ваш ответ", { exact: true })).toHaveValue(
        "Воду",
    );
    expect(attempts).toBe(0);
    await dialog
        .getByRole("button", { name: "Проверить ответ", exact: true })
        .click();
    await expect(
        dialog
            .getByRole("region", { name: "Учебное упражнение" })
            .getByRole("alert"),
    ).toHaveCount(0);
    await expect(dialog.getByText("Вспомните источник энергии")).toBeVisible();
    await expect(
        dialog.getByRole("button", { name: "Показать решение" }),
    ).toHaveCount(0);
    await dialog.getByLabel("Ваш ответ", { exact: true }).fill("Свет");
    await dialog
        .getByRole("button", { name: "Проверить ответ", exact: true })
        .click();
    await dialog.getByRole("button", { name: "Показать решение" }).click();
    await expect(
        dialog.getByRole("heading", { name: "Разбор решения" }),
    ).toBeVisible();
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
    await page.screenshot({
        path: info.outputPath("material-practice.png"),
        fullPage: true,
    });
    await dialog.getByText("Моя история и заметки", { exact: true }).click();
    await dialog.getByLabel("Сохранять на этом устройстве").check();
    await dialog
        .getByLabel("Мои заметки", { exact: true })
        .fill("Свет — источник энергии.");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Читать", exact: true }).click();
    await dialog.getByText("Моя история и заметки", { exact: true }).click();
    await expect(dialog.getByLabel("Мои заметки", { exact: true })).toHaveValue(
        "Свет — источник энергии.",
    );
    const stored = await page.evaluate(() =>
        localStorage.getItem("course-workspace:learner-course-one:1"),
    );
    expect(stored).not.toContain("workspace-test");
    await dialog
        .getByRole("button", { name: "Удалить историю и заметки" })
        .click();
    expect(
        await page.evaluate(() =>
            localStorage.getItem("course-workspace:learner-course-one:1"),
        ),
    ).toBeNull();
});

test("stopping a stream keeps the question and discards the draft", async ({
    page,
}) => {
    page.on("pageerror", (error) => {
        throw error;
    });
    await page.addInitScript(() =>
        sessionStorage.setItem("canvas_portal_token", "workspace-test"),
    );
    await page.route("**/api-proxy/portal/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith("/chat/stream")) {
            await new Promise((resolve) => setTimeout(resolve, 1500));
            return route
                .fulfill({
                    contentType: "application/x-ndjson",
                    body:
                        JSON.stringify({
                            event: "result",
                            result: { answer: "Поздний ответ", citations: [] },
                        }) + "\n",
                })
                .catch(() => {});
        }
        return route.fulfill({
            json: path.endsWith("/session")
                ? { title: "Курс", role: "student" }
                : path.endsWith("/preferences")
                  ? { quality_enabled: false }
                  : [],
        });
    });
    await page.goto("/portal");
    await page.getByLabel("Ваш вопрос").fill("Объясни тему");
    await page.getByRole("button", { name: "Отправить", exact: true }).click();
    await page.getByRole("button", { name: "Остановить ответ" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText(
        "Ответ остановлен",
    );
    await expect(page.getByLabel("Ваш вопрос")).toHaveValue("Объясни тему");
    await expect(page.getByRole("log")).not.toContainText("Поздний ответ");
});

test("teacher quality console saves policy and resolves reviews at narrow widths", async ({
    page,
}, info) => {
    await page.addInitScript(() =>
        sessionStorage.setItem("canvas_portal_token", "teacher-workspace"),
    );
    let policy = {
        quality_enabled: true,
        allow_solutions: false,
        solution_after_attempts: 2,
    };
    let resolved = false;
    await page.route("**/api-proxy/portal/**", async (route) => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        if (path.endsWith("/preferences")) {
            if (route.request().method() === "PUT")
                policy = route.request().postDataJSON();
            return route.fulfill({ json: policy });
        }
        if (path.endsWith("/quality/entry")) {
            resolved = true;
            return route.fulfill({ json: { saved: true } });
        }
        if (path.endsWith("/quality"))
            return route.fulfill({
                json: {
                    entries: resolved
                        ? []
                        : [
                              {
                                  id: "entry",
                                  day: "2026-09-19",
                                  question:
                                      "[имя]: почему растениям нужен свет?",
                                  answer: "Хлорофилл поглощает энергию света.",
                                  document_ids: [],
                                  feedback: "unclear",
                                  status: "open",
                              },
                          ],
                    has_more: false,
                },
            });
        return route.fulfill({
            json: path.endsWith("/session")
                ? { title: "Биология", role: "teacher" }
                : [],
        });
    });
    await page.goto("/portal");
    await expect(page.getByLabel("Добавлять мои вопросы")).toHaveCount(0);
    await page
        .getByRole("button", { name: "Качество ответов", exact: true })
        .click();
    await page.getByLabel("Разрешить готовые решения").check();
    await page.getByLabel("Открывать решение после попыток").selectOption("3");
    await page.getByRole("button", { name: "Сохранить настройки" }).click();
    await expect(
        page.getByRole("status").filter({ hasText: "Настройки сохранены" }),
    ).toBeVisible();
    expect(policy.solution_after_attempts).toBe(3);
    await page.getByText("Ответ помощника", { exact: true }).click();
    for (const width of [320, 390, 768, 1440]) {
        await page.setViewportSize({ width, height: 900 });
        expect(
            await page.evaluate(
                () => document.documentElement.scrollWidth <= innerWidth,
            ),
        ).toBe(true);
    }
    await page.setViewportSize({
        width: info.project.name === "mobile" ? 390 : 1280,
        height: 900,
    });
    await page
        .getByRole("heading", { name: "Журнал качества" })
        .scrollIntoViewIfNeeded();
    await page.screenshot({
        path: info.outputPath("quality-console.png"),
        fullPage: false,
    });
    await page.getByRole("button", { name: "Отметить просмотренным" }).click();
    await expect(
        page.getByText("В этом разделе пока нет записей."),
    ).toBeVisible();
});
