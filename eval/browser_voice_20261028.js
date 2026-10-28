async (page) => {
  const root = new URL(page.url()).origin;
  const installMock = () => {
    window.__speechTest = { starts: 0, stops: 0, aborts: 0, instance: null, onStop: "" };
    class FakeRecognition {
      constructor() { window.__speechTest.instance = this; }
      start() { window.__speechTest.starts++; this.onstart?.(); }
      stop() {
        window.__speechTest.stops++;
        const transcript = window.__speechTest.onStop;
        if (transcript) this.onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript }, length: 1 }] });
        this.onend?.();
      }
      abort() { window.__speechTest.aborts++; this.onend?.(); }
    }
    Object.defineProperty(window, "SpeechRecognition", { value: FakeRecognition, configurable: true });
  };
  await page.addInitScript(installMock);
  const requests = [];
  await page.route("**/api/chat", async (route) => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ json: { session_id: "test", reply: "Принято", payload: { kind: "greeting" },
      stage: "start", understood: [], assumptions: [], suggestions: [], nlu: "rules", checked: [], ms: 0 } });
  });
  await page.reload();
  const send = page.locator("#send");
  const input = page.getByRole("textbox", { name: "Сообщение агенту" });
  if ((await page.evaluate(() => window.__speechTest.starts)) !== 0) throw new Error("started without hold");
  await input.fill("План");
  await page.evaluate(() => { window.__speechTest.onStop = "хочу в горы"; });
  await send.hover();
  await page.mouse.down();
  await page.waitForTimeout(650);
  if ((await send.getAttribute("data-listening")) !== "true") throw new Error("no listening state while held");
  if ((await page.evaluate(() => window.__speechTest.starts)) !== 1) throw new Error("hold did not start recognition");
  await page.mouse.up();
  if ((await input.inputValue()) !== "План хочу в горы") throw new Error("text was not appended for review");
  if (requests.length) throw new Error("release sent the message automatically");
  if (!(await page.locator("#voice-status").innerText()).includes("Проверьте")) throw new Error("no review status");
  await send.click();
  await page.waitForFunction(() => document.querySelector("#log")?.innerText.includes("Принято"));
  if (requests.length !== 1 || requests[0].text !== "План хочу в горы") throw new Error("manual short-click send differs");

  await page.evaluate(() => { window.__speechTest.onStop = ""; });
  await send.hover(); await page.mouse.down(); await page.waitForTimeout(650);
  await page.evaluate(() => { const r = window.__speechTest.instance; r.onerror({ error: "not-allowed" }); r.onend(); });
  await page.mouse.up();
  if (!(await page.locator("#voice-status").innerText()).includes("разрешения")) throw new Error("permission denial not explained");

  await send.focus(); await page.keyboard.down("Space"); await page.waitForTimeout(650);
  if ((await page.evaluate(() => window.__speechTest.starts)) !== 3) throw new Error("keyboard hold did not start recognition");
  await page.keyboard.up("Space");
  if (requests.length !== 1) throw new Error("keyboard hold sent the message");

  const unsupported = await page.context().newPage();
  await unsupported.addInitScript(() => {
    Object.defineProperty(window, "SpeechRecognition", { value: undefined, configurable: true });
    Object.defineProperty(window, "webkitSpeechRecognition", { value: undefined, configurable: true });
  });
  await unsupported.goto(root + "/");
  if (!(await unsupported.locator("#send").isEnabled())) throw new Error("text send disabled in unsupported browser");
  if (!(await unsupported.locator("#voice-status").innerText()).includes("недоступен")) throw new Error("no text fallback");
  await unsupported.close();

  const embed = await page.context().newPage();
  await embed.addInitScript(installMock);
  await embed.goto(root + "/static/widget-demo.html");
  await embed.getByRole("button", { name: "Открыть помощника по поездкам" }).click();
  const child = embed.frameLocator('iframe[title="Помощник в планировании поездки"]');
  await child.locator("#send").hover(); await embed.mouse.down(); await embed.waitForTimeout(650);
  const frame = embed.frames().find((item) => item.url().includes("/static/widget.html"));
  if (!frame || !(await frame.evaluate(() => window.__speechTest.starts === 1))) throw new Error("widget did not start");
  await embed.getByRole("button", { name: "Закрыть помощника по поездкам" }).evaluate((button) => button.click());
  await frame.waitForFunction(() => window.__speechTest.aborts === 1);
  await embed.mouse.up();
  await embed.close();
  return { status: "PASS", mocked_speech: true, hold_release: true, automatic_send: false,
    short_click_send: true, keyboard_hold: true, permission_denial: true, unsupported_fallback: true,
    widget_close_stops_recognition: true };
}
