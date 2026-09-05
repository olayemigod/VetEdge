(function installVetEdgePostQaNavigationHardening(global) {
	"use strict";

	if (!global || global.__vetedgePostQaNavigationHardeningInstalled) return;
	global.__vetedgePostQaNavigationHardeningInstalled = true;

	const SHELL_SELECTOR = ".edge-app-shell[data-edge-product]";
	const HOME_DATASET_KEY = "vetedgeDirectHome";
	const HOME_ATTRIBUTE = "data-vetedge-direct-home";
	const PRODUCT_HOST_ID = "edge-product-menu-host";
	const PRODUCT_TRIGGER_ID = "edge-product-menu-trigger";
	const PRODUCT_PANEL_ID = "edge-product-menu-dropdown";
	const PRODUCT_OPEN_CLASS = "edge-product-menu--open";
	const LIFECYCLE_EVENTS = ["toolbar_setup", "page-change", "desktop_screen", "sidebar_setup"];
	let scheduled = null;
	let observer = null;

	function runtime() {
		return global.EdgeSuiteUI || global.EdgeUI || null;
	}

	function visible(element) {
		if (!element?.isConnected || element.hidden || element.getAttribute?.("aria-hidden") === "true") return false;
		const style = global.getComputedStyle?.(element);
		if (style?.display === "none" || style?.visibility === "hidden" || style?.contentVisibility === "hidden") return false;
		const rect = element.getBoundingClientRect?.();
		return Boolean(rect && rect.width > 0 && rect.height > 0);
	}

	function vetedgeShell() {
		return Array.from(global.document?.querySelectorAll?.(SHELL_SELECTOR) || []).find((shell) => {
			const product = String(shell.dataset?.edgeProduct || "").trim().toLowerCase();
			return visible(shell) && (product === "vetedge" || product === "veterinary");
		}) || null;
	}

	function directHomeTarget() {
		return String(global.location?.pathname || "").replace(/\/+$/, "") === "/desk/vetedge";
	}

	function navigateHome() {
		if (global.VetEdgeNavigationRecovery?.navigate?.("/desk/vetedge")) return true;
		const adapter = runtime()?.getAdapter?.("navigation:vetedge") || runtime()?.getAdapter?.("navigation:veterinary");
		if (adapter?.open?.("/desk/vetedge")) return true;
		if (typeof global.frappe?.set_route === "function") {
			global.frappe.set_route("vetedge");
			return true;
		}
		global.location?.assign?.("/desk/vetedge");
		return true;
	}

	function sectionLabel(toggle) {
		const labelNode = Array.from(toggle?.children || []).find((node) => !node.classList?.contains("edge-icon"));
		return String(labelNode?.textContent || toggle?.textContent || "").trim();
	}

	function syncDirectHomeState(item) {
		if (!item) return false;
		item.dataset[HOME_DATASET_KEY] = "1";
		item.setAttribute("aria-label", "Home");
		item.setAttribute("title", "Home");
		item.removeAttribute("aria-expanded");
		item.removeAttribute("aria-controls");
		const active = directHomeTarget();
		item.classList.toggle("active", active);
		if (active) item.setAttribute("aria-current", "page");
		else item.removeAttribute("aria-current");
		return true;
	}

	function patchDirectHome(shell) {
		const existing = shell.querySelector(`.edge-sidebar-item[${HOME_ATTRIBUTE}="1"]`);
		if (existing) return syncDirectHomeState(existing);

		const homeSection = Array.from(shell.querySelectorAll(".edge-sidebar__section")).find((section) => {
			return sectionLabel(section.querySelector(".edge-sidebar__section-toggle")) === "Home";
		});
		if (!homeSection) return false;

		const toggle = homeSection.querySelector(".edge-sidebar__section-toggle");
		const nestedItem = homeSection.querySelector(".edge-sidebar__items .edge-sidebar-item");
		if (!toggle && !nestedItem) return false;

		// Home is navigation, not a category. Replace the one-item accordion
		// section with the actual sidebar item so there is no chevron, expansion
		// state, hidden child, or second click required. Clone the generated child
		// when available so EdgeSuite keeps its canonical icon/label markup.
		const directItem = nestedItem?.cloneNode(true) || toggle.cloneNode(true);
		directItem.classList.remove("edge-sidebar__section-toggle");
		directItem.classList.add("edge-sidebar-item");
		if (directItem.tagName === "BUTTON") directItem.type = "button";
		if (directItem.tagName === "A") directItem.setAttribute("href", "/desk/vetedge");
		directItem.querySelectorAll(".edge-icon").forEach((icon, index) => {
			if (index > 0) icon.remove();
		});
		syncDirectHomeState(directItem);
		homeSection.replaceWith(directItem);
		return true;
	}

	function sharedProductConfig() {
		try {
			return runtime()?.getProductMenuConfig?.() || null;
		} catch (_error) {
			return null;
		}
	}

	function productTarget(shell) {
		return shell.querySelector(".edge-topbar-actions") || shell.querySelector(".edge-topbar__brand") || null;
	}

	function gridIcon() {
		try {
			const icon = global.frappe?.utils?.icon?.("grid", "sm");
			if (icon) return icon;
		} catch (_error) {
			// Deterministic SVG fallback below.
		}
		return '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><circle cx="4" cy="4" r="1.5"></circle><circle cx="10" cy="4" r="1.5"></circle><circle cx="16" cy="4" r="1.5"></circle><circle cx="4" cy="10" r="1.5"></circle><circle cx="10" cy="10" r="1.5"></circle><circle cx="16" cy="10" r="1.5"></circle><circle cx="4" cy="16" r="1.5"></circle><circle cx="10" cy="16" r="1.5"></circle><circle cx="16" cy="16" r="1.5"></circle></svg>';
	}

	function createSharedHost(target) {
		const doc = global.document;
		let host = doc.getElementById(PRODUCT_HOST_ID);
		let trigger = doc.getElementById(PRODUCT_TRIGGER_ID);
		let panel = doc.getElementById(PRODUCT_PANEL_ID);

		if (!host) {
			host = doc.createElement("span");
			host.id = PRODUCT_HOST_ID;
			host.className = "edge-product-menu__host";
		}
		if (!trigger) {
			trigger = doc.createElement("button");
			trigger.id = PRODUCT_TRIGGER_ID;
			trigger.type = "button";
			trigger.className = "edge-product-menu__trigger";
			trigger.setAttribute("aria-haspopup", "menu");
			trigger.setAttribute("aria-expanded", "false");
			trigger.setAttribute("aria-label", "Open Veterinary product menu");
			trigger.innerHTML = gridIcon();
			host.appendChild(trigger);
		} else if (!host.contains(trigger)) {
			host.appendChild(trigger);
		}
		if (!target.contains(host)) target.prepend(host);

		if (!panel) {
			panel = doc.createElement("aside");
			panel.id = PRODUCT_PANEL_ID;
			panel.className = "edge-product-menu";
			panel.hidden = true;
			panel.setAttribute("role", "dialog");
			panel.setAttribute("aria-modal", "false");
			doc.body.appendChild(panel);
		}
		return { host, trigger, panel };
	}

	function routeProductItem(node) {
		const config = sharedProductConfig();
		const item = {
			link_type: node?.dataset?.linkType || "Page",
			link_to: node?.dataset?.linkTo || "",
			route: node?.dataset?.route || "",
		};
		if (typeof config?.navigate === "function") {
			config.navigate(item);
			return true;
		}
		if (item.route && global.VetEdgeNavigationRecovery?.navigate?.(item.route)) return true;
		return false;
	}

	function filterProductPanel(panel, query) {
		const term = String(query || "").trim().toLowerCase();
		let count = 0;
		panel.querySelectorAll(".edge-product-menu__section").forEach((section) => {
			let sectionCount = 0;
			section.querySelectorAll(".edge-product-menu__item").forEach((item) => {
				const match = !term || String(item.textContent || "").toLowerCase().includes(term);
				item.hidden = !match;
				if (match) {
					sectionCount += 1;
					count += 1;
				}
			});
			section.hidden = sectionCount === 0;
		});
		const resultCount = panel.querySelector(".edge-product-menu__result-count");
		if (resultCount) resultCount.textContent = String(count);
	}

	function bindRepairedProductMenu(host, trigger, panel) {
		if (host.dataset.vetedgeProductMenuBridgeBound === "1") return;
		host.dataset.vetedgeProductMenuBridgeBound = "1";

		trigger.addEventListener("click", (event) => {
			// This listener is capture-bound only for a repaired EdgeSuite-shell host,
			// so the original native-navbar listener cannot double-toggle the menu.
			event.preventDefault();
			event.stopPropagation();
			event.stopImmediatePropagation();
			const edgeUI = runtime();
			if (!edgeUI) return;
			if (panel.hidden) edgeUI.openProductMenu?.();
			else edgeUI.closeProductMenu?.();
		}, true);

		panel.addEventListener("click", (event) => {
			const close = event.target?.closest?.(".edge-product-menu__close");
			if (close) {
				event.preventDefault();
				runtime()?.closeProductMenu?.();
				return;
			}
			const item = event.target?.closest?.(".edge-product-menu__item");
			if (!item) return;
			event.preventDefault();
			event.stopPropagation();
			routeProductItem(item);
			runtime()?.closeProductMenu?.();
		}, true);

		panel.addEventListener("input", (event) => {
			if (!event.target?.matches?.(".edge-product-menu__search")) return;
			filterProductPanel(panel, event.target.value);
		});
	}

	function ensureProductMenu(shell) {
		const edgeUI = runtime();
		const config = sharedProductConfig();
		if (!edgeUI || !config || !Array.isArray(config.sections) || !config.sections.length) return false;

		try { edgeUI.mountProductMenu?.(); } catch (_error) { /* bridge below */ }
		let host = global.document.getElementById(PRODUCT_HOST_ID);
		let trigger = global.document.getElementById(PRODUCT_TRIGGER_ID);
		let panel = global.document.getElementById(PRODUCT_PANEL_ID);
		if (trigger && panel && visible(trigger)) return true;

		const target = productTarget(shell);
		if (!target) return false;
		({ host, trigger, panel } = createSharedHost(target));
		host.dataset.vetedgeProductMenuBridge = "1";
		bindRepairedProductMenu(host, trigger, panel);
		try { edgeUI.refreshProductMenu?.(); } catch (_error) { /* config remains available */ }
		return visible(trigger);
	}

	function repairUnresponsiveSharedTrigger(event) {
		const trigger = event.target?.closest?.(`#${PRODUCT_TRIGGER_ID}`);
		if (!trigger) return;
		const panel = global.document.getElementById(PRODUCT_PANEL_ID);
		if (!panel) return;
		global.setTimeout(() => {
			if (!panel.hidden || trigger.getAttribute("aria-expanded") === "true") return;
			const shell = vetedgeShell();
			if (!shell) return;
			ensureProductMenu(shell);
			try { runtime()?.openProductMenu?.(); } catch (_error) { /* leave repaired trigger available */ }
		}, 0);
	}

	function reconcile() {
		global.clearTimeout(scheduled);
		scheduled = null;
		const shell = vetedgeShell();
		if (!shell) return false;
		patchDirectHome(shell);
		ensureProductMenu(shell);
		return true;
	}

	function schedule(delay = 0) {
		global.clearTimeout(scheduled);
		scheduled = global.setTimeout(reconcile, delay);
	}

	global.document?.addEventListener("click", (event) => {
		const directHome = event.target?.closest?.(`[${HOME_ATTRIBUTE}="1"]`);
		if (directHome) {
			event.preventDefault();
			event.stopPropagation();
			event.stopImmediatePropagation();
			navigateHome();
			return;
		}
		repairUnresponsiveSharedTrigger(event);
	}, true);

	LIFECYCLE_EVENTS.forEach((eventName) => global.document?.addEventListener(eventName, () => schedule(0)));
	global.frappe?.router?.on?.("change", () => schedule(0));
	global.addEventListener?.("popstate", () => schedule(0));

	if (global.MutationObserver && global.document?.body) {
		observer = new global.MutationObserver(() => {
			const shell = vetedgeShell();
			if (!shell) return;
			const homePatched = shell.querySelector(`[${HOME_ATTRIBUTE}="1"]`);
			const trigger = global.document.getElementById(PRODUCT_TRIGGER_ID);
			if (!homePatched || !trigger || !visible(trigger)) schedule(50);
		});
		observer.observe(global.document.body, { childList: true, subtree: true });
	}

	global.VetEdgePostQaNavigation = {
		reconcile,
		ensureProductMenu: () => {
			const shell = vetedgeShell();
			return shell ? ensureProductMenu(shell) : false;
		},
		navigateHome,
		state() {
			const shell = vetedgeShell();
			const host = global.document?.getElementById(PRODUCT_HOST_ID);
			return {
				activeShell: Boolean(shell),
				directHome: Boolean(shell?.querySelector?.(`[${HOME_ATTRIBUTE}="1"]`)),
				productTriggerVisible: visible(global.document?.getElementById(PRODUCT_TRIGGER_ID)),
				productMenuBridged: host?.dataset?.vetedgeProductMenuBridge === "1",
				productMenuOpen: !global.document?.getElementById(PRODUCT_PANEL_ID)?.hidden && global.document?.documentElement?.classList?.contains(PRODUCT_OPEN_CLASS),
			};
		},
	};

	if (global.document?.readyState === "loading") {
		global.document.addEventListener("DOMContentLoaded", () => schedule(0), { once: true });
	} else {
		schedule(0);
	}
})(window);