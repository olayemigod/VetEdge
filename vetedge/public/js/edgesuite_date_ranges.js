(function () {
	frappe.EdgeSuite = frappe.EdgeSuite || {};
	
	const DateRanges = {
		earliestDate: "2020-01-01",
		
		init() {
			frappe.call({
				method: "vetedge.services.report_visibility.get_earliest_transaction_date",
				callback: (r) => {
					if (r.message) {
						this.earliestDate = r.message;
					}
				}
			});
		},
		
		getDefaultPreset() {
			return "this_month";
		},
		
		getRange(preset) {
			let start, end;
			const today = moment();
			switch (preset) {
				case "today":
					start = today.clone().startOf("day");
					end = today.clone().endOf("day");
					break;
				case "yesterday":
					start = today.clone().subtract(1, "days").startOf("day");
					end = today.clone().subtract(1, "days").endOf("day");
					break;
				case "this_week":
					start = today.clone().startOf("week");
					end = today.clone().endOf("week");
					break;
				case "last_week":
					start = today.clone().subtract(1, "weeks").startOf("week");
					end = today.clone().subtract(1, "weeks").endOf("week");
					break;
				case "this_month":
					start = today.clone().startOf("month");
					end = today.clone().endOf("month");
					break;
				case "last_month":
					start = today.clone().subtract(1, "months").startOf("month");
					end = today.clone().subtract(1, "months").endOf("month");
					break;
				case "this_quarter":
					start = today.clone().startOf("quarter");
					end = today.clone().endOf("quarter");
					break;
				case "last_quarter":
					start = today.clone().subtract(1, "quarters").startOf("quarter");
					end = today.clone().subtract(1, "quarters").endOf("quarter");
					break;
				case "this_year":
					start = today.clone().startOf("year");
					end = today.clone().endOf("year");
					break;
				case "last_year":
					start = today.clone().subtract(1, "years").startOf("year");
					end = today.clone().subtract(1, "years").endOf("year");
					break;
			case "full_history":
				return { start: "", end: "" };
				default:
					return null;
			}
			return {
				start: start.format("YYYY-MM-DD"),
				end: end.format("YYYY-MM-DD")
			};
		},
		
		getPreviousRange(preset, currentRange = null) {
			let range = currentRange;
			if (!range && preset && preset !== "custom") {
				range = this.getRange(preset);
			}
			if (!range || !range.start || !range.end) {
				return null;
			}
			const start = moment(range.start);
			const end = moment(range.end);
			const durationDays = end.diff(start, "days") + 1;
			const prevEnd = start.clone().subtract(1, "days");
			const prevStart = prevEnd.clone().subtract(durationDays - 1, "days");
			return {
				start: prevStart.format("YYYY-MM-DD"),
				end: prevEnd.format("YYYY-MM-DD")
			};
		},
		
		getOptions() {
			return [
				{ value: "this_month", label: __("This Month") },
				{ value: "today", label: __("Today") },
				{ value: "yesterday", label: __("Yesterday") },
				{ value: "this_week", label: __("This Week") },
				{ value: "last_week", label: __("Last Week") },
				{ value: "last_month", label: __("Last Month") },
				{ value: "this_quarter", label: __("This Quarter") },
				{ value: "last_quarter", label: __("Last Quarter") },
				{ value: "this_year", label: __("This Year") },
				{ value: "last_year", label: __("Last Year") },
				{ value: "full_history", label: __("Full History") },
				{ value: "custom", label: __("-- Custom Range --") }
			];
		},

		applyPreset({ state, preset, presetField, fromField, toField, refresh }) {
			const range = this.getRange(preset);
			if (!range) return false;
			state.is_updating_preset = true;
			state.date_preset = preset;
			state.from_date = range.start;
			state.to_date = range.end;
			presetField.set_value(preset);
			fromField.set_value(range.start);
			toField.set_value(range.end);
			frappe.route_options = Object.assign({}, frappe.route_options, {
				date_preset: preset, from_date: range.start, to_date: range.end,
			});
			requestAnimationFrame(() => {
				refresh(() => requestAnimationFrame(() => { state.is_updating_preset = false; }));
			});
			return true;
		}
	};
	
	frappe.EdgeSuite.DateRanges = DateRanges;
	
	// Auto-initialize on load
	$(document).ready(() => {
		DateRanges.init();
	});
})();

// VFD-BILL-01 browser navigation guard.
// This is intentionally loaded after the shared EdgeSuite/VetEdge navigation
// bridges so it can guarantee current-window routing even when a shared menu
// panel is re-rendered and loses component-local event listeners.
(function installVetEdgeBillingNavigationGuard(global) {
	"use strict";
	if (!global || global.__vetedgeBillingNavigationGuardInstalled) return;
	global.__vetedgeBillingNavigationGuardInstalled = true;

	const BILLING_CENTER_ROUTE = "/desk/vetedge-billing-center";
	const BILLING_SESSIONS_ROUTE = "/desk/vetedge-billing-sessions";
	const BILLING_SESSION_DOCTYPE = "Veterinary Billing Session";
	const NATIVE_BILLING_SESSION_PATH = "/desk/veterinary-billing-session";
	const PRODUCT_PANEL_SELECTORS = ["#edge-product-menu-dropdown", "#vetedge-product-menu-panel"];
	const PRODUCT_ITEM_SELECTOR = [
		".edge-product-menu__item",
		".edge-product-menu-item",
		".vetedge-product-menu-link",
		"[data-link-to]",
		"[data-route]",
		"[role='menuitem']",
	].join(",");
	let redirectingNativeSession = false;
	let scheduledReconcile = null;

	function runtime() {
		return global.EdgeSuiteUI || global.EdgeUI || null;
	}

	function normalizeText(value) {
		return String(value || "").replace(/\s+/g, " ").trim();
	}

	function slug(value) {
		return normalizeText(value)
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, "-")
			.replace(/^-|-$/g, "");
	}

	function currentWindow(route, { replace = false } = {}) {
		const target = String(route || "").trim();
		if (!target) return false;
		const url = new URL(target, global.location.origin);
		if (url.origin !== global.location.origin) return false;
		const next = `${url.pathname}${url.search}${url.hash}`;
		const current = `${global.location.pathname}${global.location.search}${global.location.hash}`;
		if (current === next) return true;
		if (replace) global.location.replace(next);
		else global.location.assign(next);
		return true;
	}

	function billingSessionDetailRoute(name) {
		const session = normalizeText(name);
		return session ? `${BILLING_SESSIONS_ROUTE}?name=${encodeURIComponent(session)}` : BILLING_SESSIONS_ROUTE;
	}

	function productConfig() {
		try {
			return runtime()?.getProductMenuConfig?.() || null;
		} catch (_error) {
			return null;
		}
	}

	function itemFromConfigByLabel(label) {
		const text = normalizeText(label).toLowerCase();
		if (!text) return null;
		const items = (productConfig()?.sections || []).flatMap((section) => section?.items || []);
		return items.find((item) => {
			const itemLabel = normalizeText(item?.label).toLowerCase();
			return itemLabel && (text === itemLabel || text.startsWith(`${itemLabel} `) || text.includes(itemLabel));
		}) || null;
	}

	function describeProductItem(node) {
		const explicit = {
			label: normalizeText(node?.dataset?.label || node?.getAttribute?.("aria-label") || node?.textContent),
			link_type: normalizeText(node?.dataset?.linkType || node?.getAttribute?.("data-link-type")),
			link_to: normalizeText(node?.dataset?.linkTo || node?.getAttribute?.("data-link-to")),
			route: normalizeText(node?.dataset?.route || node?.getAttribute?.("data-route") || node?.getAttribute?.("href")),
		};
		const configured = itemFromConfigByLabel(explicit.label) || {};
		return {
			label: configured.label || explicit.label,
			link_type: explicit.link_type || configured.link_type || configured.linkType || "Page",
			link_to: explicit.link_to || configured.link_to || configured.linkTo || "",
			route: explicit.route || configured.route || "",
		};
	}

	function canonicalProductRoute(item) {
		const linkTo = normalizeText(item?.link_to || item?.linkTo);
		const route = normalizeText(item?.route);
		const label = normalizeText(item?.label);
		if (linkTo === BILLING_SESSION_DOCTYPE || linkTo === "vetedge-billing-sessions" || label === "Billing Session" || label === "Billing Sessions") {
			return BILLING_SESSIONS_ROUTE;
		}
		if (linkTo === "vetedge-billing-center" || route.includes("vetedge-billing-center") || label === "Billing Center") {
			return BILLING_CENTER_ROUTE;
		}
		try {
			const recovery = global.VetEdgeNavigationRecovery;
			const canonical = recovery?.canonicalRoute?.(item);
			if (canonical) return canonical;
		} catch (_error) {
			// Deterministic fallback below.
		}
		if (route) return route;
		if (!linkTo) return "";
		const type = normalizeText(item?.link_type || item?.linkType || "Page");
		if (type === "Report") return `/desk/query-report/${encodeURIComponent(linkTo)}`;
		if (type === "DocType") return `/desk/${slug(linkTo)}`;
		return `/desk/${linkTo.replace(/^\/+/, "")}`;
	}

	function panelContaining(node) {
		return PRODUCT_PANEL_SELECTORS
			.map((selector) => global.document?.querySelector?.(selector))
			.find((panel) => panel?.contains?.(node)) || null;
	}

	function productItemFromEvent(event) {
		const panel = panelContaining(event.target);
		if (!panel) return null;
		const item = event.target?.closest?.(PRODUCT_ITEM_SELECTOR);
		return item && panel.contains(item) ? item : null;
	}

	function closeProductMenu() {
		try { runtime()?.closeProductMenu?.(); } catch (_error) { /* no-op */ }
		const fallback = global.document?.querySelector?.("#vetedge-product-menu-panel");
		if (fallback) fallback.hidden = true;
	}

	function routeProductItem(node) {
		const item = describeProductItem(node);
		const route = canonicalProductRoute(item);
		if (!route) return false;
		closeProductMenu();
		return currentWindow(route);
	}

	function searchableItems(panel) {
		return Array.from(panel?.querySelectorAll?.(PRODUCT_ITEM_SELECTOR) || []).filter((item) => {
			return !item.matches?.("input, textarea, select") && !item.closest?.(".edge-product-menu__close");
		});
	}

	function filterProductMenu(panel, query) {
		if (!panel) return 0;
		const term = normalizeText(query).toLowerCase();
		let count = 0;
		for (const item of searchableItems(panel)) {
			if (item.dataset.vetedgeSearchOriginalHidden === undefined) {
				item.dataset.vetedgeSearchOriginalHidden = item.hidden ? "1" : "0";
			}
			const originallyHidden = item.dataset.vetedgeSearchOriginalHidden === "1";
			const match = !term || normalizeText(item.textContent).toLowerCase().includes(term);
			item.hidden = originallyHidden || !match;
			if (!item.hidden) count += 1;
		}
		for (const section of panel.querySelectorAll?.(".edge-product-menu__section, .vetedge-product-menu-section") || []) {
			const visibleItems = searchableItems(section).some((item) => !item.hidden);
			section.hidden = !visibleItems;
		}
		const resultCount = panel.querySelector?.(".edge-product-menu__result-count");
		if (resultCount) resultCount.textContent = String(count);
		return count;
	}

	function isProductSearchInput(node) {
		const panel = panelContaining(node);
		if (!panel || !(node instanceof global.HTMLInputElement)) return false;
		const type = normalizeText(node.type).toLowerCase();
		const placeholder = normalizeText(node.placeholder).toLowerCase();
		return type === "search" || node.classList.contains("edge-product-menu__search") || placeholder.includes("search");
	}

	function sidebarItemLabel(item) {
		return normalizeText(item?.querySelector?.(".edge-sidebar-item__label")?.textContent || item?.textContent);
	}

	function sidebarBillingRoute(item) {
		const label = sidebarItemLabel(item);
		if (label === "Billing Center") return BILLING_CENTER_ROUTE;
		if (label === "Billing Session" || label === "Billing Sessions") return BILLING_SESSIONS_ROUTE;
		return "";
	}

	function makeAnchorCurrentWindow(anchor, route) {
		if (!anchor || !route) return;
		anchor.setAttribute("href", route);
		anchor.setAttribute("target", "_self");
		anchor.removeAttribute("rel");
	}

	function reconcileBillingSidebar() {
		for (const item of global.document?.querySelectorAll?.(".edge-app-shell[data-edge-product] .edge-sidebar-item") || []) {
			const route = sidebarBillingRoute(item);
			if (!route) continue;
			item.dataset.vetedgeCanonicalBillingRoute = route;
			if (item.matches?.("a")) makeAnchorCurrentWindow(item, route);
			for (const anchor of item.querySelectorAll?.("a") || []) makeAnchorCurrentWindow(anchor, route);
		}
	}

	function nativeBillingSessionTarget() {
		const path = String(global.location?.pathname || "").replace(/\/+$/, "");
		if (path === NATIVE_BILLING_SESSION_PATH) return BILLING_SESSIONS_ROUTE;
		if (!path.startsWith(`${NATIVE_BILLING_SESSION_PATH}/`)) return "";
		let name = path.slice(NATIVE_BILLING_SESSION_PATH.length + 1);
		try { name = decodeURIComponent(name); } catch (_error) { /* keep route text */ }
		if (!name || name === "new" || name.toLowerCase().startsWith("new-veterinary-billing-session")) return BILLING_SESSIONS_ROUTE;
		return billingSessionDetailRoute(name);
	}

	function redirectNativeBillingSession() {
		if (redirectingNativeSession) return false;
		const target = nativeBillingSessionTarget();
		if (!target) return false;
		redirectingNativeSession = true;
		currentWindow(target, { replace: true });
		return true;
	}

	function reconcile() {
		global.clearTimeout(scheduledReconcile);
		scheduledReconcile = null;
		reconcileBillingSidebar();
		redirectNativeBillingSession();
	}

	function scheduleReconcile(delay = 0) {
		global.clearTimeout(scheduledReconcile);
		scheduledReconcile = global.setTimeout(reconcile, delay);
	}

	global.document?.addEventListener("click", (event) => {
		const productItem = productItemFromEvent(event);
		if (productItem) {
			event.preventDefault();
			event.stopPropagation();
			event.stopImmediatePropagation();
			routeProductItem(productItem);
			return;
		}

		const sidebarItem = event.target?.closest?.(".edge-app-shell[data-edge-product] .edge-sidebar-item");
		const sidebarRoute = sidebarBillingRoute(sidebarItem);
		if (sidebarRoute) {
			event.preventDefault();
			event.stopPropagation();
			event.stopImmediatePropagation();
			currentWindow(sidebarRoute);
			return;
		}

		const nativeSessionAnchor = event.target?.closest?.(`a[href*="${NATIVE_BILLING_SESSION_PATH}"]`);
		if (nativeSessionAnchor) {
			const url = new URL(nativeSessionAnchor.href, global.location.origin);
			if (url.origin === global.location.origin) {
				event.preventDefault();
				event.stopPropagation();
				event.stopImmediatePropagation();
				let name = url.pathname.startsWith(`${NATIVE_BILLING_SESSION_PATH}/`)
					? url.pathname.slice(NATIVE_BILLING_SESSION_PATH.length + 1)
					: "";
				try { name = decodeURIComponent(name); } catch (_error) { /* keep route text */ }
				currentWindow(billingSessionDetailRoute(name));
			}
		}
	}, true);

	global.document?.addEventListener("input", (event) => {
		if (!isProductSearchInput(event.target)) return;
		filterProductMenu(panelContaining(event.target), event.target.value);
	}, true);

	global.document?.addEventListener("keydown", (event) => {
		if (event.key !== "Enter" || !isProductSearchInput(event.target)) return;
		const panel = panelContaining(event.target);
		const first = searchableItems(panel).find((item) => !item.hidden);
		if (!first) return;
		event.preventDefault();
		event.stopPropagation();
		routeProductItem(first);
	}, true);

	global.frappe?.router?.on?.("change", () => scheduleReconcile(0));
	global.addEventListener?.("popstate", () => scheduleReconcile(0));
	for (const eventName of ["toolbar_setup", "page-change", "desktop_screen", "sidebar_setup"]) {
		global.document?.addEventListener?.(eventName, () => scheduleReconcile(0));
	}

	if (global.MutationObserver && global.document?.body) {
		const observer = new global.MutationObserver(() => scheduleReconcile(50));
		observer.observe(global.document.body, { childList: true, subtree: true });
	}

	global.VetEdgeBillingNavigationGuard = {
		reconcile,
		filterProductMenu,
		billingSessionDetailRoute,
		redirectNativeBillingSession,
	};

	scheduleReconcile(0);
})(window);
