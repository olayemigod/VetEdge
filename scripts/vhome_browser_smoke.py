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
DEFAULT_TIMEOUT_MS = 30_000
NAVIGATION_TIMEOUT_MS = 60_000
API_TIMEOUT_MS = 30_000

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
        "click_metric": "today-appointments",
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
        "actions": ("Executive Dashboard", "Clinical Workspace", "Find Patient"),
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


def _progress(label: str, status: str) -> None:
    print(f"[VHOME browser] {status}: {label}", flush=True)


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


def _new_page(context: BrowserContext, events: list[str], label: str) -> Page:
    page = context.new_page()
    page.set_default_timeout(DEFAULT_TIMEOUT_MS)
    page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
    _wire_diagnostics(page, events, label)
    return page


def _login(
    context: BrowserContext,
    user: str,
    password: str,
    events: list[str],
    label: str,
    *,
    expect_vetedge_home: bool = False,
) -> dict:
    response = context.request.post(
        f"{BASE_URL}/api/method/login",
        form={"usr": user, "pwd": password},
        timeout=API_TIMEOUT_MS,
    )
    events.append(f"[{label}] login: status={response.status} ok={response.ok} user={user}")
    if not response.ok:
        raise AssertionError(f"{label}: login failed for {user} with HTTP {response.status}")
    data = response.json()
    if not isinstance(data, dict):
        raise AssertionError(f"{label}: login response was not an object")
    if expect_vetedge_home:
        home_page = str(data.get("home_page") or "").rstrip("/")
        if home_page not in {"desk/vetedge", "/desk/vetedge"}:
            raise AssertionError(
                f"{label}: expected Veterinary Home login destination, got {home_page!r}"
            )
    return data


def _assert_home(page: Page) -> None:
    page.get_by_role("heading", name="Veterinary Home", exact=True).wait_for()
    for heading in ("Needs Your Attention", "Your Operational Snapshot", "Quick Actions"):
        page.get_by_role("heading", name=heading, exact=True).wait_for()
    page.get_by_text("Working as", exact=True).wait_for()
    page.get_by_text("Branch scope", exact=True).wait_for()
    page.get_by_text("Operational date", exact=True).first.wait_for()
    if "resource-center" in page.url:
        raise AssertionError(f"Veterinary Home redirected to Resource Center: {page.url}")
    if page.get_by_role("heading", name="Veterinary Home", exact=True).count() != 1:
        raise AssertionError("Veterinary Home mounted more than once")


def _payload(
    context: BrowserContext,
    events: list[str],
    label: str,
    *,
    branch: str | None = None,
    operational_date: str | None = None,
) -> dict:
    params = {}
    if branch:
        params["branch"] = branch
    if operational_date:
        params["operational_date"] = operational_date
    response = context.request.get(
        f"{BASE_URL}/api/method/vetedge.services.home.get_home_payload",
        params=params,
        timeout=API_TIMEOUT_MS,
    )
    events.append(f"[{label}] payload: status={response.status} ok={response.ok}")
    if not response.ok:
        raise AssertionError(f"{label}: Home payload request failed with HTTP {response.status}")
    data = response.json()
    payload = data.get("message") if isinstance(data, dict) else None
    if not isinstance(payload, dict):
        raise AssertionError(f"{label}: Home payload response did not contain a message object")
    return payload


def _drilldown(
    context: BrowserContext,
    events: list[str],
    label: str,
    metric_key: str,
    *,
    branch: str | None = None,
    operational_date: str | None = None,
) -> dict:
    params = {"metric_key": metric_key}
    if branch:
        params["branch"] = branch
    if operational_date:
        params["operational_date"] = operational_date
    response = context.request.get(
        f"{BASE_URL}/api/method/vetedge.services.home.get_metric_drilldown",
        params=params,
        timeout=API_TIMEOUT_MS,
    )
    events.append(f"[{label}] drilldown:{metric_key}: status={response.status} ok={response.ok}")
    if not response.ok:
        raise AssertionError(
            f"{label}: drilldown {metric_key!r} failed with HTTP {response.status}"
        )
    data = response.json()
    result = data.get("message") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise AssertionError(f"{label}: drilldown response did not contain a message object")
    return result


def _metric_map(payload: dict) -> dict[str, dict]:
    return {row["key"]: row for row in payload.get("metrics") or []}


def _assert_metric_reconciliation(
    browser_context: BrowserContext,
    payload: dict,
    keys: tuple[str, ...],
    events: list[str],
    label: str,
) -> None:
    metrics = _metric_map(payload)
    context = payload.get("context") or {}
    branch = context.get("branch_value")
    operational_date = context.get("operational_date")
    for key in keys:
        metric = metrics.get(key)
        if not metric:
            raise AssertionError(f"{label}: expected metric {key!r} is missing")
        result = _drilldown(
            browser_context,
            events,
            label,
            key,
            branch=branch,
            operational_date=operational_date,
        )
        if result.get("total") != metric.get("value"):
            raise AssertionError(
                f"{label}: card/drilldown mismatch for {key!r}: "
                f"card={metric.get('value')} drilldown={result.get('total')}"
            )
        if result.get("metric", {}).get("key") != key:
            raise AssertionError(f"{label}: drilldown returned wrong metric identity for {key!r}")


def _assert_clicked_metric(page: Page, payload: dict, metric_key: str) -> None:
    metric = _metric_map(payload).get(metric_key)
    if not metric:
        raise AssertionError(f"clicked metric {metric_key!r} is missing")
    button = page.locator(".vetedge-home-stat-button").filter(has_text=metric["label"])
    if button.count() != 1:
        raise AssertionError(
            f"expected one clickable KPI for {metric[\"label\"]!r}, got {button.count()}"
        )
    button.click()
    panel = page.locator(".vetedge-home-drilldown")
    panel.get_by_role("heading", name=metric["label"], exact=True).wait_for()
    panel.get_by_text(f"{metric['value']} total", exact=False).wait_for()
    footer = panel.get_by_text(f"of {metric['value']}", exact=False)
    if metric["value"] and footer.count() == 0:
        raise AssertionError(
            f"clicked KPI {metric_key!r} did not render a drilldown total matching {metric['value']}"
        )


def _assert_persona(
    page: Page,
    browser_context: BrowserContext,
    case: dict,
    events: list[str],
) -> dict:
    _assert_home(page)
    context_panel = page.locator(".vetedge-home-context")
    context_panel.get_by_text(case["primary"], exact=True).wait_for()
    for label in case.get("additional", ()):
        context_panel.get_by_text(label, exact=True).wait_for()
    for action in case.get("actions", ()):
        page.get_by_role("button", name=action, exact=True).wait_for()
    for group in case.get("forbidden_groups", ()):
        if page.get_by_role("heading", name=group, exact=True).count():
            raise AssertionError(f"{case['key']}: forbidden action group {group!r} is visible")

    payload = _payload(browser_context, events, f"persona:{case['key']}")
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

    _assert_metric_reconciliation(
        browser_context,
        payload,
        tuple(case.get("metric_keys", ())),
        events,
        f"persona:{case['key']}",
    )
    if case.get("click_metric"):
        _assert_clicked_metric(page, payload, case["click_metric"])
    return payload


def _checkpoint(events: list[str], persona_results: dict[str, dict]) -> None:
    (ARTIFACT_DIR / "browser-events.log").write_text("\n".join(events), encoding="utf-8")
    (ARTIFACT_DIR / "persona-results.partial.json").write_text(
        json.dumps(persona_results, indent=2), encoding="utf-8"
    )


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
    print(json.dumps(metadata, indent=2), flush=True)
    print("\n".join(events[-100:]), flush=True)


def _run_control_desk(browser: Browser, events: list[str]) -> None:
    label = "control-desk"
    _progress(label, "START")
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = _new_page(context, events, label)
    try:
        _login(context, "Administrator", ADMIN_PASSWORD, events, label)
        response = page.goto(f"{BASE_URL}/app", wait_until="domcontentloaded")
        events.append(f"[{label}] goto: status={response.status if response else 'none'} url={page.url}")
        page.wait_for_timeout(2500)
    finally:
        context.close()
    _progress(label, "PASS")


def _run_admin_home(browser: Browser, events: list[str]) -> None:
    label = "administrator"
    _progress(label, "START")
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = _new_page(context, events, label)
    try:
        _login(context, "Administrator", ADMIN_PASSWORD, events, label)
        response = page.goto(f"{BASE_URL}/app/vetedge", wait_until="domcontentloaded")
        events.append(f"[{label}] goto: status={response.status if response else 'none'} url={page.url}")
        try:
            _assert_home(page)
        except Exception:
            _capture(page, events, "vhome-initial-failure")
            raise
        page.screenshot(path=str(ARTIFACT_DIR / "vhome-desktop.png"), full_page=True)

        page.evaluate("() => { frappe.set_route('vetedge-resource-center'); return true; }")
        page.wait_for_timeout(1500)
        page.evaluate("() => { frappe.set_route('vetedge'); return true; }")
        try:
            _assert_home(page)
        except Exception:
            _capture(page, events, "vhome-warm-nav-failure")
            raise

        page.set_viewport_size({"width": 390, "height": 844})
        page.reload(wait_until="domcontentloaded")
        try:
            _assert_home(page)
        except Exception:
            _capture(page, events, "vhome-mobile-failure")
            raise
        if not page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 2"):
            _capture(page, events, "vhome-mobile-overflow")
            raise AssertionError("Veterinary Home overflows the narrow viewport horizontally")
        page.screenshot(path=str(ARTIFACT_DIR / "vhome-mobile.png"), full_page=True)
    finally:
        context.close()
    _progress(label, "PASS")


def _run_persona_home(browser: Browser, events: list[str], case: dict) -> dict:
    label = f"persona:{case['key']}"
    _progress(label, "START")
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = _new_page(context, events, label)
    try:
        _login(
            context,
            case["email"],
            PERSONA_PASSWORD,
            events,
            label,
            expect_vetedge_home=True,
        )
        response = page.goto(f"{BASE_URL}/app/vetedge", wait_until="domcontentloaded")
        events.append(f"[{label}] goto: status={response.status if response else 'none'} url={page.url}")
        try:
            payload = _assert_persona(page, context, case, events)
        except Exception:
            _capture(page, events, f"vhome-{case['key']}-failure")
            raise
        page.screenshot(path=str(ARTIFACT_DIR / f"vhome-{case['key']}.png"), full_page=True)
    finally:
        context.close()
    _progress(label, "PASS")
    return payload


def _run_plain_desk_denial(browser: Browser, events: list[str]) -> None:
    label = "plain-desk-denial"
    _progress(label, "START")
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = _new_page(context, events, label)
    try:
        _login(context, "vhome-browser-desk-only@example.com", PERSONA_PASSWORD, events, label)
        page.goto(f"{BASE_URL}/app/vetedge", wait_until="domcontentloaded")
        page.get_by_text("Veterinary Home could not load", exact=True).wait_for()
        if page.get_by_role("heading", name="Your Operational Snapshot", exact=True).count():
            raise AssertionError("plain Desk User unexpectedly received Veterinary Home dashboard content")
    except Exception:
        _capture(page, events, "vhome-plain-desk-denial-failure")
        raise
    finally:
        context.close()
    _progress(label, "PASS")


def _run_guest_denial(browser: Browser, events: list[str]) -> None:
    label = "guest-denial"
    _progress(label, "START")
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = _new_page(context, events, label)
    try:
        page.goto(f"{BASE_URL}/app/vetedge", wait_until="domcontentloaded")
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
    _progress(label, "PASS")


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
    _progress("matrix", "START")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=chrome, headless=True, args=["--no-sandbox"])
        try:
            _run_control_desk(browser, events)
            _checkpoint(events, persona_results)
            _run_admin_home(browser, events)
            _checkpoint(events, persona_results)
            for case in PERSONA_CASES:
                payload = _run_persona_home(browser, events, case)
                persona_results[case["key"]] = {
                    "primary_persona": payload.get("primary_persona"),
                    "personas": payload.get("personas"),
                    "context": payload.get("context"),
                    "metric_keys": [row.get("key") for row in payload.get("metrics") or []],
                    "metric_values": {
                        row.get("key"): row.get("value") for row in payload.get("metrics") or []
                    },
                    "action_labels": [row.get("label") for row in payload.get("quick_actions") or []],
                }
                _checkpoint(events, persona_results)
            _run_plain_desk_denial(browser, events)
            _checkpoint(events, persona_results)
            _run_guest_denial(browser, events)
        finally:
            browser.close()

    _assert_pageerror_attribution(events)
    (ARTIFACT_DIR / "persona-results.json").write_text(json.dumps(persona_results, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "browser-events.log").write_text("\n".join(events), encoding="utf-8")
    _progress("matrix", "PASS")


if __name__ == "__main__":
    main()
