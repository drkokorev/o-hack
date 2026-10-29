/* One readable sentence; values remain server-owned and each opens its own editor. */
window.createTripSentence = ({container, onEdit}) => {
  const plural = (n, one, few, many) => n % 10 === 1 && n % 100 !== 11 ? one :
    n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? few : many;
  const months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
  const shortMonths = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
  // Explicit display forms for catalog names; never guess a case for arbitrary map points.
  const directions = {
    'Москва':'в Москву', 'Горный Алтай':'на Горный Алтай', 'Байкал (Иркутск)':'на Байкал (Иркутск)',
    'Мурманск и Териберка':'в Мурманск и Териберку', 'Камчатка':'на Камчатку', 'Карелия':'в Карелию',
    'Анталья':'в Анталью', 'Хургада':'в Хургаду', 'Пхукет':'на Пхукет', 'Санья (Хайнань)':'в Санью (Хайнань)',
    'Мальдивы':'на Мальдивы', 'Шри-Ланка':'на Шри-Ланку', 'Бали':'на Бали', 'Гоа':'в Гоа',
    'Будва':'в Будву', 'Кипр (Айя-Напа)':'на Кипр (Айя-Напа)', 'Крит':'на Крит', 'Барселона':'в Барселону',
    'Прага':'в Прагу', 'Фукуок':'на Фукуок', 'Доха':'в Доху', 'Акаба':'в Акабу', 'Занзибар':'на Занзибар',
    'Сейшелы':'на Сейшелы', 'Маврикий':'на Маврикий', 'Пунта-Кана':'в Пунта-Кану', 'Самара':'в Самару', 'Уфа':'в Уфу'
  };
  let locked = false;
  const control = (key, text, label, missing = false) => {
    const button = document.createElement('button');
    button.type = 'button'; button.className = `trip-word trip-word-${key}${missing ? ' is-missing' : ''}`;
    button.dataset.tripField = key; button.textContent = text; button.disabled = locked;
    button.setAttribute('aria-label', `${label}: ${text}. Изменить`);
    button.setAttribute('aria-haspopup', 'dialog');
    button.title = `Изменить: ${label.toLocaleLowerCase('ru')}`;
    button.onclick = () => onEdit(key);
    return button;
  };
  const date = (value, year = true, compact = false) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
    const [y, m, d] = value.split('-').map(Number);
    return months[m - 1] ? `${d} ${(compact ? shortMonths : months)[m - 1]}${year ? ` ${y}` : ''}` : null;
  };
  function render(data, info) {
    const s = data?.trip_summary || {}, understood = data?.understood || [];
    const known = (info?.places || []).find(p => p.name === s.destination) ||
      (!s.destination && (info?.places || []).find(p => understood.includes(p.name)));
    const destination = s.destination || known?.name;
    const hidden = new Set();
    const remove = (text) => { if (text) hidden.add(text); };
    const parts = [];
    const put = (separator, key, value, label, missing = false) => {
      if (parts.length) parts.push(separator);
      parts.push(control(key, value, label, missing));
    };
    const scope = s.search_scope;
    if (!['hotel_only', 'transfer_only', 'split_hotel'].includes(scope)) {
      const origin = (info?.origins || []).find(o => o.name === s.origin);
      put('', 'origin', s.origin ? origin?.from || `откуда: ${s.origin}` : 'откуда?', 'Город отправления', !s.origin);
      if (s.origin) remove(`из: ${s.origin}`);
    }
    if (scope !== 'split_hotel') {
      const direction = destination ? directions[destination] || (known ? `в ${destination}` : `куда: ${destination}`) : 'куда?';
      put(' ', 'destination', direction, 'Направление', !destination);
      remove(destination);
    }
    const start = date(s.date_from, s.date_from?.slice(0, 4) !== s.date_to?.slice(0, 4)), end = date(s.date_to);
    if (scope !== 'transfer_only') {
      const dates = start && end ? `${date(s.date_from, s.date_from.slice(0,4)!==s.date_to.slice(0,4), true)} — ${date(s.date_to, true, true)}` : s.date_from ? `с ${date(s.date_from, true, true)}` : 'когда?';
      put(', ', 'dates', dates, 'Даты поездки', !s.date_from);
      if (start && end) remove(`${start} — ${end}`);
      else if (s.date_from) remove(`начало: ${date(s.date_from)}`);
      if (s.nights && !['flight_only', 'train_only'].includes(scope)) {
        const nights = `${s.nights} ${plural(s.nights, 'ночь', 'ночи', 'ночей')}`;
        put(' ', 'duration', `на ${nights}`, 'Длительность'); remove(nights);
      }
    }
    const people = [];
    if (s.adults) {
      const adults = `${s.adults} ${plural(s.adults, 'взрослый', 'взрослых', 'взрослых')}`;
      people.push(adults); remove(adults);
    }
    if (s.children) {
      const children = `${s.children} ${plural(s.children, 'ребёнок', 'ребёнка', 'детей')}`;
      people.push(children); remove(children);
    }
    put(', ', 'people', people.join(' и ') || 'кто едет?', 'Путешественники', !people.length);
    const money = s.budget_total ? new Intl.NumberFormat('ru-RU').format(s.budget_total) : null;
    put(', ', 'budget', money ? `до ${money} ₽ на всех` : 'бюджет?', 'Общий бюджет', !money);
    if (money) remove(`бюджет ${money} ₽`);
    container.replaceChildren('Едем ', ...parts, '.');
    // Only exact duplicates of represented values disappear. Ages, transport,
    // per-person budgets, accessibility needs and assumptions stay available.
    const normalize = value => String(value).replace(/\s*\(примерно по IP\)/g, '').replace(/[\s\u00a0\u202f]+/g, ' ').trim();
    const duplicates = new Set([...hidden].map(normalize));
    return understood.filter(value => !duplicates.has(normalize(value)));
  }
  function setBusy(value) {
    locked = value;
    container.querySelectorAll('button').forEach(button => { button.disabled = value; });
  }
  return {render, setBusy};
};

/* Preview at most two concrete wishes. Every remaining wish stays in the disclosure.
   Weather leads when present, then travel restrictions, then general preferences.
   This ordering is a display rule, not a claim about learned user priorities. */
window.renderTripWishes = ({values, assumptions, onEdit, busy}) => {
  const temperatures = new Map(), all = [];
  for (const text of values) {
    const match = /^(воздух|море) (от|до) (-?[\d.,]+) °C$/.exec(text);
    if (!match) { all.push({text, assumed:false}); continue; }
    const [,kind,bound,value] = match;
    if (!temperatures.has(kind)) temperatures.set(kind, {});
    temperatures.get(kind)[bound] = value;
  }
  for (const [kind, limits] of temperatures) {
    const range = limits.от && limits.до ? `${limits.от}–${limits.до}` : limits.от ? `от ${limits.от}` : `до ${limits.до}`;
    const editRange = [limits.от ? `от ${limits.от}` : '', limits.до ? `до ${limits.до}` : ''].filter(Boolean).join(' ');
    all.push({text:`${kind} ${range} °C`, weather:true, editText:`Температура ${kind === 'воздух' ? 'воздуха' : 'моря'} ${editRange} градусов`});
  }
  all.push(...assumptions.map(text=>({text, assumed:true})));
  const priority = item => item.assumed ? 5 : item.weather ? 0 :
    /без пересадок|с питомцем|безбарьер|коляск|пандус|аллерг|без глютена/.test(item.text) ? 1 :
    /завтрак|включено|питание|от \d★/.test(item.text) ? 2 : 3;
  const sorted = all.map((item,index)=>({...item,index})).sort((a,b)=>priority(a)-priority(b)||a.index-b.index);
  const button = (item, preview = false) => {
    const node = document.createElement('button'); node.type = 'button';
    node.className = preview ? 'trip-highlight' : 'chip';
    if(item.assumed) node.classList.add('assumed');
    node.textContent = item.assumed ? `Предположение: ${item.text}` : item.text;
    node.setAttribute('aria-label', `Изменить условие: ${node.textContent}`);
    node.setAttribute('aria-haspopup','dialog'); node.disabled = busy;
    node.onclick = () => onEdit(item.weather ? 'weather' : 'other', item.editText || item.text);
    return node;
  };
  const preview = sorted.slice(0,2), remaining = sorted.slice(2);
  document.getElementById('condition-highlights').replaceChildren(...preview.map(item=>button(item,true)));
  document.getElementById('conditions').replaceChildren(...remaining.map(item=>button(item)));
  const details = document.getElementById('all-conditions'); details.hidden = !remaining.length;
  details.querySelector('summary').textContent = `Ещё ${remaining.length}`;
};
