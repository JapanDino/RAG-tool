import { expect, test, type Page } from "@playwright/test";

const API_BASE = `http://localhost:${process.env.CANVAS_SIMULATOR_E2E_BACKEND_PORT || "8000"}`;

type ProfileId = "deepseek_openai_v1" | "gemma_openai_v1";

const profiles = [
  {
    id: "deepseek_openai_v1",
    label: "DeepSeek · OpenAI-совместимый",
    contract: "openai_chat_completions_v1",
    summary: "Синтетический ответ DeepSeek прошёл локальный строгий JSON-контракт.",
  },
  {
    id: "gemma_openai_v1",
    label: "Gemma · OpenAI-совместимый",
    contract: "openai_chat_completions_v1",
    summary: "Синтетический ответ Gemma прошёл локальный строгий JSON-контракт.",
  },
] as const;

function reportFor(profile: ProfileId, configured = false) {
  const selected = profiles.find((item) => item.id === profile) || profiles[0];
  const localChecks = [
    {
      code: "profile_contract_supported",
      status: "passed",
      owner: "application",
      label: "Структурированный ответ распознаётся",
      detail: "Синтетический ответ прошёл локальный контракт.",
    },
    ...[
      "server_feature_enabled",
      "server_credential_present",
      "server_model_selection_present",
      "exact_origin_policy_valid",
      "bounded_runtime_policy_valid",
    ].map((code) => ({
      code,
      status: configured ? "passed" : "blocked",
      owner: "application",
      label: "Серверная настройка",
      detail: configured ? "Форма настройки принята." : "Требуется серверная настройка.",
    })),
  ];
  const externalChecks = [
    "host_reachable_from_application",
    "tls_chain_trusted",
    "configured_model_available",
    "structured_probe_succeeds",
    "latency_budget_observed",
  ].map((code) => ({
    code,
    status: "external",
    owner: "system_administrator",
    label: "Внешняя проверка",
    detail: "Выполняется системным администратором внутри школьной сети.",
  }));
  return {
    schema_version: 1,
    profile: selected,
    available_profiles: profiles,
    status: configured ? "ready_for_credentialed_probe" : "configuration_required",
    configuration_state: configured ? "configured" : "setup_required",
    organization_model_route: "deterministic_only",
    network_probe_performed: false,
    credentials_included: false,
    course_data_used: false,
    checks: [...localChecks, ...externalChecks],
    required_server_fields: ["AGENT_MODEL_ENABLED", "AGENT_MODEL_BASE_URL"],
    operator_command: `python scripts/check_agent_model_preflight.py --profile ${profile.startsWith("gemma") ? "gemma" : "deepseek"}`,
    limitations: [
      "Реальный хост не проверялся.",
      "Качество модели не проверялось.",
      "Секреты и данные курса не использовались.",
    ],
    bundle_fingerprint: profile.startsWith("gemma")
      ? "sha256:bbbbbbbbbbbbbbbb"
      : "sha256:aaaaaaaaaaaaaaaa",
  };
}

async function openPanel(page: Page) {
  await page.goto("/workspace/integrations/lti");
  const panel = page.getByRole("region", { name: "Паспорт подключения AI-сервиса" });
  await expect(panel).toBeVisible();
  return panel;
}

test.beforeEach(async ({ request, page }) => {
  const response = await request.post(
    `${API_BASE}/identity/development/bootstrap`,
    { data: {} },
  );
  expect(response.ok()).toBeTruthy();
  await page.addInitScript(() => {
    window.localStorage.setItem("rag-dev-user", "admin@local.test");
  });
});

test("administrator gets a staged, content-free infrastructure passport", async ({ page }, testInfo) => {
  const browserErrors: string[] = [];
  const preflightRequests: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await page.route("**/organizations/*/agent-model/preflight**", async (route) => {
    const request = route.request();
    preflightRequests.push(request.url());
    expect(request.headers()["x-api-key"]).toBeUndefined();
    const profile = new URL(request.url()).searchParams.get("profile") as ProfileId;
    await route.fulfill({ json: reportFor(profile) });
  });

  const panel = await openPanel(page);
  await expect(
    panel.getByRole("heading", { name: "Пакет готов, сервер ждёт настройки" }),
  ).toBeVisible();
  await expect(panel.getByText("Контракт DeepSeek распознаётся", { exact: true })).toBeVisible();
  await expect(panel.getByText("Проверить реальный хост в школьной сети", { exact: true })).toBeVisible();
  await expect(panel).toContainText("Сеть не проверялась");
  await expect(panel).toContainText("Секреты не включены");
  await expect(panel).toContainText("Данные курса не использованы");
  await expect(panel).toContainText("Использование школьного AI-сервиса сейчас на паузе");

  const gemma = panel.getByRole("button", { name: /Gemma/ });
  await gemma.focus();
  await page.keyboard.press("Enter");
  await expect(gemma).toHaveAttribute("aria-pressed", "true");
  await expect(panel.getByText("Контракт Gemma распознаётся", { exact: true })).toBeVisible();
  await expect(gemma).toBeFocused();
  expect(preflightRequests).toHaveLength(2);
  expect(preflightRequests.every((url) => url.startsWith(`${API_BASE}/`))).toBeTruthy();

  await panel.screenshot({ path: testInfo.outputPath("agent-model-preflight.png") });
  const overflow = await page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth;
    return Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .map((element) => Math.ceil(element.getBoundingClientRect().right))
      .filter((right) => right > viewportWidth + 1);
  });
  expect(overflow).toEqual([]);
  expect(browserErrors).toEqual([]);
});

test("configured server is described as ready only for a later credentialed probe", async ({ page }) => {
  await page.route("**/organizations/*/agent-model/preflight**", async (route) => {
    const profile = new URL(route.request().url()).searchParams.get("profile") as ProfileId;
    await route.fulfill({ json: reportFor(profile, true) });
  });
  const panel = await openPanel(page);
  await expect(
    panel.getByRole("heading", { name: "Можно переходить к внешней проверке" }),
  ).toBeVisible();
  await expect(panel).toContainText("Доступность хоста и качество модели ещё не проверялись");
  await expect(panel.getByText("Безопасная форма конфигурации принята", { exact: true })).toBeVisible();
  await expect(panel).toContainText("Локальная проверка контракта пройдена");
  await expect(panel).not.toContainText("6 локальных");
  await expect(panel).toContainText("Он не доказывает качество модели или готовность реального хоста");
});

test("failed profile switch keeps the previous passport and export coherent", async ({ page }) => {
  await page.route("**/organizations/*/agent-model/preflight**", async (route) => {
    const url = new URL(route.request().url());
    const profile = url.searchParams.get("profile") as ProfileId;
    if (!url.pathname.endsWith("/export") && profile === "gemma_openai_v1") {
      await route.fulfill({ status: 503, json: { detail: "private host state" } });
      return;
    }
    await route.fulfill({ json: reportFor(profile) });
  });
  const panel = await openPanel(page);
  const deepseek = panel.getByRole("button", { name: /DeepSeek/ });
  const gemma = panel.getByRole("button", { name: /Gemma/ });
  await gemma.focus();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("alert")).toContainText("Паспорт подключения не загрузился");
  await expect(gemma).toBeFocused();
  await expect(gemma).toHaveAttribute("aria-pressed", "false");
  await expect(deepseek).toHaveAttribute("aria-pressed", "true");
  await expect(panel.getByText("Контракт DeepSeek распознаётся", { exact: true })).toBeVisible();
  await expect(
    panel.getByRole("heading", { name: /DeepSeek · fingerprint sha256:aaaaaaaaaaaaaaaa/ }),
  ).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "Скачать пакет для системного администратора" }),
  ).toBeEnabled();
});

test("validated export downloads with a fixed safe filename", async ({ page }) => {
  await page.route("**/organizations/*/agent-model/preflight**", async (route) => {
    const request = route.request();
    expect(request.headers()["x-api-key"]).toBeUndefined();
    const profile = new URL(request.url()).searchParams.get("profile") as ProfileId;
    await route.fulfill({ json: reportFor(profile) });
  });
  const panel = await openPanel(page);
  await panel.getByRole("button", { name: /Gemma/ }).click();
  await expect(panel.getByText("Контракт Gemma распознаётся", { exact: true })).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await panel.getByRole("button", { name: "Скачать пакет для системного администратора" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("agent-model-preflight-gemma.json");
  const path = await download.path();
  expect(path).not.toBeNull();
  const body = await (await import("node:fs/promises")).readFile(path as string, "utf8");
  expect(body).toContain("sha256:bbbbbbbbbbbbbbbb");
  expect(body).not.toContain("secret-value");
  expect(body).not.toContain("course content");
  await expect(panel).toContainText("Пакет sha256:bbbbbbbbbbbbbbbb скачан");
});

test("unsafe export is rejected and a failed load offers keyboard retry", async ({ page }) => {
  let loadAttempts = 0;
  let unsafeExport = true;
  await page.route("**/organizations/*/agent-model/preflight**", async (route) => {
    const url = route.request().url();
    if (url.includes("/export")) {
      const safe = reportFor("deepseek_openai_v1");
      await route.fulfill({
        json: unsafeExport ? { ...safe, credentials_included: true } : safe,
      });
      return;
    }
    loadAttempts += 1;
    if (loadAttempts === 1) {
      await route.fulfill({ status: 503, json: { detail: "private infrastructure failure" } });
      return;
    }
    await route.fulfill({ json: reportFor("deepseek_openai_v1") });
  });

  await page.goto("/workspace/integrations/lti");
  await expect(page.getByRole("heading", { name: "Паспорт временно недоступен" })).toBeVisible();
  await expect(page.getByText(/private infrastructure failure/)).toHaveCount(0);
  const retry = page.getByRole("button", { name: "Собрать снова" });
  await retry.focus();
  await page.keyboard.press("Enter");
  const panel = page.getByRole("region", { name: "Паспорт подключения AI-сервиса" });
  await expect(panel).toBeVisible();

  await panel.getByRole("button", { name: "Скачать пакет для системного администратора" }).click();
  await expect(panel.getByRole("alert")).toContainText("Пакет не скачан");
  unsafeExport = false;
});
