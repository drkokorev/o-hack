/* Apply before paint; the conversation never changes the visual theme. */
(() => {
  let theme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  try { const saved = localStorage.getItem('odin.theme'); if (['light','dark'].includes(saved)) theme = saved; } catch (_) {}
  const apply = (value) => {
    document.documentElement.dataset.theme = value;
    const button = document.getElementById('theme-toggle');
    if (button) {
      button.setAttribute('aria-label', value === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему');
      button.title = button.getAttribute('aria-label');
      button.innerHTML = value === 'dark' ? '<svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5"/></svg>' : '<svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.1A8.5 8.5 0 0 1 9.9 4a8.5 8.5 0 1 0 10.2 10.1Z"/></svg>';
      button.setAttribute('aria-pressed', String(value === 'dark'));
    }
    document.dispatchEvent(new CustomEvent('odin:theme', {detail:{theme:value}}));
  };
  apply(theme);
  document.addEventListener('DOMContentLoaded', () => {
    apply(theme);
    document.getElementById('theme-toggle')?.addEventListener('click', () => {
      theme = theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('odin.theme', theme); } catch (_) {}
      apply(theme);
    });
  }, {once:true});
})();
