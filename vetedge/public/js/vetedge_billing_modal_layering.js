(function () {
	"use strict";

	if (window.__vetedgeBillingModalLayeringInstalled) return;
	window.__vetedgeBillingModalLayeringInstalled = true;

	const BILLING_TITLES = new Set(["Billing & Payment", "Record Payment"]);

	function isVisible(element) {
		if (!element) return false;
		const style = window.getComputedStyle(element);
		return style.display !== "none" && style.visibility !== "hidden";
	}

	function dialogTitle(wrapper) {
		const title = wrapper?.querySelector?.(".modal-title, .modal-header h4, .modal-header .title-text");
		return String(title?.textContent || "").trim();
	}

	function visibleLayerElements() {
		return [...document.querySelectorAll(".modal, [role='dialog'], .edge-modal, .edge-modal-backdrop")].filter(isVisible);
	}

	function highestLayer(exclude) {
		let highest = 1050;
		for (const element of visibleLayerElements()) {
			if (element === exclude || exclude?.contains?.(element)) continue;
			const value = Number.parseInt(window.getComputedStyle(element).zIndex, 10);
			if (Number.isFinite(value)) highest = Math.max(highest, value);
		}
		return highest;
	}

	function edgeBillingVisible() {
		return [...document.querySelectorAll(".vetedge-edge-modal-presenter-host [role='dialog'], .vetedge-edge-modal-presenter-host .edge-modal")].some(isVisible);
	}

	function elevate(wrapper, force = false) {
		if (!wrapper || (!force && !BILLING_TITLES.has(dialogTitle(wrapper)))) return false;
		const zIndex = highestLayer(wrapper) + 20;
		wrapper.style.zIndex = String(zIndex);
		wrapper.dataset.vetedgeBillingLayer = "1";
		const backdrops = [...document.querySelectorAll(".modal-backdrop")].filter(isVisible);
		const backdrop = backdrops.at(-1);
		if (backdrop) {
			backdrop.style.zIndex = String(zIndex - 10);
			backdrop.dataset.vetedgeBillingBackdrop = "1";
		}
		return true;
	}

	function elevateBillingDialogs() {
		const dialogs = [...document.querySelectorAll(".modal")].filter(isVisible);
		const hasEdgeBilling = edgeBillingVisible();
		for (const dialog of dialogs) {
			// When the shared EdgeSuite billing presenter is visible, any subsequently
			// opened native Frappe Message/validation dialog is a child interaction and
			// must sit above it. Legacy Billing/Record Payment dialogs retain the same
			// behavior for compatibility fallback.
			elevate(dialog, hasEdgeBilling || BILLING_TITLES.has(dialogTitle(dialog)));
		}
	}

	const observer = new MutationObserver(() => window.requestAnimationFrame(elevateBillingDialogs));
	observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "style"] });

	function wrapSharedModal() {
		const modal = window.vetedgeBillingModal;
		if (!modal?.open || modal.__layeringWrapped) return false;
		const originalOpen = modal.open.bind(modal);
		modal.open = function (...args) {
			const result = originalOpen(...args);
			window.requestAnimationFrame(elevateBillingDialogs);
			window.setTimeout(elevateBillingDialogs, 25);
			return result;
		};
		modal.__layeringWrapped = true;
		return true;
	}

	wrapSharedModal();
	window.setTimeout(wrapSharedModal, 0);
	window.setTimeout(wrapSharedModal, 250);
	window.VetEdgeBillingModalLayering = { elevateBillingDialogs, wrapSharedModal };
})();
