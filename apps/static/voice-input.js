/* Optional browser recognition: long-press send to dictate; review before sending. */
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

  window.attachVoiceInput = ({ input, button, status, form }) => {
    const BrowserRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let backend = null;
    let press = null, timer = null, current = null, suppressClick = false;

    const updateHint = () => {
      if (current) return;
      if (backend?.backend === "gigaam") {
        status.textContent = backend.status === "ready"
          ? "Удерживайте кнопку отправки для голоса (до 20 секунд). Звук распознаётся на сервере приложения."
          : "Локальная модель голоса загружается или недоступна; текстовый ввод работает.";
      } else {
        status.textContent = BrowserRecognition && window.isSecureContext
          ? "Удерживайте кнопку отправки для голоса. Аудио может отправляться сервису браузера."
          : "Голосовой ввод недоступен; можно написать сообщение.";
      }
    };
    const checkBackend = async () => {
      try {
        const response = await fetch("/api/voice", { cache: "no-store" });
        backend = response.ok ? await response.json() : { backend: "browser" };
      } catch (_) { backend = { backend: "browser" }; }
      updateHint();
      if (backend.backend === "gigaam" && backend.status === "loading") setTimeout(checkBackend, 4000);
    };
    checkBackend();

    const setListening = (active) => {
      button.dataset.listening = String(active);
      if (active) status.textContent = "Слушаю. Отпустите кнопку, чтобы закончить.";
    };
    const cancel = () => {
      clearTimeout(timer); timer = null; press = null;
      if (current) {
        const recognition = current; current = null;
        try { recognition.abort(); } catch (_) { /* already stopped */ }
      }
      setListening(false); status.textContent = "";
    };
    const start = () => {
      if (!backend) { status.textContent = "Проверяю доступность голосового ввода; удерживайте кнопку ещё раз."; return; }
      const useLocal = backend.backend === "gigaam";
      const Recognition = useLocal ? LocalRecognition : BrowserRecognition;
      const available = window.isSecureContext && Recognition && (!useLocal ||
        (backend.status === "ready" && navigator.mediaDevices?.getUserMedia && (window.AudioContext || window.webkitAudioContext)));
      if (!available) {
        status.textContent = "Голосовой ввод недоступен в этом браузере или соединении; можно написать сообщение.";
        return;
      }
      const recognition = new Recognition();
      current = recognition;
      recognition.lang = "ru-RU";
      recognition.continuous = true;
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      let lastFinal = -1, failed = false, stopRequested = false;
      recognition.onstart = () => {
        if (current !== recognition) return;
        if (stopRequested) {
          try { recognition.stop(); } catch (_) { /* already stopped */ }
        } else setListening(true);
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
        status.textContent = (recognition.limited ? "Достигнут лимит 20 секунд. " : "") +
          "Текст добавлен. Проверьте его и нажмите «Отправить».";
      };
      recognition.onerror = (event) => {
        if (current !== recognition) return;
        failed = true; setListening(false);
        status.textContent = event.error === "not-allowed" || event.error === "service-not-allowed"
          ? "Нет разрешения на микрофон или сервис распознавания. Можно написать сообщение."
          : "Не удалось распознать речь. Попробуйте ещё раз или напишите сообщение.";
      };
      recognition.onend = () => {
        if (current !== recognition) return;
        current = null; setListening(false);
        if (!failed && lastFinal < 0) status.textContent = "Речь не распознана. Попробуйте ещё раз или напишите сообщение.";
      };
      recognition.requestStop = () => {
        stopRequested = true; setListening(false);
        status.textContent = "Распознаю речь…";
        try { recognition.stop(); } catch (_) { /* onstart will stop it once ready */ }
      };
      try { status.textContent = "Включаю микрофон…"; recognition.start(); }
      catch (_) { current = null; setListening(false); status.textContent = "Не удалось начать запись. Можно написать сообщение."; }
    };
    const arm = (kind, id) => {
      if (button.disabled || press || current) return;
      press = { kind, id, held: false };
      timer = setTimeout(() => {
        if (!press) return;
        press.held = true;
        start();
      }, 500);
    };
    const finish = (kind, id, cancelled = false) => {
      if (!press || press.kind !== kind || press.id !== id) return;
      clearTimeout(timer); timer = null;
      const held = press.held; press = null;
      if (!held) return;
      if (cancelled) { cancel(); return; }
      suppressClick = true;
      // A pointer/keyboard release normally generates a click immediately after this handler.
      setTimeout(() => { suppressClick = false; }, 1000);
      if (current) current.requestStop();
    };

    button.addEventListener("pointerdown", (event) => {
      if (!event.isPrimary || event.button !== 0) return;
      arm("pointer", event.pointerId);
      try { button.setPointerCapture(event.pointerId); } catch (_) { /* optional */ }
    });
    button.addEventListener("pointerup", (event) => finish("pointer", event.pointerId));
    button.addEventListener("pointercancel", (event) => finish("pointer", event.pointerId, true));
    button.addEventListener("keydown", (event) => {
      if (event.code === "Space" && !event.repeat) arm("keyboard", "Space");
    });
    button.addEventListener("keyup", (event) => {
      if (event.code === "Space") finish("keyboard", "Space");
    });
    button.addEventListener("contextmenu", (event) => { if (press?.held) event.preventDefault(); });
    button.addEventListener("click", (event) => {
      if (!suppressClick) return;
      suppressClick = false; event.preventDefault(); event.stopImmediatePropagation();
    }, true);
    form.addEventListener("submit", cancel, true);
    status.textContent = "Проверяю доступность голосового ввода…";
    return { cancel };
  };
})();
