import { expect, test } from "@playwright/test";

test("student can ask with citations and leave a separate review", async ({
    page,
}, testInfo) => {
    await page.addInitScript(() =>
        sessionStorage.setItem("canvas_portal_token", "synthetic-test-session"),
    );
    let feedback: unknown;
    await page.route("**/api-proxy/portal/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        let body: unknown;
        if (path.endsWith("/session"))
            body = { title: "Биология · Фотосинтез", role: "student" };
        else if (path.endsWith("/chat"))
            body = {
                answer: "Растения используют энергию света.",
                citations: [
                    {
                        document_id: 1,
                        chunk_id: 1,
                        title: "Введение",
                        quote: "Фотосинтез преобразует энергию света.",
                    },
                ],
            };
        else if (path.endsWith("/feedback")) {
            feedback = route.request().postDataJSON();
            body = { saved: true };
        } else if (path.endsWith("/materials/1"))
            body = {
                title: "Введение",
                chunks: [
                    { id: 1, text: "Фотосинтез преобразует энергию света." },
                ],
            };
        else
            body = [
                {
                    document_id: 1,
                    title: "Введение",
                    published: true,
                    kind: "literature",
                },
            ];
        await route.fulfill({ json: body });
    });
    await page.goto("/portal");
    await expect(
        page.getByRole("heading", { name: "Биология · Фотосинтез" }),
    ).toBeVisible();
    await expect(
        page.getByRole("button", { name: "Анализ курса", exact: true }),
    ).toHaveCount(0);
    await page
        .getByRole("button", { name: "Объясни основную идею темы" })
        .click();
    await expect(page.getByLabel("Ваш вопрос")).toBeFocused();
    await expect(page.getByLabel("Ваш вопрос")).toHaveValue(
        "Объясни основную идею темы",
    );
    await page.getByLabel("Ваш вопрос").fill("Что такое фотосинтез?");
    await page.getByRole("button", { name: "Отправить", exact: true }).click();
    await expect(
        page.getByText("Растения используют энергию света."),
    ).toBeVisible();
    await page.getByText("Источник: Введение").click();
    await expect(
        page.getByText("Фотосинтез преобразует энергию света."),
    ).toBeVisible();
    if (testInfo.project.name === "mobile") {
        await page.mouse.wheel(0, 500);
        await expect
            .poll(() => page.evaluate(() => window.scrollY))
            .toBeGreaterThan(0);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
        path: testInfo.outputPath("chat.png"),
        fullPage: true,
    });
    await page.getByRole("button", { name: "Материалы", exact: true }).click();
    await expect(
        page.getByText("Добавить литературу", { exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Читать", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Введение" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(
        page.getByRole("button", { name: "Читать", exact: true }),
    ).toBeFocused();
    await page.getByRole("button", { name: "Оставить отзыв" }).click();
    await page.keyboard.press("Shift+Tab");
    await expect(
        page.getByRole("button", { name: "Отмена", exact: true }),
    ).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(
        page.getByRole("combobox", { name: "Оценка", exact: true }),
    ).toBeFocused();
    await page
        .getByRole("combobox", { name: "Оценка", exact: true })
        .selectOption("difficult");
    await page.getByRole("button", { name: "Отправить отзыв" }).click();
    await expect(
        page.getByRole("status").filter({ hasText: "Спасибо!" }),
    ).toContainText("Отзыв сохранён");
    expect(feedback).toEqual({ rating: "difficult", comment: "" });
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
});

test("teacher sees publication controls and analysis", async ({
    page,
}, testInfo) => {
    await page.addInitScript(() =>
        sessionStorage.setItem("canvas_portal_token", "synthetic-test-session"),
    );
    let published = false;
    await page.route("**/api-proxy/portal/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        let body: unknown;
        if (path.endsWith("/session"))
            body = { title: "Курс преподавателя", role: "teacher" };
        else if (route.request().method() === "PATCH") {
            published = route.request().postDataJSON().published;
            body = { published };
        } else if (path.endsWith("/analysis"))
            body = {
                distribution: { understand: 3 },
                chunks_analyzed: 3,
                limit: 500,
                note: "Предварительный анализ",
                examples: [],
            };
        else
            body = [
                {
                    document_id: 1,
                    title: "Литература",
                    published,
                    kind: "literature",
                },
            ];
        await route.fulfill({ json: body });
    });
    await page.goto("/portal");
    await page.getByRole("button", { name: "Материалы", exact: true }).click();
    await page.getByLabel("Поиск по названию").fill("нет такого");
    await expect(
        page.getByText("Ничего не найдено.", { exact: false }),
    ).toBeVisible();
    await page.getByLabel("Поиск по названию").fill("литература");
    await expect(
        page.getByRole("heading", { name: "Литература", exact: true }),
    ).toBeVisible();
    await page
        .getByLabel("Публикация", { exact: true })
        .selectOption("published");
    await expect(
        page.getByRole("button", { name: "Опубликовать для всех" }),
    ).toHaveCount(0);
    await page.getByLabel("Публикация", { exact: true }).selectOption("all");
    await page.screenshot({
        path: testInfo.outputPath("library.png"),
        fullPage: true,
    });
    await page.getByRole("button", { name: "Опубликовать для всех" }).click();
    await expect(
        page.getByRole("button", { name: "Скрыть", exact: true }),
    ).toBeVisible();
    expect(published).toBe(true);
    await page
        .getByRole("button", { name: "Анализ курса", exact: true })
        .click();
    await expect(page.getByText("Предварительный анализ")).toBeVisible();
});

test("expired session clears access and prompts Canvas launch", async ({
    page,
}) => {
    await page.addInitScript(() =>
        sessionStorage.setItem("canvas_portal_token", "expired-test-session"),
    );
    await page.route("**/api-proxy/portal/**", (route) =>
        route.fulfill({ status: 401, json: { detail: "expired" } }),
    );
    await page.goto("/portal");
    await expect(page.getByRole("main").getByRole("alert")).toContainText(
        "Сессия завершилась",
    );
    await expect(
        page.getByRole("heading", { name: "Войдите через Canvas" }),
    ).toBeVisible();
    expect(
        await page.evaluate(() =>
            sessionStorage.getItem("canvas_portal_token"),
        ),
    ).toBeNull();
});
