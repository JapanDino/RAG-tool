import { fulfillPortal } from "./portal-fixture";
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

test("protected illustrations appear in chat and material reader with original download", async ({ page }, testInfo) => {
    await page.addInitScript(() => { sessionStorage.setItem("canvas_portal_token", "synthetic-image-session"); Object.defineProperty(navigator, "pdfViewerEnabled", { value: false }); });
    let hidden = false;
    const image = { id: 7, document_id: 1, caption: "Схема связи фаз фотосинтеза", location: "Страница 2", page: 2, width: 1000, height: 420 };
    await page.route("**/api-proxy/portal/**", async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith("/preferences")) return route.fulfill({ json: { quality_enabled: false, allow_solutions: false, solution_after_attempts: 2 } });
        if (path.endsWith("/imports/latest")) return route.fulfill({ json: null });
        expect(route.request().headers().authorization).toBe("Bearer synthetic-image-session");
        expect(route.request().url()).not.toContain("synthetic-image-session");
        if (path.endsWith("/images/7")) return hidden
            ? fulfillPortal(route, { status: 404, json: { detail: "Hidden" } })
            : fulfillPortal(route, { contentType: "image/png", body: readFileSync(join(__dirname, "fixtures", "diagram.png")) });
        if (path.endsWith("/original")) return fulfillPortal(route, { body: "synthetic PDF", headers: { "content-type": "application/pdf" } });
        if (path.endsWith("/session")) return fulfillPortal(route, { json: { title: "Биология", role: "student" } });
        if (path.endsWith("/chat/stream")) return fulfillPortal(route, { json: {
            answer: "Световая фаза образует АТФ и НАДФН для цикла Кальвина.", images: [image],
            citations: [{ document_id: 1, chunk_id: 2, title: "Фотосинтез.pdf", quote: "Две фазы связаны переносом энергии." }],
        } });
        if (path.endsWith("/materials/1")) return fulfillPortal(route, { json: { title: "Фотосинтез.pdf", document_id: 1,
            original_available: true, original_mime: "application/pdf", images: [image], chunks: [{ id: 1, text: "Учебный текст." }] } });
        return fulfillPortal(route, { json: [{ document_id: 1, title: "Фотосинтез.pdf", published: true, kind: "literature" }] });
    });
    await page.goto("/portal");
    await page.getByLabel("Ваш вопрос").fill("Как связаны две фазы?");
    await page.getByRole("button", { name: "Отправить", exact: true }).click();
    const picture = page.getByRole("img", { name: image.caption });
    await expect(picture).toBeVisible();
    await expect.poll(() => picture.evaluate((node: HTMLImageElement) => node.naturalWidth)).toBe(1000);
    await page.getByRole("button", { name: "Открыть источник иллюстрации" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("img")).toBeVisible();
    await dialog.getByRole("button", { name: "Открыть PDF" }).click();
    await expect(dialog.getByRole("alert")).toContainText("В этом браузере нет встроенного просмотра PDF");
    const downloadPromise = page.waitForEvent("download");
    await dialog.getByRole("button", { name: "Скачать оригинал" }).click();
    expect((await downloadPromise).suggestedFilename()).toBe("Фотосинтез.pdf");
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("illustrated-source.png"), fullPage: true });
    await page.keyboard.press("Escape");
    hidden = true;
    await page.getByRole("button", { name: "Материалы", exact: true }).click();
    await page.getByRole("button", { name: "Читать", exact: true }).click();
    await expect(page.getByRole("dialog").getByRole("status")).toContainText("Иллюстрация недоступна");
    await expect(page.getByRole("dialog").getByRole("img")).toHaveCount(0);
});
