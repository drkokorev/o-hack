/* Keep the conversation readable while retaining the agent's complete answer. */
window.renderTravelReply = function renderTravelReply(container, reply, kind) {
  const text = String(reply || "");
  let compact = text;
  if (["ideas", "destinations", "packages", "cart", "hotels"].includes(kind)) {
    const blocks = text.split(/\n\s*\n/);
    const kept = blocks.filter((block) => !/^\s*\d+\.\s/.test(block) &&
      // Dates already appear in the chosen parameters and the result introduction.
      !(kind === 'packages' && /^Учёл даты поездки:[^\n]+\.$/.test(block.trim())));
    // If the response has no separable option blocks, keep it intact.
    if (kept.length && kept.length < blocks.length) compact = kept.join("\n\n");
  }
  container.textContent = compact;
  if (compact !== text) {
    const details = document.createElement("details");
    details.className = "full-reply";
    const summary = document.createElement("summary");
    summary.textContent = "Показать полный ответ";
    const full = document.createElement("div");
    full.textContent = text;
    details.append(summary, full);
    container.append(details);
  }
};
