/* Presentation preferences only; these do not change the agent's trip state. */
window.createPreferences = function createPreferences(map) {
  const country = document.getElementById("country");
  const currency = document.getElementById("currency");
  const note = document.getElementById("exchange-note");
  const original = new WeakMap();
  let rates = null;
  const euro = new Set("AD AT BE CY DE EE ES FI FR GR HR IE IT LT LU LV MC ME MT NL PT SI SK SM VA".split(" "));
  const read = (key) => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const save = (key, value) => { try { localStorage.setItem(key, value); } catch (_) {} };
  const currencyFor = (code) => euro.has(code) ? "EUR" : code === "US" ? "USD" : "RUB";
  let manualCurrency = read("odin.currency");
  const manualCountry = read("odin.country");

  function convert(value) {
    if (currency.value === "RUB" || !rates || !rates.rub_per_unit[currency.value]) return null;
    return new Intl.NumberFormat("ru-RU", { style: "currency", currency: currency.value,
      maximumFractionDigits: 0 }).format(value / rates.rub_per_unit[currency.value]);
  }
  function apply() {
    document.querySelectorAll("#view, #conditions, #log .bot, #say").forEach((root) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach((node) => {
        if (!original.has(node)) original.set(node, node.nodeValue);
        const text = original.get(node);
        node.nodeValue = text.replace(/((?:\d{1,3}(?:[\s\u00a0\u202f]\d{3})+|\d+)(?:[,.]\d{1,2})?)\s*₽/g, (match, amount) => {
          const value = Number(amount.replace(/[\s\u00a0\u202f]/g, "").replace(",", "."));
          const changed = convert(value); return changed ? `≈ ${changed}` : match;
        });
      });
    });
    document.querySelectorAll("[data-rub-price]").forEach((node) => {
      if (!node.dataset.originalLabel) node.dataset.originalLabel = node.textContent;
      const changed = convert(Number(node.dataset.rubPrice));
      node.textContent = changed ? `≈ ${changed}` : node.dataset.originalLabel;
    });
    currency.title = currency.value === "RUB" ? "Валюта демонстрационных цен" :
      "Примерный пересчёт демо-цен по курсу ЦБ РФ на 28.10.2026; бюджет в диалоге указывайте в рублях";
  }
  currency.addEventListener("change", () => { manualCurrency = currency.value; save("odin.currency", manualCurrency); apply(); });
  country.addEventListener("change", () => {
    if (!country.value) return;
    save("odin.country", country.value); map.setCountry(country.value, true);
    if (!manualCurrency) { currency.value = currencyFor(country.value); apply(); }
  });
  if (["RUB", "EUR", "USD"].includes(manualCurrency)) currency.value = manualCurrency;
  Promise.all([
    fetch("/static/country-options.json").then((r) => r.json()),
    fetch("/api/visitor-country", { cache: "no-store" }).then((r) => r.ok ? r.json() : null).catch(() => null),
    fetch("/static/exchange-rates.json").then((r) => r.json()).catch(() => null),
  ]).then(([names, location, exchange]) => {
    rates = exchange;
    Object.entries(names).sort((a, b) => a[1].localeCompare(b[1], "ru")).forEach(([code, name]) => {
      const option = document.createElement("option"); option.value = code; option.textContent = name; country.append(option);
    });
    const selected = manualCountry || location?.country_code;
    if (selected && names[selected]) {
      country.value = selected; map.setCountry(selected, !!manualCountry);
      if (!manualCountry) country.title = "Страна определена приблизительно по IP; можно изменить";
      if (!manualCurrency) currency.value = currencyFor(selected);
    }
    if (rates) {
      note.append("Пересчёт демо-сумм приблизительный: ", Object.assign(document.createElement("a"),
        { href: rates.url, target: "_blank", rel: "noopener", textContent: "курс ЦБ РФ на 28.10.2026" }),
        ". Бюджет в разговоре пока указывается в рублях.");
    } else {
      currency.value = "RUB"; currency.disabled = true;
      note.textContent = "Курс недоступен; суммы показаны в рублях.";
    }
    apply();
  }).catch(() => { country.disabled = true; currency.value = "RUB"; currency.disabled = true; });
  return { apply, currency: () => currency.value };
};
