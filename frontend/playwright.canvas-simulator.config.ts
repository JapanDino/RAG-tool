import { defineConfig, devices } from "@playwright/test";

const e2eDatabase = `sqlite:///../.tmp/canvas-simulator-e2e-${process.pid}.db`;
const backendPort = process.env.CANVAS_SIMULATOR_E2E_BACKEND_PORT || "8000";
const frontendPort = process.env.CANVAS_SIMULATOR_E2E_FRONTEND_PORT || "3000";
const backendUrl = `http://localhost:${backendPort}`;
const frontendUrl = `http://localhost:${frontendPort}`;

const sharedEnvironment = {
  APP_ENV: "development",
  AUTH_MODE: "development",
  CANVAS_SIMULATOR_ENABLED: "true",
  CANVAS_SIMULATOR_DATA_MODE: "synthetic",
  // Regression trap: actor-aware SSR must ignore the legacy chooser map.
  CANVAS_SIMULATOR_LTI_REGISTRATION_MAP: '{"demo-ai":1,"demo-review":2}',
  CANVAS_SIMULATOR_LTI_BASE_URL: backendUrl,
  CANVAS_SIMULATOR_E2E_BACKEND_PORT: backendPort,
  CORS_ALLOW_ORIGINS: frontendUrl,
  DATABASE_URL: e2eDatabase,
  EMBEDDING_PROVIDER: "hash",
  ENABLE_LLM: "0",
  FRONTEND_PUBLIC_URL: frontendUrl,
};

export default defineConfig({
  testDir: "./tests/canvas-simulator",
  timeout: 60_000,
  fullyParallel: false,
  forbidOnly: true,
  preserveOutput: "always",
  retries: 0,
  workers: 1,
  reporter: "line",
  expect: {
    timeout: 15_000,
  },
  use: {
    baseURL: frontendUrl,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "mobile",
      use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: [
    {
      command: "python ../scripts/start_canvas_simulator_e2e.py",
      env: sharedEnvironment,
      reuseExistingServer: false,
      stderr: "pipe",
      stdout: "pipe",
      timeout: 120_000,
      url: `${backendUrl}/openapi.json`,
    },
    {
      command: `npx next start -p ${frontendPort}`,
      env: {
        ...sharedEnvironment,
        NEXT_PUBLIC_API_BASE: backendUrl,
      },
      reuseExistingServer: false,
      stderr: "pipe",
      stdout: "pipe",
      timeout: 180_000,
      url: `${frontendUrl}/canvas-simulator`,
    },
  ],
});
