  const log = document.getElementById("log"), input = document.getElementById("text"), form = document.getElementById("form");
  const voice = createVoiceInput({input, button:form.querySelector("button"), status:document.getElementById("voice-status")});
  window.addEventListener("message", (event) => {
    if (event.source === window.parent && event.data?.type === "odin-widget-hidden") voice.cancel();
  });
  let session = null, busy = false;
  function element(tag, className, text) {
    const node = document.createElement(tag); if (className) node.className = className;
    if (text != null) node.textContent = text; return node;
  }
  function message(text, user = false, kind = null) {
    const node = element("div", `message${user ? " user" : ""}`);
    if (user) node.textContent = text; else renderTravelReply(node, text, kind);
    log.append(node); log.scrollTop = log.scrollHeight;
  }
  function action(label, text) {
    const button = element("button", "action", label); button.type = "button";
    button.addEventListener("click", () => send(text)); return button;
  }
  function render(payload) {
    const p = payload || {}, items = p.items || [];
    const cards = element("div", "cards");
    if (["ideas", "destinations"].includes(p.kind)) items.forEach((d, i) => {
      const card = element("article", "card"); card.append(element("b", "", `${i + 1}. ${d.name}, ${d.country}`));
      if (d.total) card.append(element("p", "", `Демо-цена: от ${d.total}`));
      card.append(action("Хочу сюда", `давай ${d.name}`)); cards.append(card);
    });
    if (["packages", "tent_transport"].includes(p.kind)) items.forEach((item, i) => {
      const card = element("article", "card"); card.append(element("b", "", `${item.title || `Вариант ${i + 1}`} · ${item.total}`));
      card.append(element("p", "", "Цена и расписание демонстрационные"), action("Выбрать", `беру ${i + 1} вариант`)); cards.append(card);
    });
    if (["cart", "tent_cart"].includes(p.kind)) {
      const row = element("div", "actions"); row.append(action("Выбрать способ оплаты", "да, оформляй"), action("К вариантам", "нет")); cards.append(row);
    }
    if (p.kind === "payment") {
      const row = element("div", "actions"); row.append(action("Демо-карта", "оплата картой"), action("Демо-СБП", "оплата СБП"));
      if (p.method) row.append(action("Подтвердить демонстрацию", "да, подтверждаю"));
      row.append(action("В корзину", "нет")); cards.append(row);
    }
    if (cards.childNodes.length) log.append(cards);
    log.scrollTop = log.scrollHeight;
  }
  async function send(text) {
    text = String(text || "").trim(); if (!text || busy) return;
    if (voice.isActive()) voice.cancel();
    busy = true; form.querySelector("button").disabled = true; input.value = ""; voice.update(); message(text, true);
    try {
      const response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, session_id: session }) });
      if (!response.ok) throw new Error("unavailable");
      const data = await response.json(); session = data.session_id;
      message(data.reply || "", false, data.payload?.kind); render(data.payload);
    } catch (_) { if (!input.value) input.value = text; message("Не удалось отправить. Текст сохранён — попробуйте ещё раз."); }
    finally { busy = false; form.querySelector("button").disabled = false; voice.update(); input.focus(); }
  }
  form.addEventListener("submit", (event) => { event.preventDefault();
    if (voice.isActive() || !input.value.trim()) voice.begin(); else { voice.clearStatus(); send(input.value); }
  });
  input.disabled = false; form.querySelector("button").disabled = false; voice.update();
