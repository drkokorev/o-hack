// Run through playwright-cli against the isolated local preview.
async (page) => {
  const base = new URL(page.url()).origin;
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/info", (route) => route.fulfill({status:503, body:"unavailable"}));
  await page.goto(base + "/");
  await page.getByText("Не удалось подключиться. Проверьте, что приложение запущено.").waitFor();
  await page.getByText("Не удалось загрузить карту. Повторите подключение.").waitFor();
  await page.unroute("**/api/info");
  await page.getByRole("button", {name:"Повторить", exact:true}).click();
  await page.getByText("Расскажите, что важно в поездке.", {exact:false}).waitFor();
  await page.locator(".maplibregl-canvas").waitFor({timeout:30000});
  if (await page.locator("#startup-error").count()) throw new Error("Startup error remained after recovery");
  if (errors.length) throw new Error(errors.join("; "));
  return {initialFailure:"shown", retry:"recovered", map:"loaded", javascriptErrors:errors};
}
