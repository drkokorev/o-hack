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
          const data = event.inputBuffer.getChannelData(0);
          if (!this.stopped) {
            this.chunks.push(new Float32Array(data));
            let sum = 0; for (let i = 0; i < data.length; i += 4) sum += data[i] * data[i];
            this.onlevel?.(Math.sqrt(sum / (data.length / 4)));
          }
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
  // dedicated: a separate microphone button next to «Send» — click to record, click again to review the text,
  // or press «Send» while recording to transcribe and send at once (finish()).
  window.createVoiceInput = ({ input, button, status, holdToTalk = false, dedicated = false }) => {
    const BrowserRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const icons = {
      mic: '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" stroke="currentColor" stroke-width="1.8"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3m-3 0h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
      arrow: '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      stop: '<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor"/></svg>',
    };
    let backend = null, current = null, phase = "idle", limit = null, ticker = null;
    let pressed = false, held = false, pointerId = null, holdTimer = null, suppressUntil = 0, mode = "toggle", startedAt = 0;
    let disclosedBackend = null, after = null;
    // Полоска уровня звука во время записи (как в Claude): последние значения громкости столбиками
    const wave = dedicated ? document.getElementById("voice-wave") : null, BARS = 28;
    if (wave) wave.replaceChildren(...Array.from({ length: BARS }, () => document.createElement("i")));
    let levels = [];
    const showLevel = (value) => {
      if (!wave) return;
      levels = [...levels, Math.min(1, value * 9)].slice(-BARS);
      [...wave.children].forEach((bar, i) => {
        const v = levels[i - (BARS - levels.length)];
        bar.style.height = v === undefined ? "" : `${Math.max(3, Math.round(v * 22))}px`;
      });
    };
    const setWave = (on) => { if (wave) { wave.hidden = !on; input.classList.toggle("dictating", on); if (!on) { levels = []; showLevel(0); levels = []; } } };
    const cancelButton = holdToTalk ? document.getElementById("voice-cancel") : null;
    const notifyAudio = (recording) => document.dispatchEvent(new CustomEvent("odin:recording", {detail:{recording}}));
    const message = (text) => { status.textContent = text; status.hidden = !text; };
    function update() {
      const hasText = Boolean(input.value.trim());
      button.innerHTML = current ? (phase === "listening" && mode === "hold" ? icons.mic : icons.stop) :
        (dedicated ? icons.mic : holdToTalk || hasText ? icons.arrow : icons.mic);
      const label = current ? (phase === "processing" ? "Распознаю речь" :
        dedicated ? "Остановить запись и вставить текст" : "Остановить запись") :
        dedicated ? "Голосовой ввод" :
        holdToTalk ? "Отправить сообщение. Удерживайте для диктовки" : hasText ? "Отправить" : "Голосовой ввод";
      button.setAttribute("aria-label", label);
      button.title = label;
      button.classList.toggle("recording", Boolean(current) && phase !== "processing");
      setWave(Boolean(current));
      if (wave) wave.classList.toggle("processing", phase === "processing");
      button.dataset.listening = String(Boolean(current) && phase === "listening");
      if (cancelButton) cancelButton.hidden = !current;
    }
    function hint() {
      if (current || holdToTalk || dedicated) return;
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
      clearTimeout(limit); clearInterval(ticker); clearTimeout(holdTimer); limit = null;
      pressed = false; held = false; after = null; notifyAudio(false);
      const recognition = current; current = null; phase = "idle";
      if (recognition) { try { recognition.abort(); } catch (_) { /* already stopped */ } }
      update(); message(""); hint();
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
      recognition.onlevel = showLevel;
      current = recognition; phase = "starting"; update();
      recognition.lang = "ru-RU"; recognition.continuous = false;
      recognition.interimResults = false; recognition.maxAlternatives = 1;
      let lastFinal = -1, failed = false, stopRequested = false;
      recognition.onstart = () => {
        if (current !== recognition) return;
        if (stopRequested) { try { recognition.stop(); } catch (_) {} return; }
        phase = "listening"; update();
        startedAt = performance.now(); notifyAudio(true);
        const finishHint = mode === "hold" ? "отпустите, чтобы закончить" :
          dedicated ? "■ — вставить текст, ↑ — сразу отправить" : "нажмите стрелку, чтобы закончить";
        const tick = () => message(`Запись ${Math.min(20,Math.floor((performance.now()-startedAt)/1000))} / 20 с · ${finishHint}`);
        tick(); ticker = setInterval(tick, 250);
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
        if (!after) message((recognition.limited ? "Достигнут лимит 20 секунд. " : "") +
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
        clearTimeout(limit); clearInterval(ticker); limit = null; current = null; phase = "idle"; notifyAudio(false); update();
        const then = after; after = null;
        if (!failed && lastFinal < 0) message("Речь не распознана. Попробуйте ещё раз или напишите сообщение.");
        else if (!failed && then) then();
      };
      recognition.requestStop = () => {
        if (stopRequested) return;
        stopRequested = true; clearInterval(ticker); notifyAudio(false);
        phase = "processing"; update(); message("Распознаю речь…");
        try { recognition.stop(); } catch (_) { /* onstart will stop it once ready */ }
      };
      try {
        message(useLocal ? "Включаю микрофон. Звук распознаётся на сервере приложения." :
          "Включаю микрофон. Аудио может отправляться сервису браузера.");
        recognition.start();
        limit = setTimeout(() => { if (current === recognition) { recognition.limited = true; recognition.requestStop(); } }, 20000);
      } catch (_) {
        current = null; phase = "idle"; clearInterval(ticker); notifyAudio(false); update(); message("Не удалось начать запись. Можно написать сообщение.");
      }
    }
    async function begin(requestedMode = "toggle") {
      if (button.disabled || current) return;
      mode = requestedMode;
      if (!backend) { message("Голос ещё загружается. Попробуйте через секунду."); return; }
      if ((holdToTalk || dedicated) && disclosedBackend !== backend.backend) {
        const dialog = document.getElementById("voice-dialog");
        document.getElementById("voice-disclosure").textContent = backend.backend === "gigaam"
          ? "Аудио будет отправлено на сервер приложения для распознавания."
          : "Аудио может передаваться сервису распознавания вашего браузера.";
        document.getElementById("voice-dismiss").onclick = () => dialog.close();
        document.getElementById("voice-allow").onclick = async () => {
          dialog.close(); disclosedBackend = backend.backend;
          if (!navigator.mediaDevices?.getUserMedia) { message("Микрофон недоступен. Можно написать сообщение."); return; }
          if (dedicated) { toggle(); return; }  // разрешение спросит сама запись
          try {
            const stream = await navigator.mediaDevices.getUserMedia({audio:true});
            stream.getTracks().forEach((track)=>track.stop());
            message("Микрофон готов. Удерживайте стрелку или выберите «Начать диктовку» в меню.");
          } catch (_) { message("Доступ к микрофону не получен. Текстовый ввод работает."); }
        };
        if (!dialog.open) dialog.showModal();
        return;
      }
      if (requestedMode === "hold" && !pressed) return;
      toggle();
    }
    if (dedicated) {
      button.addEventListener("click", () => { if (current) { if (phase !== "processing") current.requestStop(); } else begin("toggle"); });
    }
    if (holdToTalk || dedicated) {
      document.addEventListener("keydown",(event)=>{if(event.key==="Escape" && current){event.preventDefault();cancel();}});
      document.addEventListener("visibilitychange",()=>{if(document.hidden){clearTimeout(holdTimer);pressed=false;if(current)cancel();}});
      window.addEventListener("pagehide",cancel);
    }
    if (holdToTalk) {
      button.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || button.disabled || current) return;
        pressed = true; held = false; pointerId = event.pointerId;
        button.setPointerCapture?.(pointerId);
        holdTimer = setTimeout(()=>{if(pressed){held=true;suppressUntil=performance.now()+1000;begin("hold");}},350);
      });
      button.addEventListener("pointerup", (event) => {
        if(event.pointerId !== pointerId) return;
        clearTimeout(holdTimer); pressed=false;
        const rect=button.getBoundingClientRect();
        const outside=event.clientX<rect.left-12 || event.clientX>rect.right+12 || event.clientY<rect.top-12 || event.clientY>rect.bottom+12;
        if(held || outside) {
          suppressUntil=performance.now()+600;
          if(current && outside) cancel();
          else if(current && phase === "starting") { cancel(); message("Микрофон готовится. Попробуйте удержать стрелку ещё раз."); }
          else if(current && phase === "listening") current.requestStop();
        }
        held=false;pointerId=null;
      });
      button.addEventListener("pointercancel",()=>{clearTimeout(holdTimer);pressed=false;suppressUntil=performance.now()+600;if(current)cancel();});
      button.addEventListener("click",(event)=>{
        if(event.detail > 0 && performance.now()<suppressUntil){event.preventDefault();event.stopImmediatePropagation();}
      },true);
      button.addEventListener("contextmenu",(event)=>event.preventDefault());
    }
    input.addEventListener("input", update);
    // Stop recording, wait for the transcript, then call done() — «Send» pressed while dictating.
    function finish(done) {
      if (!current) { done(); return; }
      after = done;
      if (phase !== "processing") current.requestStop();
    }
    update(); if(!holdToTalk && !dedicated)message("Проверяю доступность голосового ввода…"); checkBackend();
    return { toggle, begin, finish, update, cancel, isActive: () => Boolean(current), clearStatus: () => message("") };
  };
})();
