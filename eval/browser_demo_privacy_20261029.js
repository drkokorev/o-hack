// playwright-cli -s=privacy run-code --filename eval/browser_demo_privacy_20261029.js
// Run against the locally started demo. All dialogue inputs are fictional.
async (page) => {
  const base = "http://localhost:8080";
  const checks = [];
  const external = new Set();
  const errors = [];
  const check = (name, condition) => {
    checks.push({name, pass: Boolean(condition)});
    if (!condition) throw new Error(name);
  };
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (["http:", "https:"].includes(url.protocol) && url.origin !== base) external.add(url.origin);
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto(base);
  await page.waitForFunction(() => document.querySelectorAll("#stages li").length > 0);
  const draft = "Хочу из Казани к морю в июне, вдвоём";
  await page.locator("#text").fill(draft);
  const footer = page.locator(".site-legal-footer");
  await footer.scrollIntoViewIfNeeded();
  check("two_footer_links", await footer.locator("a").count() === 2);
  check("footer_links_preserve_chat_tab", await footer.locator('a[target="_blank"]').count() === 2);
  await page.screenshot({path: "output/playwright/privacy-footer-desktop.png"});
  const [policy] = await Promise.all([
    page.context().waitForEvent("page"),
    footer.getByRole("link", {name: "Политика конфиденциальности", exact: true}).click()
  ]);
  await policy.waitForLoadState();
  check("policy_is_readable", (await policy.locator("h1").innerText()) === "Политика конфиденциальности");
  check("policy_marks_demo_and_missing_operator", (await policy.locator("body").innerText()).includes("Оператор сервиса ещё не указан"));
  check("policy_has_no_script", await policy.locator("script").count() === 0);
  await policy.screenshot({path: "output/playwright/privacy-document-desktop.png", fullPage: true});
  await policy.getByRole("link", {name: "Условия использования", exact: true}).click();
  check("terms_are_readable", (await policy.locator("h1").innerText()) === "Условия использования");
  await policy.close();
  check("draft_survives_document_reading", await page.locator("#text").inputValue() === draft);

  // Real local model-backed HTTP dialogue: no names, contacts or documents.
  await page.locator("#text").fill("Из Казани в Стамбул с 10 по 17 мая 2027, двое взрослых, бюджет 180000 рублей");
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url() === `${base}/api/chat` && r.request().method() === "POST", {timeout: 90000}),
    page.locator("#send").click()
  ]);
  const first = await response.json();
  check("chat_responds_after_documents", response.ok() && Boolean(first.reply));
  check("explicit_origin_is_preserved", (first.understood || []).includes("из: Казань"));
  check("destination_is_preserved", (first.understood || []).some((s) => s.includes("Стамбул")));

  const [terms] = await Promise.all([
    page.context().waitForEvent("page"),
    footer.getByRole("link", {name: "Условия использования", exact: true}).click()
  ]);
  await terms.waitForLoadState();
  await terms.close();
  await page.locator("#text").fill("Теперь без самолёта, остальное оставь");
  const [next] = await Promise.all([
    page.waitForResponse((r) => r.url() === `${base}/api/chat` && r.request().method() === "POST", {timeout: 90000}),
    page.locator("#send").click()
  ]);
  const second = await next.json();
  check("session_survives_document_reading", first.session_id === second.session_id);
  check("origin_survives_correction", (second.understood || []).includes("из: Казань"));
  check("destination_survives_correction", (second.understood || []).some((s) => s.includes("Стамбул")));

  // Mobile legal links stay accessible with the map hidden.
  await page.setViewportSize({width: 390, height: 844});
  await page.goto(base);
  await footer.scrollIntoViewIfNeeded();
  check("mobile_footer_is_visible", await footer.isVisible());
  check("mobile_has_no_horizontal_overflow", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await page.screenshot({path: "output/playwright/privacy-footer-mobile.png"});

  // On a failing voice discovery request even a browser with SpeechRecognition must not use it.
  await page.route("**/api/voice", (route) => route.fulfill({status: 503, body: "unavailable"}));
  await page.addInitScript(() => {
    window.__externalSpeechCalls = 0;
    window.SpeechRecognition = window.webkitSpeechRecognition = class {
      constructor() { window.__externalSpeechCalls++; throw new Error("External speech must not be started"); }
    };
  });
  await Promise.all([
    page.waitForResponse((r) => r.url() === `${base}/api/voice`),
    page.goto(base)
  ]);
  await page.locator("#mic").click();
  check("failed_voice_keeps_external_speech_off", await page.evaluate(() => window.__externalSpeechCalls === 0));
  check("failed_voice_offers_text", (await page.locator("#voice-status").innerText()).includes("можно написать сообщение"));
  check("failed_voice_keeps_input_enabled", await page.locator("#text").isEnabled());
  await page.unroute("**/api/voice");

  await page.goto(`${base}/static/widget.html`);
  check("widget_has_both_documents", await page.locator('.legal-links a[target="_blank"]').count() === 2);
  check("no_automatic_external_browser_requests", external.size === 0);
  check("no_javascript_errors", errors.length === 0);
  return {checks, live_dialogue: {first_nlu: first.nlu, second_nlu: second.nlu,
    first_kind: first.payload?.kind, second_kind: second.payload?.kind},
    external_origins: [...external], javascript_errors: errors};
}
