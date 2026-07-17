import {expect, test, type Page} from "playwright/test";

function captureBrowserFailures(page: Page) {
  const failures: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => failures.push(`page: ${error.message}`));
  page.on("requestfailed", (request) => {
    const reason = request.failure()?.errorText;
    if (reason !== "net::ERR_ABORTED") {
      failures.push(`request: ${request.method()} ${request.url()} ${reason}`);
    }
  });
  return failures;
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
}

test("salary benchmark uses the verified market snapshot", async ({page}) => {
  const failures = captureBrowserFailures(page);
  await page.goto("/salary");
  await page.getByLabel("Khu vực").selectOption("Ha Noi");
  const prediction = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/api/salary/predict") &&
      response.status() === 200,
  );
  await page.getByRole("button", {name: "Tính mức lương thị trường"}).click();
  const result = (await (await prediction).json()) as {
    salary_estimate: number;
    sample_size: number;
    source: string;
    period_end: string;
  };
  const millions = `${Math.round(result.salary_estimate / 100_000) / 10}M`;
  const [year, month] = result.period_end.split("-");

  expect(result.source).toBe("market_quantiles");
  expect(result.sample_size).toBeGreaterThanOrEqual(3);
  await expect(page.getByText(millions).first()).toBeVisible();
  await expect(
    page.getByText(new RegExp(`${result.sample_size} quan sát công khai`)),
  ).toBeVisible();
  await expect(page.getByText(new RegExp(`${month}/${year}`))).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({path: "test-results/salary-desktop.png", fullPage: true});
  expect(failures).toEqual([]);
});

test("candidate can own and erase CV data, then manage an alert", async ({page}) => {
  const failures = captureBrowserFailures(page);
  const email = `e2e-${Date.now()}@example.com`;

  await page.goto("/profile");
  await page.getByRole("button", {name: "Chưa có tài khoản? Đăng ký"}).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mật khẩu").fill("JobRadar-e2e-password");
  await page.getByRole("button", {name: "Đăng ký", exact: true}).click();
  await expect(page.getByRole("heading", {name: email})).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: "candidate.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "Backend Developer with 4 years of Python, FastAPI, PostgreSQL and Docker experience.",
    ),
  });
  await expect(page.getByText(/Đã phân tích CV/)).toBeVisible();
  await expect(page.getByRole("button", {name: "Xóa dữ liệu CV"})).toBeVisible();
  await page.getByRole("button", {name: "Xóa dữ liệu CV"}).click();
  await expect(page.getByText("Đã xóa nội dung CV và vector ngữ nghĩa.")).toBeVisible();

  await page.goto("/alerts");
  await page.getByRole("button", {name: "Tạo cảnh báo"}).click();
  await page.getByLabel("Tên cảnh báo").fill("Backend Hà Nội");
  await page.getByLabel("Kỹ năng, cách nhau bằng dấu phẩy").fill("Python, FastAPI");
  await page.getByLabel("Khu vực").fill("Ha Noi");
  await page.getByRole("button", {name: "Lưu cảnh báo"}).click();
  await expect(page.getByText("Backend Hà Nội")).toBeVisible();
  await expect(page.getByText("Đã tạo cảnh báo.")).toBeVisible();
  const toggle = page.locator(".toggle input");
  await expect(toggle).toBeChecked();
  await page.locator(".toggle span").click();
  await expect(toggle).not.toBeChecked();
  const deleted = page.waitForResponse(
    (response) =>
      response.request().method() === "DELETE" &&
      response.url().includes("/api/alerts/") &&
      response.status() === 204,
  );
  await page.getByRole("button", {name: "Xóa cảnh báo"}).click();
  await deleted;
  await expect(page.getByText("Backend Hà Nội")).not.toBeVisible();
  await expectNoHorizontalOverflow(page);
  expect(failures).toEqual([]);
});
