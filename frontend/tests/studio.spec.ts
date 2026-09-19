import { expect, test } from "@playwright/test";

test("studio navigation and layout work on desktop and mobile", async ({
    page,
}, testInfo) => {
    await page.addInitScript(() => {
        localStorage.setItem("bloom_visited", "1");
        localStorage.setItem("bloom_theme", "dark"); // Old preferences must not undo the redesign.
    });
    await page.route("**/api-proxy/**", (route) =>
        route.fulfill({ json: { status: "ok", semantic: true } }),
    );
    await page.goto("/");
    await expect(
        page.getByRole("heading", { name: "Анализ материалов", exact: true }),
    ).toBeVisible();
    await expect(
        page.getByRole("navigation", { name: "Разделы студии" }),
    ).toBeVisible();
    await expect(page.locator("body")).toHaveCSS(
        "background-color",
        "rgb(255, 255, 255)",
    );
    await page.screenshot({
        path: testInfo.outputPath("studio.png"),
        fullPage: true,
    });
    if (testInfo.project.name === "desktop") {
        await page.getByTitle("Выбрать датасет").click();
        await expect(page.getByLabel("Dataset ID (ввести вручную)")).toBeFocused();
    }
    await page
        .getByRole("button", { name: "Векторный поиск", exact: true })
        .click();
    await expect(
        page.getByRole("heading", { name: "Поиск по материалам", exact: true }),
    ).toBeVisible();
    await page
        .getByRole("navigation")
        .getByRole("button", { name: "Настройки", exact: true })
        .click();
    await expect(
        page.getByText("Эмбеддинги", { exact: true }).last(),
    ).toBeVisible();
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
});
