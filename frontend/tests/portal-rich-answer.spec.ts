import { fulfillPortal } from "./portal-fixture";
import { expect, test } from "@playwright/test";

test("structured explanations, source-linked diagrams and follow-up controls", async ({ page }, testInfo) => {
    await page.addInitScript(() => sessionStorage.setItem("canvas_portal_token", "synthetic-rich-session"));
    const requests: { message: string; history: { content: string }[]; response_style: string }[] = [];
    const title = "Учебная страница Canvas";
    await page.route("**/api-proxy/portal/**", async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith("/preferences")) return route.fulfill({ json: { quality_enabled: false, allow_solutions: false, solution_after_attempts: 2 } });
        if (path.endsWith("/imports/latest")) return route.fulfill({ json: null });
        if (path.endsWith("/session")) return fulfillPortal(route, { json: { title: "Биология", role: "student" } });
        if (path.endsWith("/chat/stream")) {
            requests.push(route.request().postDataJSON());
            return fulfillPortal(route, { json: {
                answer: "Фазы связаны переносом энергии.",
                citations: [{ chunk_id: 3, document_id: 1, title, quote: "АТФ образуется в световой фазе." }],
                sections: [{ heading: "Как это работает", body: "Световая фаза обеспечивает цикл Кальвина энергией.",
                    bullets: ["Образуется АТФ", "АТФ используется в цикле"], citations: [3] }],
                diagram: { title: "Связь фаз", nodes: [{ id: "a", label: "Световая фаза на мембранах тилакоидов" },
                    { id: "b", label: "Цикл Кальвина в строме хлоропласта" }],
                    edges: [{ source: "a", target: "b", label: "передаёт АТФ и НАДФН" }], citations: [3] },
            } });
        }
        if (path.endsWith("/materials/1")) return fulfillPortal(route, { json: { title, document_id: 1,
            source_url: "https://canvas.test/courses/123/pages/lesson", chunks: [{ id: 3, text: "АТФ образуется в световой фазе." }] } });
        return fulfillPortal(route, { json: [{ title, document_id: 1, published: true, kind: "canvas_page" }] });
    });
    await page.goto("/portal");
    await page.getByLabel("Ваш вопрос").fill("Как связаны фазы фотосинтеза?");
    await page.getByRole("button", { name: "Отправить", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Как это работает" })).toBeVisible();
    await expect.poll(() => page.getByRole("log").evaluate(log => {
        const answer = log.querySelector("article:last-of-type")!;
        return Math.round(answer.getBoundingClientRect().top - log.getBoundingClientRect().top);
    })).toBeLessThan(40);
    const diagram = page.getByRole("figure", { name: "Связь фаз" });
    await expect(diagram).toContainText("составлена помощником");
    await diagram.scrollIntoViewIfNeeded();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await diagram.locator("li").evaluateAll(nodes => nodes.every(node => node.scrollWidth <= node.clientWidth))).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("structured-answer.png"), fullPage: true });
    await diagram.getByRole("button", { name: `Источник: ${title}`, exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("link", { name: "Открыть страницу в Canvas" })).toHaveAttribute("href", "https://canvas.test/courses/123/pages/lesson");
    await page.keyboard.press("Escape");
    for (const label of ["Объясни проще", "По шагам", "Покажи схему"]) {
        await page.getByRole("button", { name: label, exact: true }).click();
        await expect(page.getByLabel("Ваш вопрос")).toBeFocused();
        await expect(page.getByLabel("Ваш вопрос")).toHaveValue(/Как связаны фазы фотосинтеза/);
    }
    expect(requests).toHaveLength(1);
    await page.getByRole("button", { name: "Отправить", exact: true }).click();
    await expect.poll(() => requests.length).toBe(2);
    expect(requests[1].message).toContain("Покажи схему");
    expect(requests[1].response_style).toBe("diagram");
    expect(requests[1].history[1].content).toContain("Как это работает");
    await expect(page.getByRole("button", { name: "Отправить", exact: true })).toBeDisabled();
});
