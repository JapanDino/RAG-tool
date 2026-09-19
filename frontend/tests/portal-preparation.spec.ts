import { expect, test } from "@playwright/test";

test("teacher reviews draft, readiness and persists a distinct Bloom correction", async ({
    page,
}) => {
    await page.addInitScript(() =>
        sessionStorage.setItem("canvas_portal_token", "preparation-test"),
    );
    let review: any = null;
    let checked = false;
    let payload: any;
    const citation = {
        document_id: 1,
        chunk_id: 11,
        title: "Черновик темы",
        quote: "Создайте модель клетки по готовому образцу.",
    };
    await page.route("**/api-proxy/portal/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith("/chat/stream")) {
            payload = route.request().postDataJSON();
            checked = true;
            return route.fulfill({
                contentType: "application/x-ndjson",
                body:
                    JSON.stringify({
                        event: "result",
                        result: {
                            answer: "Разбор по черновику.",
                            citations: [citation],
                        },
                    }) + "\n",
            });
        }
        if (path.endsWith("/review")) {
            review = {
                ...route.request().postDataJSON(),
                revision: 1,
                updated_at: "2026-09-19T15:00:00Z",
            };
            return route.fulfill({ json: review });
        }
        const data = path.endsWith("/session")
            ? {
                  title: "Биология",
                  role: "teacher",
                  storage_scope: "teacher-preparation",
              }
            : path.endsWith("/preferences")
              ? { quality_enabled: false }
              : path.endsWith("/materials")
                ? [
                      {
                          document_id: 1,
                          title: "Черновик темы",
                          published: false,
                          kind: "literature",
                      },
                  ]
                : path.endsWith("/materials/1")
                  ? {
                        document_id: 1,
                        title: "Черновик темы",
                        published: false,
                        chunks: [{ id: 11, text: citation.quote }],
                    }
                  : path.endsWith("/readiness")
                    ? {
                          counts: {
                              total: 1,
                              published: 0,
                              drafts: 1,
                              problems: 0,
                              preview_checked: checked ? 1 : 0,
                          },
                          note: "Проверка чата не подтверждает правильность ответа.",
                          last_import: null,
                          materials: [
                              {
                                  document_id: 1,
                                  title: "Черновик темы",
                                  published: false,
                                  chunks: 1,
                                  indexed: 1,
                                  problems: [],
                                  preview_checked: checked,
                              },
                          ],
                      }
                    : path.endsWith("/analysis")
                      ? {
                            distribution: { apply: 1 },
                            statuses: { proposed: 1 },
                            note: "Предварительная разметка",
                            chunks_analyzed: 1,
                            limit: 500,
                            examples: [
                                {
                                    document_id: 1,
                                    chunk_id: 11,
                                    text_hash: "a".repeat(64),
                                    title: "Черновик темы",
                                    text: citation.quote,
                                    levels: ["apply"],
                                    knowledge: ["conceptual"],
                                    status: "proposed",
                                    evidence: [],
                                    review,
                                },
                            ],
                        }
                      : null;
        return route.fulfill({ json: data });
    });
    await page.goto("/portal");
    await page
        .getByRole("button", { name: "Готовность курса", exact: true })
        .click();
    await expect(
        page.getByText(
            "По текущей версии ещё нет успешной проверки чата преподавателем.",
        ),
    ).toBeVisible();
    await page
        .getByRole("button", { name: "Проверить материал и чат" })
        .click();
    const dialog = page.getByRole("dialog");
    await expect(
        dialog.getByText("Проверка преподавателя.", { exact: false }),
    ).toBeVisible();
    await expect(
        dialog.getByRole("button", { name: "Проверь понимание" }),
    ).toHaveCount(0);
    await dialog
        .getByRole("textbox", { name: "Ваш вопрос", exact: true })
        .fill("Как выполнить задание?");
    await dialog
        .getByRole("button", { name: "Отправить", exact: true })
        .click();
    await expect(
        dialog.getByText("Разбор по черновику.", { exact: true }),
    ).toBeVisible();
    expect(payload.preview).toBe(true);
    expect(payload.context.document_id).toBe(1);
    expect(payload.share_for_review).toBe(false);
    await dialog.getByRole("button", { name: "Закрыть материал" }).click();
    await page.getByRole("button", { name: "Обновить проверку" }).click();
    await expect(
        page.getByText(
            "Проверка чата: получен ответ с источниками по текущей версии.",
        ),
    ).toBeVisible();
    await page
        .getByRole("button", { name: "Анализ курса", exact: true })
        .click();
    await page.getByText("Черновик темы · Применить", { exact: true }).click();
    await page.getByLabel("Решение", { exact: true }).selectOption("corrected");
    await page
        .getByRole("checkbox", { name: "Применить", exact: true })
        .uncheck();
    await page.getByRole("checkbox", { name: "Понять", exact: true }).check();
    await page
        .getByLabel("Обоснование преподавателя")
        .fill("Здесь ученик объясняет уже готовую модель.");
    await page.getByRole("button", { name: "Сохранить разметку" }).click();
    await expect(
        page.getByText(
            "Разметка сохранена. Автоматический результат сохранён отдельно.",
        ),
    ).toBeVisible();
    expect(review.levels).toEqual(["understand"]);
    await page.reload();
    await page
        .getByRole("button", { name: "Анализ курса", exact: true })
        .click();
    await page.getByText("Черновик темы · Применить", { exact: true }).click();
    await expect(
        page.getByRole("checkbox", { name: "Понять", exact: true }),
    ).toBeChecked();
    await expect(page.getByLabel("Обоснование преподавателя")).toHaveValue(
        "Здесь ученик объясняет уже готовую модель.",
    );
    for (const width of [320, 390, 768, 1440]) {
        await page.setViewportSize({ width, height: 900 });
        expect(
            await page.evaluate(
                () => document.documentElement.scrollWidth <= window.innerWidth,
            ),
        ).toBe(true);
    }
});

test("learner resumes a saved draft and finishes three questions after reload", async ({
    page,
}) => {
    await page.addInitScript(() =>
        sessionStorage.setItem("canvas_portal_token", "study-resume-test"),
    );
    let state: any = null;
    const exercise = (number = 1) => ({
        id: "session1",
        topic: "Фотосинтез",
        question: `Вопрос ${number}: откуда энергия?`,
        question_number: number,
        total_questions: 3,
        attempts: 0,
        draft_answer: "",
        correct: false,
        can_reveal: false,
        history: [],
        citations: [],
    });
    await page.route("**/api-proxy/portal/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith("/study")) state = exercise();
        if (path.endsWith("/draft")) {
            state.draft_answer = route.request().postDataJSON().answer;
            return route.fulfill({ json: { saved: true } });
        }
        if (path.endsWith("/attempt"))
            state = {
                ...state,
                attempts: state.attempts + 1,
                correct: true,
                feedback: "Верно",
                draft_answer: route.request().postDataJSON().answer,
            };
        if (path.endsWith("/next")) {
            const history = [
                ...state.history,
                {
                    question: state.question,
                    correct: state.correct,
                    attempts: state.attempts,
                },
            ];
            state =
                state.question_number === 3
                    ? { ...state, completed: true, history }
                    : { ...exercise(state.question_number + 1), history };
        }
        const data = path.endsWith("/session")
            ? {
                  title: "Биология",
                  role: "student",
                  storage_scope: "resume-one",
              }
            : path.endsWith("/preferences")
              ? { quality_enabled: false }
              : path.endsWith("/materials")
                ? []
                : state;
        return route.fulfill({ json: data });
    });
    await page.goto("/portal");
    await expect(
        page.getByRole("button", { name: "Готовность курса", exact: true }),
    ).toHaveCount(0);
    await page
        .getByRole("textbox", { name: "Ваш вопрос", exact: true })
        .fill("Фотосинтез");
    await page.getByRole("button", { name: "Проверь понимание" }).click();
    await page
        .getByRole("textbox", { name: "Ваш ответ", exact: true })
        .fill("Энергия света");
    await expect(page.getByText("Черновик ответа сохранён")).toBeVisible();
    await page.reload();
    await page.getByRole("button", { name: "Продолжить тренировку" }).click();
    await expect(
        page.getByRole("textbox", { name: "Ваш ответ", exact: true }),
    ).toHaveValue("Энергия света");
    await expect(
        page.getByRole("button", { name: "Показать решение" }),
    ).toHaveCount(0);
    for (let number = 1; number <= 3; number++) {
        await expect(
            page.getByText(`Вопрос ${number} из 3`, { exact: true }),
        ).toBeVisible();
        await page
            .getByRole("textbox", { name: "Ваш ответ", exact: true })
            .fill("Энергия света");
        await page
            .getByRole("button", { name: "Проверить ответ", exact: true })
            .click();
        await expect(page.getByText("Черновик ответа сохранён")).toBeVisible();
        await expect(page.getByText("Сохраняем ответ…")).toHaveCount(0);
        await page
            .getByRole("button", {
                name:
                    number === 3 ? "Завершить тренировку" : "Следующий вопрос",
                exact: true,
            })
            .click();
    }
    await expect(
        page.getByText("Тренировка завершена", { exact: true }),
    ).toBeVisible();
    await expect(
        page.getByRole("textbox", { name: "Ваш ответ", exact: true }),
    ).toHaveCount(0);
    await page.reload();
    await page.getByRole("button", { name: "Открыть результат" }).click();
    await expect(
        page.getByText("Тренировка завершена", { exact: true }),
    ).toBeVisible();
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
    ).toBe(true);
});
