import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
    testDir: "./tests",
    fullyParallel: true,
    use: {
        baseURL: "http://127.0.0.1:3100",
        screenshot: "only-on-failure",
        channel: process.env.PLAYWRIGHT_CHANNEL,
    },
    projects: [
        { name: "desktop", use: { ...devices["Desktop Chrome"] } },
        {
            name: "mobile",
            use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
        },
    ],
    webServer: {
        command: "npx next start -H 127.0.0.1 -p 3100",
        url: "http://127.0.0.1:3100/portal",
        reuseExistingServer: false,
    },
});
