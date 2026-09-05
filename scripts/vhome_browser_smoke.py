from __future__ import annotations

import os
import shutil
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE_URL = os.environ.get("VHOME_BASE_URL", "http://ci.localhost:8000").rstrip("/")
ARTIFACT_DIR = Path(os.environ.get("VHOME_ARTIFACT_DIR", "/tmp/vhome-browser-artifacts"))


def _assert_home(page: Page) -> None:
	page.get_by_role("heading", name="Veterinary Home", exact=True).wait_for(timeout=120_000)
	for heading in ("Needs Your Attention", "Your Operational Snapshot", "Quick Actions"):
		page.get_by_role("heading", name=heading, exact=True).wait_for(timeout=30_000)
	page.get_by_text("Working as", exact=True).wait_for(timeout=30_000)
	page.get_by_text("Branch scope", exact=True).wait_for(timeout=30_000)
	if "resource-center" in page.url:
		raise AssertionError(f"Veterinary Home redirected to Resource Center: {page.url}")
	if page.get_by_role("heading", name="Veterinary Home", exact=True).count() != 1:
		raise AssertionError("Veterinary Home mounted more than once")


def main() -> None:
	ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
	chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chromium")
	if not chrome:
		raise RuntimeError("Chrome/Chromium executable is not available on the CI runner")

	with sync_playwright() as playwright:
		browser = playwright.chromium.launch(executable_path=chrome, headless=True, args=["--no-sandbox"])
		context = browser.new_context(viewport={"width": 1440, "height": 1000})
		login = context.request.post(
			f"{BASE_URL}/api/method/login",
			form={"usr": "Administrator", "pwd": "admin"},
			timeout=120_000,
		)
		if not login.ok:
			raise AssertionError(f"Administrator login failed with HTTP {login.status}")

		page = context.new_page()
		page.goto(f"{BASE_URL}/app/vetedge", wait_until="domcontentloaded", timeout=120_000)
		_assert_home(page)
		page.screenshot(path=str(ARTIFACT_DIR / "vhome-desktop.png"), full_page=True)

		# Exercise warm Desk navigation rather than a full browser reload. Returning
		# to Veterinary Home must reuse the shell without mounting duplicate content.
		page.evaluate("frappe.set_route('vetedge-resource-center')")
		page.wait_for_timeout(1_500)
		page.evaluate("frappe.set_route('vetedge')")
		_assert_home(page)

		page.set_viewport_size({"width": 390, "height": 844})
		page.reload(wait_until="domcontentloaded", timeout=120_000)
		_assert_home(page)
		overflow = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
		if not overflow:
			raise AssertionError("Veterinary Home overflows the narrow viewport horizontally")
		page.screenshot(path=str(ARTIFACT_DIR / "vhome-mobile.png"), full_page=True)

		browser.close()


if __name__ == "__main__":
	main()
