async (page) => {
  const root = new URL(page.url()).origin;
  await page.addInitScript(() => {
    window.__audioTest = { requested: 0, tracksStopped: 0, delay: 0 };
    const stream = { getTracks: () => [{ stop: () => { window.__audioTest.tracksStopped++; } }] };
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: {
      getUserMedia: async () => {
        window.__audioTest.requested++;
        await new Promise((resolve) => setTimeout(resolve, window.__audioTest.delay));
        return stream;
      }
    }});
    class FakeAudioContext {
      constructor() { this.sampleRate = 16000; }
      resume() { return Promise.resolve(); }
      close() { return Promise.resolve(); }
      createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
      createScriptProcessor() {
        const node = { onaudioprocess: null, disconnect() {}, connect() {
          setTimeout(() => node.onaudioprocess?.({ inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.1) },
            outputBuffer: { getChannelData: () => new Float32Array(4096) } }), 20);
        }};
        return node;
      }
    }
    window.AudioContext = FakeAudioContext;
  });
  const chats = [], audioRequests = [];
  await page.route("**/api/voice", (route) => route.fulfill({ json: { backend: "gigaam", status: "ready", max_seconds: 20 } }));
  await page.route("**/api/voice/transcribe", async (route) => {
    const bytes = route.request().postDataBuffer();
    audioRequests.push({ type: route.request().headers()["content-type"], riff: bytes?.subarray(0, 4).toString(), length: bytes?.length });
    await route.fulfill({ json: { backend: "gigaam", text: "с другом в горы" } });
  });
  await page.route("**/api/chat", async (route) => {
    chats.push(route.request().postDataJSON());
    await route.fulfill({ json: { session_id: "test", reply: "Принято", payload: { kind: "greeting" },
      stage: "start", understood: [], assumptions: [], suggestions: [], nlu: "rules", checked: [], ms: 0 } });
  });
  await page.goto(root + "/");
  await page.waitForFunction(() => document.querySelector("#voice-status")?.innerText.includes("сервере"));
  if ((await page.evaluate(() => window.__audioTest.requested)) !== 0) throw new Error("microphone started without hold");
  const send = page.locator("#send"), input = page.locator("#text");
  await input.fill("Еду"); await send.hover(); await page.mouse.down(); await page.waitForTimeout(800); await page.mouse.up();
  await page.waitForFunction(() => document.querySelector("#text")?.value.includes("с другом в горы"));
  if ((await input.inputValue()) !== "Еду с другом в горы") throw new Error("local transcript not available for review");
  if (audioRequests.length !== 1 || audioRequests[0].riff !== "RIFF" || audioRequests[0].type !== "audio/wav" || audioRequests[0].length <= 44)
    throw new Error("bad audio request");
  if (chats.length) throw new Error("message was sent automatically");
  if ((await page.evaluate(() => window.__audioTest.tracksStopped)) !== 1) throw new Error("microphone still active");
  await send.click();
  await page.waitForFunction(() => document.querySelector("#log")?.innerText.includes("Принято"));
  if (chats.length !== 1 || chats[0].text !== "Еду с другом в горы") throw new Error("manual send failed");

  await page.evaluate(() => { window.__audioTest.delay = 600; });
  await send.hover(); await page.mouse.down(); await page.waitForTimeout(650); await page.mouse.up();
  await page.waitForTimeout(700);
  if (audioRequests.length !== 1 || chats.length !== 1) throw new Error("late permission sent audio or message");
  if ((await page.evaluate(() => window.__audioTest.tracksStopped)) !== 2) throw new Error("late microphone permission not released");
  return { status: "PASS", mocked_microphone: true, server_receives_wav: true, review_before_send: true,
    late_permission_released: true };
}
