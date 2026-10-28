/* A single control: microphone when empty, send when there is text. */
window.createVoiceInput = function createVoiceInput({input, button, status}) {
  const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null, active = false;
  const mic = '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" stroke="currentColor" stroke-width="1.8"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3m-3 0h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
  const arrow = '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const stop = '<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor"/></svg>';
  function update() {
    const hasText = Boolean(input.value.trim());
    button.innerHTML = active ? stop : hasText ? arrow : mic;
    button.setAttribute("aria-label", active ? "Остановить запись" : hasText ? "Отправить" : "Голосовой ввод");
    button.title = active ? "Остановить запись" : hasText ? "Отправить" : "Голос распознаёт браузер";
    button.classList.toggle("recording", active);
  }
  function message(text) { status.textContent = text; status.hidden = !text; }
  function toggle() {
    if (active) { recognition.stop(); return; }
    if (!Speech || !window.isSecureContext) { message("Голосовой ввод в этом браузере недоступен."); input.focus(); return; }
    try {
      recognition = new Speech(); recognition.lang = "ru-RU"; recognition.interimResults = false;
      recognition.continuous = false; active = true; update();
      message("Слушаю… Голос распознаёт браузер.");
      recognition.onresult = (event) => {
        const parts = [];
        for (let i = event.resultIndex; i < event.results.length; i++) {
          if (event.results[i].isFinal) parts.push(event.results[i][0].transcript.trim());
        }
        if (parts.length) { input.value = [input.value.trim(), ...parts].filter(Boolean).join(" "); input.dispatchEvent(new Event("input", {bubbles:true})); }
      };
      recognition.onerror = (event) => {
        const errors = { "not-allowed":"Доступ к микрофону не разрешён.", "no-speech":"Речь не распознана. Попробуйте ещё раз.",
          "network":"Не удалось распознать голос. Можно написать сообщение." };
        message(errors[event.error] || "Не удалось распознать голос. Можно написать сообщение.");
      };
      recognition.onend = () => { active = false; update(); if (input.value.trim()) message(""); input.focus(); };
      recognition.start();
    } catch (_) { active = false; update(); message("Не удалось включить микрофон."); }
  }
  input.addEventListener("input", update); update();
  return { toggle, update, isActive: () => active, clearStatus: () => message("") };
};
