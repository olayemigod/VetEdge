from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "vetedge/public/js/vetedge_postqa_navigation_hardening.js"
LOADER = ROOT / "vetedge/public/js/report_pdf_patch.js"


async def main() -> None:
	patch_source = PATCH.read_text(encoding="utf-8")
	loader_source = LOADER.read_text(encoding="utf-8")
	assert "vetedge_postqa_navigation_hardening.js?v=20260905-1" in loader_source

	html = """
<!doctype html>
<html>
<head>
<style>
body { margin: 0; font-family: sans-serif; }
.edge-app-shell { display: grid; grid-template-columns: 240px 1fr; min-height: 600px; }
.edge-sidebar { display: block; width: 240px; }
.edge-sidebar__section-toggle, .edge-sidebar-item, .edge-product-menu__trigger, .edge-product-menu__item { display: flex; width: 200px; min-height: 36px; }
.edge-topbar-actions { position: absolute; top: 8px; right: 8px; min-width: 100px; min-height: 44px; display: flex; }
.edge-icon { display: inline-block; width: 16px; height: 16px; }
.edge-product-menu { position: fixed; top: 56px; right: 8px; width: 320px; min-height: 180px; background: white; }
.edge-product-menu[hidden], .edge-sidebar__items[hidden] { display: none !important; }
</style>
</head>
<body>
<div class="edge-app-shell" data-edge-product="VetEdge">
  <aside class="edge-sidebar">
    <section class="edge-sidebar__section is-expanded">
      <button class="edge-sidebar__section-toggle" type="button" aria-expanded="true">
        <span class="edge-icon">H</span><span>Home</span><span class="edge-icon">V</span>
      </button>
      <div class="edge-sidebar__items">
        <button class="edge-sidebar-item active" type="button"><span class="edge-sidebar-item__label">Veterinary Home</span></button>
      </div>
    </section>
    <section class="edge-sidebar__section">
      <button class="edge-sidebar__section-toggle" type="button" aria-expanded="false"><span>Dashboard</span><span class="edge-icon">V</span></button>
    </section>
    <section class="edge-sidebar__section">
      <button class="edge-sidebar__section-toggle" type="button" aria-expanded="false"><span>Front Desk</span><span class="edge-icon">V</span></button>
    </section>
    <section class="edge-sidebar__section">
      <button class="edge-sidebar__section-toggle" type="button" aria-expanded="false"><span>Clinical</span><span class="edge-icon">V</span></button>
    </section>
  </aside>
  <header><div class="edge-topbar-actions"></div></header>
</div>
<script>
window.__events = { routes: [], opened: 0, closed: 0 };
window.frappe = {
  router: { on() {} },
  utils: { icon() { return '<span class="edge-icon">G</span>'; } },
  set_route(route) { window.__events.routes.push(route); }
};
const config = {
  product: 'VetEdge',
  sections: [{ label: 'Clinical', items: [{ label: 'Consultations', route: '/desk/vetedge-clinical-workspace' }] }],
  navigate(item) { window.__events.routes.push(item.route); }
};
window.EdgeSuiteUI = {
  getProductMenuConfig() { return config; },
  getAdapter() { return { open(route) { window.__events.routes.push(route); return true; } }; },
  mountProductMenu() { return false; },
  refreshProductMenu() {
    const panel = document.getElementById('edge-product-menu-dropdown');
    if (!panel) return false;
    panel.innerHTML = `
      <button class="edge-product-menu__close" type="button">Close</button>
      <input class="edge-product-menu__search" type="search" />
      <span class="edge-product-menu__result-count">1</span>
      <section class="edge-product-menu__section">
        <button class="edge-product-menu__item" type="button" data-link-type="Page" data-link-to="vetedge-clinical-workspace" data-route="/desk/vetedge-clinical-workspace">Consultations</button>
      </section>`;
    return true;
  },
  openProductMenu() {
    this.refreshProductMenu();
    const panel = document.getElementById('edge-product-menu-dropdown');
    const trigger = document.getElementById('edge-product-menu-trigger');
    if (!panel || !trigger) return false;
    panel.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    document.documentElement.classList.add('edge-product-menu--open');
    window.__events.opened += 1;
    return true;
  },
  closeProductMenu() {
    const panel = document.getElementById('edge-product-menu-dropdown');
    const trigger = document.getElementById('edge-product-menu-trigger');
    if (panel) panel.hidden = true;
    if (trigger) trigger.setAttribute('aria-expanded', 'false');
    document.documentElement.classList.remove('edge-product-menu--open');
    window.__events.closed += 1;
    return true;
  }
};
window.EdgeUI = window.EdgeSuiteUI;
</script>
</body>
</html>
"""

	async with async_playwright() as playwright:
		browser = await playwright.chromium.launch(headless=True)
		page = await browser.new_page(viewport={"width": 1280, "height": 720})
		await page.set_content(html)
		await page.add_script_tag(content=patch_source)
		await page.wait_for_function("window.VetEdgePostQaNavigation?.state().directHome === true")

		home = page.locator('[data-vetedge-direct-home="1"].edge-sidebar-item')
		assert await home.count() == 1
		assert (await home.inner_text()).strip() == "Veterinary Home"
		assert await home.get_attribute("aria-label") == "Veterinary Home"
		assert await page.locator('[data-vetedge-direct-home="1"].edge-sidebar__section-toggle').count() == 0
		assert await page.locator('.edge-sidebar__section[data-vetedge-direct-home="1"]').count() == 0
		assert await home.get_attribute("aria-expanded") is None

		primary_labels = await page.locator(".edge-sidebar").evaluate(
			"""sidebar => Array.from(sidebar.children).map(node => {
			  const target = node.matches('[data-vetedge-direct-home="1"]')
			    ? node
			    : node.querySelector('.edge-sidebar__section-toggle');
			  if (!target) return '';
			  const label = Array.from(target.children || []).find(child => !child.classList.contains('edge-icon'));
			  return (label?.textContent || target.textContent || '').trim();
			})"""
		)
		assert primary_labels[:4] == ["Veterinary Home", "Dashboard", "Clinical Operations", "Appointments"]

		await home.click()
		await page.wait_for_function("window.__events.routes.includes('/desk/vetedge')")

		trigger = page.locator("#edge-product-menu-trigger")
		assert await trigger.count() == 1
		assert await trigger.is_visible()
		assert await trigger.evaluate("el => Boolean(el.closest('.edge-topbar-actions'))")

		await trigger.click()
		await page.wait_for_function("window.VetEdgePostQaNavigation.state().productMenuOpen === true")
		assert await page.locator("#edge-product-menu-dropdown").is_visible()

		search = page.locator(".edge-product-menu__search")
		await search.fill("consult")
		assert await page.locator(".edge-product-menu__item").is_visible()

		await page.locator(".edge-product-menu__item").click()
		await page.wait_for_function("window.__events.routes.includes('/desk/vetedge-clinical-workspace')")
		assert await page.locator("#edge-product-menu-dropdown").is_hidden()

		state = await page.evaluate("window.VetEdgePostQaNavigation.state()")
		events = await page.evaluate("window.__events")
		assert state["directHome"] is True
		assert state["productTriggerVisible"] is True
		assert state["productMenuBridged"] is True
		assert events["opened"] >= 1
		assert events["closed"] >= 1
		print(json.dumps({"state": state, "events": events, "primary_labels": primary_labels}, indent=2, sort_keys=True))
		await browser.close()


if __name__ == "__main__":
	asyncio.run(main())
