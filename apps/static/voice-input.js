/* Local or browser voice recognition; dictation is always reviewed before sending. */
(() => {
  "use strict";

  const pcmWav = (chunks, sourceRate) => {
    const size = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const source = new Float32Array(size);
    let offset = 0;
    for (const chunk of chunks) { source.set(chunk, offset); offset += chunk.length; }
    const targetRate = 16000, length = Math.min(targetRate * 20, Math.floor(size * targetRate / sourceRate));
    const bytes = new ArrayBuffer(44 + length * 2), view = new DataView(bytes);
    const write = (pos, value) => [...value].forEach((char, i) => view.setUint8(pos + i, char.charCodeAt(0)));
    write(0, "RIFF"); view.setUint32(4, 36 + length * 2, true); write(8, "WAVE");
    write(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, targetRate, true); view.setUint32(28, targetRate * 2, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true); write(36, "data"); view.setUint32(40, length * 2, true);
    for (let i = 0; i < length; i++) {
      const start = Math.floor(i * sourceRate / targetRate), end = Math.max(start + 1, Math.floor((i + 1) * sourceRate / targetRate));
      let sample = 0;
      for (let j = start; j < end; j++) sample += source[j] || 0;
      sample = Math.max(-1, Math.min(1, sample / (end - start)));
      view.setInt16(44 + i * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
    }
    return bytes;
  };

  class LocalRecognition {
    constructor() { this.chunks = []; this.stream = null; this.context = null; this.stopped = false; this.cancelled = false; }
    start() { this.open(); }
    async open() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (this.stopped || this.cancelled) { stream.getTracks().forEach((track) => track.stop()); this.onend?.(); return; }
        this.stream = stream;
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        this.context = new AudioContext();
        await this.context.resume();
        if (this.stopped || this.cancelled) { this.cleanup(); this.onend?.(); return; }
        this.source = this.context.createMediaStreamSource(stream);
        this.processor = this.context.createScriptProcessor(4096, 1, 1);
        this.processor.onaudioprocess = (event) => {
          if (!this.stopped) this.chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
          event.outputBuffer.getChannelData(0).fill(0);
        };
        this.source.connect(this.processor); this.processor.connect(this.context.destination);
        this.onstart?.();
        this.limit = setTimeout(() => { this.limited = true; this.stop(); }, 20000);
      } catch (error) {
        this.cleanup();
        if (!this.cancelled) this.onerror?.({ error: error?.name === "NotAllowedError" ? "not-allowed" : "audio-capture" });
        this.onend?.();
      }
    }
    cleanup() {
      clearTimeout(this.limit);
      if (this.processor) { this.processor.onaudioprocess = null; this.processor.disconnect(); }
      if (this.source) this.source.disconnect();
      if (this.stream) this.stream.getTracks().forEach((track) => track.stop());
      if (this.context) this.context.close().catch(() => {});
    }
    async stop() {
      if (this.stopped) return;
      this.stopped = true;
      if (!this.context || !this.processor) return; // open() handles a still-pending permission request
      const rate = this.context.sampleRate, wav = pcmWav(this.chunks, rate);
      this.cleanup(); this.chunks = [];
      if (wav.byteLength <= 44) { this.onerror?.({ error: "no-speech" }); this.onend?.(); return; }
      try {
        this.controller = new AbortController();
        const response = await fetch("/api/voice/transcribe", { method: "POST", body: wav,
          headers: { "Content-Type": "audio/wav" }, signal: this.controller.signal });
        if (!response.ok) throw new Error("transcription unavailable");
        const result = await response.json();
        if (!this.cancelled && result.text) this.onresult?.({ resultIndex: 0,
          results: [{ isFinal: true, 0: { transcript: result.text }, length: 1 }] });
        else if (!this.cancelled) this.onerror?.({ error: "no-speech" });
      } catch (_) { if (!this.cancelled) this.onerror?.({ error: "service-unavailable" }); }
      this.onend?.();
    }
    abort() { this.cancelled = true; this.stopped = true; this.controller?.abort(); this.cleanup(); this.chunks = []; this.onend?.(); }
  }

  // One control starts/stops dictation when the field is empty and sends edited text otherwise.
  window.createVoiceInput = ({ input, button, status }) => {
    const BrowserRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const icons = {
      mic: '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" stroke="currentColor" stroke-width="1.8"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3m-3 0h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
      arrow: '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      stop: '<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor"/></svg>',
    };
    let backend = null, current = null, phase = "idle", limit = null;
    const message = (text) => { status.textContent = text; status.hidden = !text; };
    function update() {
      const hasText = Boolean(input.value.trim());
      button.innerHTML = current ? icons.stop : hasText ? icons.arrow : icons.mic;
      const label = current ? (phase === "processing" ? "Распознаю речь" : "Остановить запись") :
        hasText ? "Отправить" : "Голосовой ввод";
      button.setAttribute("aria-label", label);
      button.title = label;
      button.classList.toggle("recording", Boolean(current) && phase !== "processing");
      button.dataset.listening = String(Boolean(current) && phase !== "processing");
    }
    function hint() {
      if (current) return;
      if (backend?.backend === "gigaam") {
        message(backend.status === "ready" ? "Голос распознаётся на сервере приложения (до 20 секунд)." :
          "Модель голоса загружается или недоступна; текстовый ввод работает.");
      } else {
        message(BrowserRecognition && window.isSecureContext ?
          "Аудио может отправляться сервису распознавания браузера." : "Голосовой ввод недоступен; можно написать сообщение.");
      }
    }
    async function checkBackend() {
      try {
        const response = await fetch("/api/voice", { cache: "no-store" });
        backend = response.ok ? await response.json() : { backend: "browser" };
      } catch (_) { backend = { backend: "browser" }; }
      hint();
      if (backend.backend === "gigaam" && backend.status === "loading") setTimeout(checkBackend, 4000);
    }
    function cancel() {
      clearTimeout(limit); limit = null;
      const recognition = current; current = null; phase = "idle";
      if (recognition) { try { recognition.abort(); } catch (_) { /* already stopped */ } }
      update(); hint();
    }
    function toggle() {
      if (current) {
        if (phase !== "processing") current.requestStop();
        return;
      }
      if (!backend) { message("Проверяю доступность голосового ввода. Попробуйте ещё раз."); return; }
      const useLocal = backend.backend === "gigaam";
      const Recognition = useLocal ? LocalRecognition : BrowserRecognition;
      const available = window.isSecureContext && Recognition && (!useLocal ||
        (backend.status === "ready" && navigator.mediaDevices?.getUserMedia && (window.AudioContext || window.webkitAudioContext)));
      if (!available) {
        message("Голосовой ввод недоступен в этом браузере или соединении; можно написать сообщение.");
        return;
      }
      const recognition = new Recognition();
      current = recognition; phase = "starting"; update();
      recognition.lang = "ru-RU"; recognition.continuous = false;
      recognition.interimResults = false; recognition.maxAlternatives = 1;
      let lastFinal = -1, failed = false, stopRequested = false;
      recognition.onstart = () => {
        if (current !== recognition) return;
        if (stopRequested) { try { recognition.stop(); } catch (_) {} return; }
        phase = "listening"; update();
        message(useLocal ? "Слушаю. Нажмите ещё раз, чтобы остановить запись; звук распознаётся на сервере приложения." :
          "Слушаю. Аудио может отправляться сервису распознавания браузера.");
      };
      recognition.onresult = (event) => {
        if (current !== recognition) return;
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          if (!result.isFinal || i <= lastFinal) continue;
          const transcript = String(result[0]?.transcript || "").trim();
          if (transcript) input.value = [input.value.trim(), transcript].filter(Boolean).join(" ");
          lastFinal = i;
        }
        input.dispatchEvent(new Event("input", { bubbles: true }));
        message((recognition.limited ? "Достигнут лимит 20 секунд. " : "") +
          "Текст добавлен. Проверьте его и нажмите «Отправить».");
      };
      recognition.onerror = (event) => {
        if (current !== recognition) return;
        failed = true;
        message(event.error === "not-allowed" || event.error === "service-not-allowed" ?
          "Нет разрешения на микрофон или сервис распознавания. Можно написать сообщение." :
          "Не удалось распознать речь. Попробуйте ещё раз или напишите сообщение.");
      };
      recognition.onend = () => {
        if (current !== recognition) return;
        clearTimeout(limit); limit = null; current = null; phase = "idle"; update();
        if (!failed && lastFinal < 0) message("Речь не распознана. Попробуйте ещё раз или напишите сообщение.");
      };
      recognition.requestStop = () => {
        if (stopRequested) return;
        stopRequested = true; phase = "processing"; update(); message("Распознаю речь…");
        try { recognition.stop(); } catch (_) { /* onstart will stop it once ready */ }
      };
      try {
        message(useLocal ? "Включаю микрофон. Звук распознаётся на сервере приложения." :
          "Включаю микрофон. Аудио может отправляться сервису браузера.");
        recognition.start();
        limit = setTimeout(() => { if (current === recognition) { recognition.limited = true; recognition.requestStop(); } }, 20000);
      } catch (_) {
        current = null; phase = "idle"; update(); message("Не удалось начать запись. Можно написать сообщение.");
      }
    }
    input.addEventListener("input", update);
    update(); message("Проверяю доступность голосового ввода…"); checkBackend();
    return { toggle, update, cancel, isActive: () => Boolean(current), clearStatus: () => message("") };
  };
})();
