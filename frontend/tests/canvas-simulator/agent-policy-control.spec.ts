import { expect, test } from "@playwright/test";

const API_BASE = `http://localhost:${process.env.CANVAS_SIMULATOR_E2E_BACKEND_PORT || "8000"}`;

const safetyBoundaries = [
  "evidence_required",
  "hidden_conversation_memory_disabled",
  "canvas_writes_disabled",
  "individual_surveillance_disabled",
];

const defaultPolicy = {
  organization_id: 1,
  learner_enabled: true,
  instructor_enabled: true,
  program_enabled: true,
  model_mode: "approved_host_with_safe_fallback",
  version: 0,
  updated_at: null,
  safety_boundaries: safetyBoundaries,
};

test.beforeEach(async ({ request, page }) => {
  const response = await request.post(
    `${API_BASE}/identity/development/bootstrap`,
    { data: {} }
  );
  expect(response.ok()).toBeTruthy();
  await page.addInitScript(() => {
    window.localStorage.setItem("rag-dev-user", "admin@local.test");
  });
});

test("administrator previews and applies the role and model route", async ({ page }, testInfo) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  let effective = { ...defaultPolicy };
  let policyReads = 0;
  await page.route("**/organizations/*/agent-policy**", async (route) => {
    const request = route.request();
    expect(request.headers()["x-api-key"]).toBeUndefined();
    const url = request.url();
    if (request.method() === "GET") {
      policyReads += 1;
      await route.fulfill({ json: effective });
      return;
    }
    if (url.endsWith("/preview")) {
      const body = request.postDataJSON();
      await route.fulfill({
        json: {
          current: effective,
          proposed: {
            learner_enabled: body.learner_enabled,
            instructor_enabled: body.instructor_enabled,
            program_enabled: body.program_enabled,
            model_mode: body.model_mode,
          },
          changes: [
            {
              field: "learner_enabled",
              label: "Помощник ученика",
              before: "Доступен",
              after: "На паузе",
              impact: "Новые и незавершённые задания ученика будут следовать этой настройке.",
            },
            {
              field: "model_mode",
              label: "Маршрут школьного AI-сервиса",
              before: "Школьный AI-сервис с безопасным резервом",
              after: "Только детерминированный режим",
              impact: "Определяет, может ли агент обращаться к настроенному школьному AI-сервису.",
            },
          ],
          confirmation: "apply_agent_policy",
        },
      });
      return;
    }
    const body = request.postDataJSON();
    expect(body.confirmation).toBe("apply_agent_policy");
    effective = {
      ...effective,
      learner_enabled: body.learner_enabled,
      instructor_enabled: body.instructor_enabled,
      program_enabled: body.program_enabled,
      model_mode: body.model_mode,
      version: 1,
      updated_at: "2026-08-03T10:00:00Z",
    };
    await route.fulfill({ json: effective });
  });

  await page.goto("/workspace/integrations/lti");
  const panel = page.getByRole("region", { name: "Кому и как помогает агент" });
  await expect(panel).toBeVisible();
  await expect(panel.getByText("Canvas", { exact: true })).toBeVisible();
  await expect(panel.getByText("Диагностика и восстановление", { exact: true })).toBeVisible();
  await expect(panel.getByText("Всегда доступен", { exact: true })).toBeVisible();

  const learnerRoute = panel.getByRole("switch", { name: /Помощник ученика/ });
  await expect(learnerRoute).toHaveAttribute("aria-checked", "true");
  await learnerRoute.click();
  await expect(learnerRoute).toHaveAttribute("aria-checked", "false");
  await panel.getByLabel("Только детерминированный режим").check();
  await panel.screenshot({ path: testInfo.outputPath("agent-policy-draft.png") });

  const previewButton = panel.getByRole("button", { name: "Проверить изменения" });
  await previewButton.focus();
  await page.keyboard.press("Enter");
  const previewHeading = panel.getByRole("heading", { name: "Что изменится после подтверждения" });
  await expect(previewHeading).toBeVisible();
  await expect(previewHeading).toBeFocused();
  await expect(panel.getByText("Canvas и сохранённые материалы не изменяются этой операцией.")).toBeVisible();
  await expect(panel.getByText("Доступен", { exact: true })).toBeVisible();
  await expect(panel.getByText("На паузе", { exact: true })).toBeVisible();
  await panel.screenshot({ path: testInfo.outputPath("agent-policy-preview.png") });

  await page.getByRole("button", { name: "Проверить готовность" }).click();
  await expect.poll(() => policyReads).toBeGreaterThan(1);
  await expect(panel.getByRole("heading", { name: "Что изменится после подтверждения" })).toBeVisible();

  await panel.getByRole("button", { name: "Вернуться к редактированию" }).click();
  await expect(previewButton).toBeFocused();
  await previewButton.click();
  await expect(previewHeading).toBeFocused();

  await panel.getByRole("button", { name: "Применить настройки" }).click();
  await expect(panel.getByText("Настройки применены. Действует версия 1.")).toBeVisible();
  await expect(panel.getByText("Версия 1", { exact: true })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Проверить изменения" })).toBeDisabled();

  const serialized = (await panel.textContent())?.toLowerCase() || "";
  for (const forbidden of ["api_key", "system_prompt", "base_url", "admin@local.test"])
    expect(serialized).not.toContain(forbidden);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  );
  expect(overflow).toBe(0);
  expect(browserErrors).toEqual([]);
});

test("version conflict keeps the administrator draft and requires a fresh preview", async ({ page }) => {
  let current = { ...defaultPolicy };
  let previewAttempts = 0;
  await page.route("**/organizations/*/agent-policy**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: current });
      return;
    }
    if (route.request().url().endsWith("/preview")) {
      previewAttempts += 1;
      if (previewAttempts === 1) {
        current = { ...current, instructor_enabled: false, version: 2 };
        await route.fulfill({
          status: 409,
          json: { detail: { code: "agent_policy_version_conflict" } },
        });
        return;
      }
      await route.fulfill({
        json: {
          current,
          proposed: { ...current, learner_enabled: false },
          changes: [
            {
              field: "learner_enabled",
              label: "Помощник ученика",
              before: "Доступен",
              after: "На паузе",
              impact: "Новые задания следуют текущей настройке.",
            },
          ],
          confirmation: "apply_agent_policy",
        },
      });
      return;
    }
    await route.abort();
  });

  await page.goto("/workspace/integrations/lti");
  const panel = page.getByRole("region", { name: "Кому и как помогает агент" });
  const learnerRoute = panel.getByRole("switch", { name: /Помощник ученика/ });
  await learnerRoute.click();
  await panel.getByRole("button", { name: "Проверить изменения" }).click();
  await expect(panel.getByText(/Другой администратор уже изменил политику/)).toBeVisible();
  await expect(panel.getByText("Версия 2", { exact: true })).toBeVisible();
  await expect(learnerRoute).toHaveAttribute("aria-checked", "false");
  await expect(panel.getByRole("button", { name: "Проверить изменения" })).toBeEnabled();

  await panel.getByRole("button", { name: "Проверить изменения" }).click();
  await expect(panel.getByRole("heading", { name: "Что изменится после подтверждения" })).toBeVisible();
});

test("load failure is bounded and keyboard retry restores the policy", async ({ page }) => {
  let attempts = 0;
  await page.route("**/organizations/*/agent-policy", async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 503, json: { detail: "secret infrastructure detail" } });
      return;
    }
    await route.fulfill({ json: defaultPolicy });
  });

  await page.goto("/workspace/integrations/lti");
  const errorPanel = page.getByRole("region", { name: "Настройки не загрузились" });
  await expect(errorPanel).toContainText("Другие функции Canvas не затронуты");
  await expect(errorPanel).not.toContainText("secret infrastructure detail");
  const retry = errorPanel.getByRole("button", { name: "Проверить снова" });
  await retry.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Кому и как помогает агент" })).toBeVisible();
});
