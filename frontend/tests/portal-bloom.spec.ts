import { expect, test } from "@playwright/test";

test("teacher sees evidence, abstention and research references without invented confidence", async ({
    page,
}) => {
    await page.addInitScript(() =>
        sessionStorage.setItem("canvas_portal_token", "bloom-test"),
    );
    await page.route("**/api-proxy/portal/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        const data = path.endsWith("/session")
            ? { title: "Биология", role: "teacher" }
            : path.endsWith("/preferences")
              ? { quality_enabled: false }
              : path.endsWith("/materials")
                ? []
                : path.endsWith("/analysis")
                  ? {
                        distribution: { apply: 1 },
                        knowledge_distribution: { conceptual: 1 },
                        statuses: {
                            proposed: 0,
                            partial: 1,
                            needs_review: 0,
                            no_task: 1,
                        },
                        note: "Предварительная рубрика; точность ещё не валидирована.",
                        rubric_version: "rbt-context-1.0",
                        chunks_analyzed: 2,
                        limit: 500,
                        examples_limit: 30,
                        references: [
                            {
                                id: "krathwohl2002",
                                title: "Krathwohl (2002): пересмотренная таксономия",
                                url: "https://doi.org/10.1207/s15430421tip4104_2",
                            },
                        ],
                        examples: [
                            {
                                document_id: 1,
                                chunk_id: 11,
                                title: "Задания",
                                text: "Создайте модель клетки по готовому образцу.",
                                levels: ["apply"],
                                status: "partial",
                                rationale: "Требуется проверка преподавателя.",
                                evidence: [
                                    {
                                        quote: "Создайте модель клетки по готовому образцу.",
                                        action: "создать",
                                        object: "модель клетки по готовому образцу",
                                        level: "apply",
                                        rule_id: "execute_template",
                                        rationale:
                                            "По готовому образцу, без нового замысла.",
                                        knowledge: ["conceptual"],
                                        knowledge_evidence: {
                                            conceptual: "модель",
                                        },
                                    },
                                ],
                            },
                            {
                                document_id: 2,
                                chunk_id: 12,
                                title: "Описание процесса",
                                text: "Световая фаза образует АТФ.",
                                levels: [],
                                status: "no_task",
                                evidence: [],
                                rationale:
                                    "Из описания темы нельзя вывести учебное действие.",
                            },
                        ],
                    }
                  : {
                        document_id: 1,
                        title: "Задания",
                        published: false,
                        chunks: [
                            {
                                id: 11,
                                text: "Создайте модель клетки по готовому образцу.",
                            },
                        ],
                    };
        await route.fulfill({ json: data });
    });
    await page.goto("/portal");
    await page
        .getByRole("button", { name: "Анализ курса", exact: true })
        .click();
    await expect(page.getByRole("status")).toContainText(
        "Без распознанного задания: 1",
    );
    await page.getByText("Задания · Применить", { exact: true }).click();
    await expect(
        page.getByText("Правило: execute_template.", { exact: false }),
    ).toBeVisible();
    await page
        .getByText("Описание процесса · Явное задание не распознано", {
            exact: true,
        })
        .click();
    await expect(
        page.getByText("Из описания темы нельзя вывести учебное действие.", {
            exact: true,
        }),
    ).toBeVisible();
    await page
        .getByText("Научная основа и ограничения", { exact: true })
        .click();
    await expect(page.getByRole("link", { name: /Krathwohl/ })).toHaveAttribute(
        "href",
        "https://doi.org/10.1207/s15430421tip4104_2",
    );
    for (const width of [320, 390, 768, 1440]) {
        await page.setViewportSize({ width, height: 900 });
        expect(
            await page.evaluate(
                () => document.documentElement.scrollWidth <= innerWidth,
            ),
        ).toBe(true);
    }
    await page
        .getByRole("button", { name: "Открыть контекст в материале" })
        .first()
        .click();
    await expect(page.getByRole("dialog")).toContainText(
        "Создайте модель клетки по готовому образцу.",
    );
});
