// playwright-cli -s=privacy run-code --filename eval/browser_voice_privacy_20261029.js
// Synthetic microphone samples and stub transcription isolate the recording controls.
async (page) => {
  const test = await page.context().newPage();
  const checks = [];
  const check = (name, condition) => {
    checks.push({name, pass: Boolean(condition)});
    if (!condition) throw new Error(name);
  };
  let transcriptions = 0, chats = 0, lastText = null;
  const transcript = "Хочу из Казани к морю";
  await test.addInitScript(() => {
    window.__mic = {requests: 0, stopped: 0, frames: 0, external: 0};
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {configurable: true, value: async () => {
      window.__mic.requests++;
      return {getTracks: () => [{stop: () => window.__mic.stopped++}]};
    }});
    window.AudioContext = class {
      constructor() { this.sampleRate = 16000; }
      async resume() {}
      createMediaStreamSource() { return {connect() {}, disconnect() {}}; }
      createScriptProcessor() {
        const processor = {connect() {}, disconnect() {}};
        this.timer = setInterval(() => {
          if (!processor.onaudioprocess) return;
          window.__mic.frames++;
          processor.onaudioprocess({
            inputBuffer: {getChannelData: () => new Float32Array(4096).fill(0.01)},
            outputBuffer: {getChannelData: () => new Float32Array(4096)}
          });
        }, 20);
        return processor;
      }
      async close() { clearInterval(this.timer); }
    };
    window.SpeechRecognition = window.webkitSpeechRecognition = class {
      constructor() { window.__mic.external++; throw new Error("External speech is forbidden"); }
    };
  });
  await test.route("**/api/voice", (route) => route.fulfill({json: {backend: "gigaam", status: "ready", max_seconds: 20}}));
  await test.route("**/api/voice/transcribe", (route) => {
    transcriptions++;
    if ((route.request().postDataBuffer()?.length || 0) <= 44) throw new Error("Missing synthetic WAV");
    return route.fulfill({json: {text: transcript, backend: "gigaam"}});
  });
  await test.route("**/api/chat", (route) => {
    chats++;
    lastText = route.request().postDataJSON().text;
    return route.fulfill({json: {session_id: "synthetic-voice-check", reply: "Условия приняты.",
      stage: "start", understood: [], suggestions: [], checked: [], payload: null}});
  });
  try {
    await Promise.all([
      test.waitForResponse((r) => r.url().endsWith("/api/voice")),
      test.goto("http://localhost:8080")
    ]);
    await test.locator("#mic").click();
    check("main_explains_audio_before_capture", await test.locator("#voice-dialog").isVisible() &&
      await test.evaluate(() => window.__mic.requests === 0));
    await test.locator("#voice-dismiss").click();
    check("declining_does_not_capture", await test.evaluate(() => window.__mic.requests === 0));
    await test.locator("#mic").click();
    await test.locator("#voice-allow").click();
    await test.waitForFunction(() => window.__mic.frames > 0);
    await test.locator("#mic").click();
    await test.waitForFunction((text) => document.querySelector("#text").value === text, transcript);
    check("main_stop_previews_without_sending", transcriptions === 1 && chats === 0);
    check("main_stop_releases_microphone", await test.evaluate(() => window.__mic.stopped >= 1));
    await test.locator("#text").fill(`${transcript}, вдвоём`);
    await test.locator("#send").click();
    await test.waitForFunction(() => document.querySelector("#log").textContent.includes("Условия приняты"));
    check("edited_transcript_is_sent", chats === 1 && lastText === `${transcript}, вдвоём`);
    await test.locator("#mic").click();
    await test.waitForFunction(() => document.querySelector("#mic").dataset.listening === "true");
    await test.keyboard.press("Escape");
    check("escape_discards_recording", transcriptions === 1 && await test.evaluate(() => window.__mic.stopped >= 2));
    await test.locator("#mic").click();
    await test.waitForFunction(() => document.querySelector("#mic").dataset.listening === "true");
    await test.evaluate(() => window.dispatchEvent(new Event("pagehide")));
    check("pagehide_discards_recording", transcriptions === 1 && await test.evaluate(() => window.__mic.stopped >= 3));
    check("main_never_uses_external_recognition", await test.evaluate(() => window.__mic.external === 0));

    await Promise.all([
      test.waitForResponse((r) => r.url().endsWith("/api/voice")),
      test.goto("http://localhost:8080/static/widget.html")
    ]);
    const button = test.locator(".entry button");
    await button.click();
    check("widget_explains_audio_before_capture", await test.locator("#voice-dialog").isVisible() &&
      await test.evaluate(() => window.__mic.requests === 0));
    await test.locator("#voice-allow").click();
    await test.waitForFunction(() => window.__mic.frames > 0);
    await button.click();
    await test.waitForFunction((text) => document.querySelector("#text").value === text, transcript);
    check("widget_second_click_previews_and_stops", transcriptions === 2 && chats === 1 &&
      await test.evaluate(() => window.__mic.stopped >= 1));
    await button.click();
    await test.waitForFunction(() => document.querySelector("#log").textContent.includes("Условия приняты"));
    check("widget_text_still_sends", chats === 2 && lastText === transcript);
    check("widget_never_uses_external_recognition", await test.evaluate(() => window.__mic.external === 0));
    return {checks, transcriptions, chats, synthetic_audio: true, real_microphone_tested: false};
  } finally {
    await test.close();
  }
}
