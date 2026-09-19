import { fulfillPortal } from "./portal-fixture";
import { expect, test, Page } from "@playwright/test";

async function course(page: Page, role = "teacher") {
    await page.addInitScript(() =>
        sessionStorage.setItem("canvas_portal_token", "synthetic-ux-audit"),
    );
    let materials = [
        {
            document_id: 1,
            title: "Фотосинтез: световая и темновая фазы",
            published: true,
            kind: "literature",
        },
        {
            document_id: 2,
            title: "Рекомендованная_литература_".repeat(8),
            published: false,
            kind: "literature",
        },
    ];
    const calls: string[] = [];
    await page.route("**/api-proxy/portal/**", async (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path.endsWith("/preferences")) return route.fulfill({ json: { quality_enabled: false, allow_solutions: false, solution_after_attempts: 2 } });
        if (path.endsWith("/imports/latest")) return route.fulfill({ json: materials.some(m => m.document_id === 4) ? { id: "job", status: "complete", progress: 1, total: 1, details: [] } : null });
        calls.push(`${request.method()} ${path}`);
        let body: unknown;
        if (path.endsWith("/session"))
            body = {
                title: "Биология · Процессы жизнедеятельности растений",
                role,
            };
        else if (path.endsWith("/analysis"))
            body = {
                distribution: { understand: 8, analyze: 3, apply: 2 },
                chunks_analyzed: 10,
                limit: 500,
                note: "Предварительная классификация по глаголам; требует проверки преподавателем.",
                examples: [
                    {
                        document_id: 1,
                        title: materials[0].title,
                        text: "Объясните, какую роль играет свет в фотосинтезе.",
                        levels: ["understand"],
                    },
                ],
            };
        else if (path.endsWith("/summary"))
            body = {
                metrics: {
                    questions: 18,
                    answers_with_sources: 15,
                    no_context: 2,
                    errors: 1,
                },
                feedback: [
                    { title: materials[0].title, rating: "clear", count: 8 },
                    {
                        title: materials[1]?.title || "Источник",
                        rating: "difficult",
                        count: null,
                    },
                ],
            };
        else if (path.endsWith("/imports")) {
            materials.push({
                document_id: 4,
                title: "Страница из Canvas",
                published: false,
                kind: "canvas_page",
            });
            body = { id: "job" };
        } else if (path.endsWith("/feedback")) body = { saved: true };
        else if (path.endsWith("/materials") && request.method() === "POST") {
            expect(request.headers()["content-type"]).toContain(
                "multipart/form-data",
            );
            materials.push({
                document_id: 3,
                title: "chapter.md",
                published: false,
                kind: "literature",
            });
            body = { document_id: 3 };
        } else if (request.method() === "DELETE") {
            const id = Number(path.split("/").pop());
            materials = materials.filter((m) => m.document_id !== id);
            body = { deleted: true };
        } else if (request.method() === "PATCH") {
            const id = Number(path.split("/").pop());
            materials = materials.map((m) =>
                m.document_id === id
                    ? { ...m, published: request.postDataJSON().published }
                    : m,
            );
            body = { published: request.postDataJSON().published };
        } else if (/\/materials\/\d+$/.test(path))
            body = {
                title: materials[0].title,
                chunks: [
                    {
                        id: 1,
                        text: "Фотосинтез превращает энергию света в энергию органических веществ. ".repeat(
                            30,
                        ),
                    },
                ],
            };
        else
            body =
                role === "teacher"
                    ? materials
                    : materials.filter((m) => m.published);
        await fulfillPortal(route, { json: body });
    });
    await page.goto("/portal");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
        "Биология",
    );
    return calls;
}

async function fits(page: Page) {
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
    const overflow = await page
        .locator(
            "main button:visible, main input:visible, main textarea:visible, main select:visible",
        )
        .evaluateAll((elements) =>
            elements
                .filter((el) => {
                    const r = el.getBoundingClientRect();
                    return (
                        r.left < -1 ||
                        r.right > innerWidth + 1 ||
                        (el instanceof HTMLButtonElement &&
                            el.scrollWidth > el.clientWidth + 2)
                    );
                })
                .map((el) => el.textContent?.slice(0, 60)),
        );
    expect(overflow).toEqual([]);
}

test("teacher can upload import hide and delete materials", async ({
    page,
}) => {
    const calls = await course(page);
    await page.getByRole("button", { name: "Материалы", exact: true }).click();
    await page.getByText("Добавить материалы в курс", { exact: true }).click();
    await page
        .getByLabel("Добавить литературу")
        .setInputFiles({
            name: "chapter.md",
            mimeType: "text/markdown",
            buffer: Buffer.from("Объясните фотосинтез."),
        });
    await expect(
        page.getByRole("heading", { name: "chapter.md" }),
    ).toBeVisible();
    await page
        .getByRole("button", { name: "Импортировать курс Canvas" })
        .click();
    await expect(
        page.getByRole("heading", { name: "Страница из Canvas" }),
    ).toBeVisible();
    const first = page
        .locator("article")
        .filter({
            has: page.getByRole("heading", {
                name: "Фотосинтез: световая и темновая фазы",
                exact: true,
            }),
        });
    await first.getByRole("button", { name: "Скрыть", exact: true }).click();
    await expect(first).toContainText("Черновик");
    page.once("dialog", (d) => d.accept());
    await first.getByRole("button", { name: "Удалить" }).click();
    await expect(first).toHaveCount(0);
    expect(calls).toContain("DELETE /api-proxy/portal/materials/1");
    await fits(page);
});

test("all teacher views fit narrow tablet and desktop widths", async ({
    page,
}, testInfo) => {
    await course(page);
    const widths =
        testInfo.project.name === "desktop" ? [768, 1440] : [320, 390];
    for (const width of widths) {
        await page.setViewportSize({ width, height: 900 });
        for (const name of [
            "Чат",
            "Материалы",
            "Анализ курса",
            "Обратная связь",
        ]) {
            await page
                .getByRole("navigation")
                .getByRole("button", { name, exact: true })
                .click();
            if (name === "Анализ курса")
                await expect(
                    page.getByText("Примеры для проверки", { exact: true }),
                ).toBeVisible();
            if (name === "Обратная связь")
                await expect(
                    page.getByText("менее 5", { exact: false }).last(),
                ).toBeVisible();
            await fits(page);
            await page.screenshot({
                path: testInfo.outputPath(`${width}-${name}.png`),
                fullPage: true,
            });
        }
    }
});

test("long answers allow follow-up and failed questions can be retried", async ({
    page,
}) => {
    await course(page, "student");
    let requests = 0;
    await page.route("**/api-proxy/portal/chat/stream", async (route) => {
        requests++;
        const payload = route.request().postDataJSON();
        expect(
            payload.history.every(
                (m: { content: string }) => m.content.length <= 4000,
            ),
        ).toBe(true);
        if (requests === 2)
            return fulfillPortal(route, {
                status: 502,
                json: { detail: "Модель временно недоступна" },
            });
        if (requests === 3) expect(payload.history).toHaveLength(2);
        await fulfillPortal(route, {
            json: {
                answer:
                    requests === 1
                        ? "Объяснение ".repeat(500)
                        : "Повторный запрос выполнен",
                citations: [],
            },
        });
    });
    await page.getByLabel("Ваш вопрос").fill("Объясни фотосинтез");
    await page.getByRole("button", { name: "Отправить", exact: true }).click();
    await expect(page.getByRole("log")).toContainText("Объяснение");
    await page.getByLabel("Ваш вопрос").fill("Приведи пример");
    await page.getByRole("button", { name: "Отправить", exact: true }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText(
        "Модель временно недоступна",
    );
    await expect(page.getByLabel("Ваш вопрос")).toHaveValue("Приведи пример");
    await expect(page.getByRole("main").getByRole("alert")).toBeInViewport();
    await page.getByRole("button", { name: "Повторить вопрос", exact: true }).click();
    await expect(page.getByRole("log")).toContainText(
        "Повторный запрос выполнен",
    );
    await fits(page);
});

test("feedback failure stays in dialog and can be retried", async ({
    page,
}, testInfo) => {
    await course(page, "student");
    let attempts = 0;
    await page.route("**/feedback", (route) =>
        ++attempts === 1
            ? fulfillPortal(route, { status: 429, json: { detail: "Hourly limit" } })
            : fulfillPortal(route, { json: { saved: true } }),
    );
    await page.getByRole("button", { name: "Материалы", exact: true }).click();
    await page.getByRole("button", { name: "Оставить отзыв" }).click();
    await page
        .getByLabel("Комментарий (необязательно)")
        .fill("Не хватает примера.");
    await page.getByRole("button", { name: "Отправить отзыв" }).click();
    await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
        "часовой лимит",
    );
    await expect(page.getByLabel("Комментарий (необязательно)")).toHaveValue(
        "Не хватает примера.",
    );
    await fits(page);
    await page.screenshot({
        path: testInfo.outputPath("feedback-dialog.png"),
        fullPage: true,
    });
    await page.getByRole("button", { name: "Отправить отзыв" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
});
