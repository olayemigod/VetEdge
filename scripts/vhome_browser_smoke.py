from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

BASE_URL = os.environ.get("VHOME_BASE_URL", "http://ci.localhost:8000").rstrip("/")
ADMIN_PASSWORD = os.environ["VHOME_ADMIN_PASSWORD"]
PERSONA_PASSWORD = os.environ.get("VHOME_PERSONA_PASSWORD", "")
ARTIFACT_DIR = Path(os.environ.get("VHOME_ARTIFACT_DIR", "/tmp/vhome-browser-artifacts"))
BRANCH_A = "VHOME QA Branch A"
BRANCH_B = "VHOME QA Branch B"
KNOWN_INHERITED_PAGEERROR = "report_pdf_patch.js:80:8"

PERSONA_CASES = (
	{
		"key": "doctor",
		"email": "vhome-browser-doctor@example.com",
		"primary": "Veterinary Doctor",
		"actions": ("Start / Continue Consultation", "Find Patient"),
		"metric_keys": ("my-appointments-today",),
		"branches": (BRANCH_A,),
		"forbidden_groups": ("Accounts / Cashier",),
	},
	{
		"key": "front-desk",
		"email": "vhome-browser-frontdesk@example.com",
		"primary": "Front Desk",
		"actions": ("Register / Find Patient", "Appointment Queue"),
		"metric_keys": ("today-appointments",),
		"metric_values": {"today-appointments": 1},
		"branches": (BRANCH_A,),
		"forbidden_groups": ("Accounts / Cashier",),
	},
	{
		"key": "nurse",
		"email": "vhome-browser-nurse@example.com",
		"primary": "Veterinary Nurse",
		"actions": ("Patient Records", "Clinical Workspace"),
		"metric_keys": ("today-appointments",),
		"branches": (BRANCH_A,),
	},
	{
		"key": "lab",
		"email": "vhome-browser-lab@example.com",
		"primary": "Laboratory",
		"actions": ("Pending Lab Orders",),
		"metric_keys": ("lab-pending",),
		"branches": (BRANCH_A,),
	},
	{
		"key": "groomer",
		"email": "vhome-browser-groomer@example.com",
		"primary": "Grooming",
		"actions": ("Grooming Appointments",),
		"metric_keys": ("grooming-today",),
		"branches": (BRANCH_A,),
	},
	{
		"key": "dispensary",
		"email": "vhome-browser-dispensary@example.com",
		"primary": "Dispensary",
		"actions": ("Pending Dispensary Work",),
		"metric_keys": ("pending-dispensary",),
		"branches": (BRANCH_A,),
	},
	{
		"key": "accounts",
		"email": "vhome-browser-accounts@example.com",
		"primary": "Accounts / Cashier",
		"actions": ("Sales Invoices", "Payments"),
		"metric_keys": ("outstanding-invoices",),
		"branches": (BRANCH_A,),
	},
	{
		"key": "branch-manager",
		"email": "vhome-browser-manager@example.com",
		"primary": "Branch Manager",
		"actions": ("Executive Dashboard",),
		"metric_keys": ("today-appointments",),
		"metric_values": {"today-appointments": 1},
		"branches": (BRANCH_A,),
	},
	{
		"key": "manager-doctor",
		"email": "vhome-browser-manager-doctor@example.com",
		"primary": "Branch Manager",
		"additional": ("Veterinary Doctor",),
		"actions": ("Executive Dashboard", "Start / Continue Consultation"),
		"metric_keys": ("today-appointments", "my-appointments-today"),
		"metric_values": {"today-appointments": 2},
		"branches": (BRANCH_A, BRANCH_B),
		"forbidden_groups": ("Accounts / Cashier",),
	},
	{
		"key": "branch-multi",
		"email": "vhome-browser-frontdesk-multi@example.com",
		"primary": "Front Desk",
		"actions": ("Appointment Queue",),
		"metric_keys": ("today-appointments",),
		"metric_values": {"today-appointments": 2},
		"branches": (BRANCH_A, BRANCH_B),
		"forbidden_groups": ("Accounts / Cashier",),
	},
)


def _wire_diagnostics(page: Page, events: list[str], label: str) -> None:
	def record_page_error(error: Exception) -> None:
		stack = getattr(error, "stack", "") or ""
		events.append(f"[{label}] pageerror: {error}\nstack: {stack}")

	def record_response(response) -> None:
		if response.status >= 400:
			events.append(f"[{label}] http:{response.status}: {response.request.method} {response.url}")

	page.on("console", lambda message: events.append(f"[{label}] console:{message.type}: {message.text}"))
	page.on("pageerror", record_page_error)
	page.on("response", record_response)
	page.on(
		"requestfailed",
		lambda request: events.append(
			f"[{label}] requestfailed: {request.method} {request.url} {request.failure}"
		),
	)


def _login(context: BrowserContext, user: str, password: str, events: list[str], label: str) -> None:
	response = context.request.post(
		f"{BASE_URL}/api/method/login",
		form={"usr": user, "pwd": password},
		timeout=120_000,
	)
	events.append(f"[{label}] login: status={response.status} ok={response.ok} user={user}")
	if not response.ok:
		raise AssertionError(f"{label}: login failed for {user} with HTTP {response.status}")


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


def _payload(page: Page) -> dict:
	return page.evaluate(
		"""async () => {
			const response = await frappe.call('vetedge.services.home.get_home_payload');
			return response.message;
		}"""
	)


def _metric_map(payload: dict) -> dict[str, dict]:
	return {row["key"]: row for row in payload.get("metrics") or []}


def _assert_persona(page: Page, case: dict) -> dict:
	_assert_home(page)
	context = page.locator(".vetedge-home-context")
	context.get_by_text(case["primary"], exact=True).wait_for(timeout=30_000)
	for label in case.get("additional", ()):
		context.get_by_text(label, exact=True).wait_for(timeout=30_000)
	for action in case.get("actions", ()):
		page.get_by_role("button", name=action, exact=True).wait_for(timeout=30_000)
	for group in case.get("forbidden_groups", ()):
		if page.get_by_role("heading", name=group, exact=True).count():
			raise AssertionError(f"{case['key']}: forbidden action group {group!r} is visible")

	payload = _payload(page)
	if payload.get("primary_persona", {}).get("label") != case["primary"]:
		raise AssertionError(
			f"{case['key']}: expected primary persona {case['primary']!r}, "
			f"got {payload.get('primary_persona')!r}"
		)
	actual_branches = tuple(payload.get("context", {}).get("assigned_branches") or [])
	if set(actual_branches) != set(case.get("branches", ())):
		raise AssertionError(
			f"{case['key']}: expected branch assignments {case.get('branches')!r}, got {actual_branches!r}"
		)
	if payload.get("context", {}).get("global_branch_access"):
		raise AssertionError(f"{case['key']}: unexpectedly has global branch access")

	metrics = _metric_map(payload)
	for key in case.get("metric_keys", ()):
		if key not in metrics:
			raise AssertionError(f"{case['key']}: expected metric {key!r} is missing")
	for key, expected in case.get("metric_values", {}).items():
		actual = metrics.get(key, {}).get("value")
		if actual != expected:
			raise AssertionError(f"{case['key']}: metric {key!r} expected {expected}, got {actual}")
	return payload


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


def _run_control_desk(browser: Browser, events: list[str]) -> None:
	context = browser.new_context(viewport={"width": 1440, "height": 1000})
	page = context.new_page()
	_wire_diagnostics(page, events, "control-desk")
	try:
		_login(context, "Administrator", ADMIN_PASSWORD, events, "control-desk")
		response = page.goto(f"{BASE_URL}/app", wait_until="domcontentloaded", timeout=120_000)
		events.append(f"[control-desk] goto: status={response.status if response else 'none'} url={page.url}")
		page.wait_for_timeout(2500)
	finally:
		context.close()


def _run_admin_home(browser: Browser, events: list[str]) -> None:
	context = browser.new_context(viewport={"width": 1440, "height": 1000})
	page = context.new_page()
	_wire_diagnostics(page, events, "administrator")
	try:
		_login(context, "Administrator", ADMIN_PASSWORD, events, "administrator")
		response = page.goto(f"{BASE_URL}/app/vetedge", wait_until="domcontentloaded", timeout=120_000)
		events.append(f"[administrator] goto: status={response.status if response else 'none'} url={page.url}")
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
	finally:
		context.close()


def _run_persona_home(browser: Browser, events: list[str], case: dict) -> dict:
	context = browser.new_context(viewport={"width": 1280, "height": 900})
	page = context.new_page()
	label = f"persona:{case['key']}"
	_wire_diagnostics(page, events, label)
	try:
		_login(context, case["email"], PERSONA_PASSWORD, events, label)
		response = page.goto(f"{BASE_URL}/app/vetedge", wait_until="domcontentloaded", timeout=120_000)
		events.append(f"[{label}] goto: status={response.status if response else 'none'} url={page.url}")
		try:
			payload = _assert_persona(page, case)
		except Exception:
			_capture(page, events, f"vhome-{case['key']}-failure")
			raise
		page.screenshot(path=str(ARTIFACT_DIR / f"vhome-{case['key']}.png"), full_page=True)
		return payload
	finally:
		context.close()


def _run_plain_desk_denial(browser: Browser, events: list[str]) -> None:
	context = browser.new_context(viewport={"width": 1280, "height": 900})
	page = context.new_page()
	label = "plain-desk-denial"
	_wire_diagnostics(page, events, label)
	try:
		_login(context, "vhome-browser-desk-only@example.com", PERSONA_PASSWORD, events, label)
		page.goto(f"{BASE_URL}/app/vetedge", wait_until="domcontentloaded", timeout=120_000)
		page.get_by_text("Veterinary Home could not load", exact=True).wait_for(timeout=30_000)
		if page.get_by_role("heading", name="Your Operational Snapshot", exact=True).count():
			raise AssertionError("plain Desk User unexpectedly received Veterinary Home dashboard content")
	except Exception:
		_capture(page, events, "vhome-plain-desk-denial-failure")
		raise
	finally:
		context.close()


def _run_guest_denial(browser: Browser, events: list[str]) -> None:
	context = browser.new_context(viewport={"width": 1280, "height": 900})
	page = context.new_page()
	_wire_diagnostics(page, events, "guest-denial")
	try:
		page.goto(f"{BASE_URL}/app/vetedge", wait_until="domcontentloaded", timeout=120_000)
		page.wait_for_timeout(1500)
		if page.get_by_role("heading", name="Veterinary Home", exact=True).count():
			raise AssertionError("Guest unexpectedly reached Veterinary Home")
		if "login" not in page.url.lower():
			raise AssertionError(f"Guest was not redirected to login: {page.url}")
	except Exception:
		_capture(page, events, "vhome-guest-denial-failure")
		raise
	finally:
		context.close()


def _assert_pageerror_attribution(events: list[str]) -> None:
	pageerrors = [event for event in events if " pageerror:" in event]
	unexpected = [event for event in pageerrors if KNOWN_INHERITED_PAGEERROR not in event]
	if unexpected:
		raise AssertionError("Unexpected browser page errors:\n" + "\n\n".join(unexpected))


def main() -> None:
	ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
	chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chromium")
	if not chrome:
		raise RuntimeError("Chrome/Chromium executable is not available on the CI runner")
	if not PERSONA_PASSWORD:
		raise RuntimeError("VHOME_PERSONA_PASSWORD is required for persona browser QA")

	events: list[str] = []
	persona_results: dict[str, dict] = {}
	with sync_playwright() as playwright:
		browser = playwright.chromium.launch(executable_path=chrome, headless=True, args=["--no-sandbox"])
		try:
			_run_control_desk(browser, events)
			_run_admin_home(browser, events)
			for case in PERSONA_CASES:
				payload = _run_persona_home(browser, events, case)
				persona_results[case["key"]] = {
					"primary_persona": payload.get("primary_persona"),
					"personas": payload.get("personas"),
					"context": payload.get("context"),
					"metric_keys": [row.get("key") for row in payload.get("metrics") or []],
					"action_labels": [row.get("label") for row in payload.get("quick_actions") or []],
				}
			_run_plain_desk_denial(browser, events)
			_run_guest_denial(browser, events)
		finally:
			browser.close()

	_assert_pageerror_attribution(events)
	(ARTIFACT_DIR / "persona-results.json").write_text(
		json.dumps(persona_results, indent=2), encoding="utf-8"
	)
	(ARTIFACT_DIR / "browser-events.log").write_text("\n".join(events), encoding="utf-8")


if __name__ == "__main__":
	main()
