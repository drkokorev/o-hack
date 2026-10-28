/* Small local illustrations, selected by events.json. No external assets. */
const ICONS = {
  race: '<path fill="#dc5444" d="M4 15h2l2-4 4-1 3-4h2l1 4 3 1 1 4h2v3H4z"/><path fill="#fff" d="M13 10l2-3h1l1 3z"/><circle cx="8" cy="18" r="2.5" fill="#263c48"/><circle cx="20" cy="18" r="2.5" fill="#263c48"/>',
  sport: '<circle cx="14" cy="13" r="9" fill="#fff" stroke="#344650" stroke-width="1.5"/><path d="m14 8 3 2-1 4h-4l-1-4 3-2Zm-5 7-2 2m12-2 2 2M14 5v3m-2 6-2 3m6-3 2 3" fill="none" stroke="#344650" stroke-width="1.3"/>',
  music: '<path d="M12 7v11a3 3 0 1 1-2-2.8V6l11-2v11a3 3 0 1 1-2-2.8V7z" fill="#6558a6"/>',
  art: '<path d="M14 4c-6 0-10 4-10 9s4 9 9 9c2 0 3-1 3-2 0-2-1-2-1-3 0-1 1-2 3-2h2c2 0 4-1 4-3 0-4-4-8-10-8z" fill="#df9d54"/><circle cx="9" cy="11" r="1.4" fill="#3558af"/><circle cx="13" cy="8" r="1.4" fill="#c95950"/><circle cx="18" cy="9" r="1.4" fill="#498673"/>',
  nature: '<path d="M5 19C5 9 11 5 22 5c0 10-4 17-12 16-2 0-4-1-5-2Z" fill="#5e9b7b"/><path d="M7 21c3-4 6-7 12-11" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round"/>',
  tech: '<rect x="7" y="6" width="14" height="14" rx="3" fill="#5d76b9"/><path d="M11 3v3m6-3v3M11 20v3m6-3v3M4 10h3m-3 6h3m14-6h3m-3 6h3" stroke="#405784" stroke-width="1.6" stroke-linecap="round"/><rect x="11" y="10" width="6" height="6" rx="1" fill="#e7efff"/>',
  film: '<rect x="4" y="9" width="20" height="13" rx="2" fill="#52647a"/><path d="m4 8 19-4 1 4-20 4z" fill="#e6b75e"/><path d="m9 7 2 3m5-5 2 3" stroke="#fff" stroke-width="2"/>',
  festive: '<path d="m14 3 5 7h-2l4 6h-3l4 5H6l4-5H7l4-6H9z" fill="#5c967a"/><path d="M14 21v3" stroke="#9b6941" stroke-width="3"/><circle cx="14" cy="13" r="1.3" fill="#f4c15c"/>',
  bicycle: '<g fill="none" stroke="#344650" stroke-width="1.8"><circle cx="7" cy="19" r="5"/><circle cx="21" cy="19" r="5"/><path d="m7 19 5-8 4 8H7l5-8h5l4 8m-10-9h3m3 0h3" stroke="#d24f45"/></g>',
  sailing: '<path d="M3 19h22l-3 4H7z" fill="#3153aa"/><path d="M13 3v15h9z" fill="#e3ae4c"/><path d="M11 6 5 18h6z" fill="#d8d4c2"/>',
  surfing: '<path d="M4 19c3-2 5-2 8 0s5 2 8 0 5-2 6-1" fill="none" stroke="#3153aa" stroke-width="2"/><path d="M6 12c3-5 13-7 16-4-3 5-13 8-16 4z" fill="#e3ae4c"/>',
  flower: '<path d="M14 25V14" stroke="#5d9c7a" stroke-width="2"/><g fill="#df5147"><circle cx="14" cy="5" r="3"/><circle cx="9" cy="8" r="3"/><circle cx="19" cy="8" r="3"/><circle cx="10" cy="13" r="3"/><circle cx="18" cy="13" r="3"/></g><circle cx="14" cy="10" r="3" fill="#e3ae4c"/>',
  book: '<path d="M3 5c5-2 8-1 11 1v17c-3-2-6-3-11-1zm22 0c-5-2-8-1-11 1v17c3-2 6-3 11-1z" fill="#d8d4c2" stroke="#3153aa" stroke-width="1.5"/>',
  food: '<circle cx="12" cy="15" r="8" fill="#e3ae4c"/><circle cx="12" cy="15" r="4" fill="#df5147"/><path d="M23 4v19m-3-19v6h6V4" fill="none" stroke="#344650" stroke-width="1.6"/>',
  paw: '<g fill="#e3ae4c"><ellipse cx="14" cy="18" rx="6" ry="5"/><circle cx="6" cy="10" r="3"/><circle cx="11" cy="6" r="3"/><circle cx="17" cy="6" r="3"/><circle cx="22" cy="10" r="3"/></g>',
  culture: '<path d="M5 7c4-2 8-2 12 0v5c0 5-3 8-6 9-3-1-6-4-6-9z" fill="#d78b77"/><path d="M17 8c2 0 4 .3 6 1v4c0 4-2 7-5 8-2-.5-3-1.5-4-3" fill="#e6bc63"/><path d="M8 11h1m4 0h1m-6 4c2 2 4 2 6 0" fill="none" stroke="#643b42" stroke-width="1.5" stroke-linecap="round"/>'
};

export function eventIcon(kind) {
  const illustration = document.createElement("span");
  illustration.className = "event-illustration";
  illustration.setAttribute("aria-hidden", "true");
  // The inserted markup comes exclusively from the local constant above.
  const icon = Object.hasOwn(ICONS, kind) ? ICONS[kind] : ICONS.art;
  illustration.innerHTML = `<svg viewBox="0 0 28 28" width="28" height="28" aria-hidden="true">${icon}</svg>`;
  return illustration;
}
