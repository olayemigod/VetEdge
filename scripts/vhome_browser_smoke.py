from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE_URL = os.environ.get("VHOME_BASE_URL", "http://ci.localhost:8000").rstrip("/")
ADMIN_PASSWORD = os.environ["VHOME_ADMIN_PASSWORD"]
ARTIFACT_DIR = Path(os.environ.get("VHOME_ARTIFACT_DIR", "/tmp/vhome-browser-artifacts"))


def _assert_home(page: Page) -> None:
	page.get_by_role("heading", name="Veterinary Home", exact=True).wait_for(timeout=30_000)
	for heading in ("Needs Your Attention", "Your Operational Snapshot", "Quick Actions"):
		page.get_by_role("heading", name=heading, exact=True).wait_for(timeout=30_000)
	page.get_by_text("Working as", exact=True).wait_for(timeout=30_000)
	page.get_by_text("Branch scope", exact=True).wait_for(timeout=30_000)
	if "resource-center" in page.url:
		raise AssertionError(f"Veterinary Home redirected to Resource Center: {page.url}")
	if page.get_by_role("heading", name="Veterinary Home", exact=True).count() != 1:
		raise AssertionError("Veterinary Home mounted more than once")


def _capture(page: Page, events: list[str], stage: str) -> None:
	try:
		(ARTIFACT_DIR / f"{stage}.html").write_text(page.content(), encoding="utf-8")
		page.screenshot(path=str(ARTIFACT_DIR / f"{stage}.png"), full_page=True)
		body = page.locator("body").inner_text(timeout=5_000)
		title = page.title()
	except Exception as exc:
		body = f"diagnostic capture failed: {exc!r}"
		title = ""
	metadata = {"stage": stage, "url": page.url, "title": title, "body_excerpt": body[:8000]}
	(ARTIFACT_DIR / f"{stage}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
	(ARTIFACT_DIR / "browser-events.log").write_text("\n".join(events), encoding="utf-8")
	print(json.dumps(metadata, indent=2))
	print("\n".join(events[-100:]))


def main() -> None:
	ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
	chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chromium")
	if not chrome:
		raise RuntimeError("Chrome/Chromium executable is not available on the CI runner")

	with sync_playwright() as playwright:
		browser = playwright.chromium.launch(executable_path=chrome, headless=True, args=["--no-sandbox"])
		context = browser.new_context(viewport={"width": 1440, "height": 1000})
		page = context.new_page()
		events: list[str] = []

		def record_page_error(error: Exception) -> None:
			stack = getattr(error, "stack", "") or ""
			events.append(f"pageerror: {error}\nstack: {stack}")

		def record_response(response) -> None:
			if response.status >= 400:
				events.append(f"http:{response.status}: {response.request.method} {response.url}")

		page.on("console", lambda message: events.append(f"console:{message.type}: {message.text}"))
		page.on("pageerror", record_page_error)
		page.on("response", record_response)
		page.on("requestfailed", lambda request: events.append(f"requestfailed: {request.method} {request.url} {request.failure}"))
		try:
			login = context.request.post(
				f"{BASE_URL}/api/method/login",
				form={"usr": "Administrator", "pwd": ADMIN_PASSWORD},
				timeout=120_000,
			)
			events.append(f"login: status={login.status} ok={login.ok}")
			if not login.ok:
				raise AssertionError(f"Administrator login failed with HTTP {login.status}")

			response = page.goto(f"{BASE_URL}/app/vetedge", wait_until="domcontentloaded", timeout=120_000)
			events.append(f"goto: status={response.status if response else 'none'} url={page.url}")
			try:
				_assert_home(page)
			except Exception:
				_capture(page, events, "vhome-initial-failure")
				raise
			page.screenshot(path=str(ARTIFACT_DIR / "vhome-desktop.png"), full_page=True)

			page.evaluate("frappe.set_route('vetedge-resource-center')")
			page.wait_for_timeout(1500)
			page.evaluate("frappe.set_route('vetedge')")
			try:
				_assert_home(page)
			except Exception:
				_capture(page, events, "vhome-warm-nav-failure")
				raise

			page.set_viewport_size({"width": 390, "height": 844})
			page.reload(wait_until="domcontentloaded", timeout=120_000)
			try:
				_assert_home(page)
			except Exception:
				_capture(page, events, "vhome-mobile-failure")
				raise
			if not page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2"):
				_capture(page, events, "vhome-mobile-overflow")
				raise AssertionError("Veterinary Home overflows the narrow viewport horizontally")
			page.screenshot(path=str(ARTIFACT_DIR / "vhome-mobile.png"), full_page=True)
			(ARTIFACT_DIR / "browser-events.log").write_text("\n".join(events), encoding="utf-8")
		finally:
			browser.close()


if __name__ == "__main__":
	main()
