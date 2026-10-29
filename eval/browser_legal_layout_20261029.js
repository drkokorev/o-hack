// playwright-cli -s=privacy run-code --filename eval/browser_legal_layout_20261029.js
async (page) => {
  await page.goto("http://localhost:8080");
  const results = [];
  for (const width of [390, 1024, 1440]) {
    await page.setViewportSize({width, height: 900});
    const footer = page.locator(".site-legal-footer");
    await footer.scrollIntoViewIfNeeded();
    const links = await footer.locator("a").evaluateAll((items) => items.map((a) => {
      const rect = a.getBoundingClientRect();
      const top = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return {text: a.textContent, clickable: top === a || a.contains(top)};
    }));
    const noOverflow = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
    results.push({width, links, no_horizontal_overflow: noOverflow});
    if (!noOverflow || links.some((a) => !a.clickable)) throw new Error(`Legal footer is inaccessible at ${width}px`);
  }
  return {results};
}
