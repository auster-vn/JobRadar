import {expect, test} from "playwright/test";

test("salary workflow remains usable on mobile", async ({page}) => {
  await page.goto("/salary");
  await page.getByLabel("Khu vực").selectOption("Ha Noi");
  const prediction = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/api/salary/predict") &&
      response.status() === 200,
  );
  await page.getByRole("button", {name: "Tính mức lương thị trường"}).click();
  const result = (await (await prediction).json()) as {salary_estimate: number};
  const millions = `${Math.round(result.salary_estimate / 100_000) / 10}M`;

  await expect(page.getByText(millions).first()).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
  await page.screenshot({path: "test-results/salary-mobile.png", fullPage: true});
});

test("mobile navigation keeps the application tracker reachable", async ({page}) => {
  await page.route("**/api/applications**", (route) =>
    route.fulfill({status: 401, contentType: "application/json", body: JSON.stringify({detail: "Not authenticated"})}),
  );
  await page.route("**/api/auth/refresh", (route) =>
    route.fulfill({status: 401, contentType: "application/json", body: JSON.stringify({detail: "Not authenticated"})}),
  );
  await page.goto("/applications");
  await expect(page.getByRole("heading", {name: "Theo dõi ứng tuyển"})).toBeVisible();
  await expect(page.getByText("Đăng nhập để theo dõi ứng tuyển")).toBeVisible();
  await expect(page.getByRole("navigation", {name: "Điều hướng di động"}).getByRole("link", {name: "Ứng tuyển"})).toHaveAttribute("aria-current", "page");
  await page.getByRole("link", {name: "Mở trang đăng nhập"}).click();
  await expect(page).toHaveURL(/\/login\?next=%2Fapplications$/);
  await expect(page.getByRole("heading", {name: "Đăng nhập an toàn"})).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
});
