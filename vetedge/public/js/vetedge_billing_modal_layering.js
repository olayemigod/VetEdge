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
		return [...document.querySelectorAll(".modal, [role='dialog'], .edge-modal, .edge-modal-backdrop")]
			.filter(isVisible);
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

	function elevate(wrapper) {
		if (!wrapper || !BILLING_TITLES.has(dialogTitle(wrapper))) return false;
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
		for (const dialog of dialogs) elevate(dialog);
	}

	const observer = new MutationObserver(() => {
		window.requestAnimationFrame(elevateBillingDialogs);
	});
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
