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
