(() => {
  "use strict";
  const script = document.currentScript;
  if (!script || !script.src || document.getElementById("o-trip-widget")) return;
  const service = new URL(script.src).origin;
  const root = document.createElement("div");
  root.id = "o-trip-widget";
  Object.assign(root.style, { position: "fixed", right: "16px", bottom: "16px", zIndex: "2147483000",
    display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "10px" });
  const frame = document.createElement("iframe");
  frame.title = "Помощник в планировании поездки";
  frame.src = `${service}/static/widget.html`;
  frame.referrerPolicy = "no-referrer";
  frame.allow = "microphone";
  frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
  frame.hidden = true;
  Object.assign(frame.style, { width: "min(390px, calc(100vw - 32px))", height: "min(620px, calc(100dvh - 100px))",
    border: "1px solid #e5e5e5", borderRadius: "24px", background: "white", boxShadow: "0 18px 60px #2d313733" });
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.textContent = "Помочь с поездкой";
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-label", "Открыть помощника по поездкам");
  Object.assign(toggle.style, { border: "0", borderRadius: "999px", padding: "14px 20px", minHeight: "48px",
    background: "#0e41d2", color: "white", font: "600 15px system-ui, sans-serif", cursor: "pointer",
    boxShadow: "0 8px 24px #0e41d244" });
  toggle.addEventListener("click", () => {
    frame.hidden = !frame.hidden;
    if (frame.hidden && frame.contentWindow) frame.contentWindow.postMessage({ type: "odin-widget-hidden" }, service);
    toggle.textContent = frame.hidden ? "Помочь с поездкой" : "Закрыть";
    toggle.setAttribute("aria-expanded", String(!frame.hidden));
    toggle.setAttribute("aria-label", frame.hidden ? "Открыть помощника по поездкам" : "Закрыть помощника по поездкам");
    if (!frame.hidden) frame.focus();
  });
  root.append(frame, toggle);
  if (document.body) document.body.append(root);
  else document.addEventListener("DOMContentLoaded", () => document.body.append(root), { once: true });
})();
