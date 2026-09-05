// Hard safety boundary: product navigation is allowed only on a visible EdgeSuite shell.
(function installVetEdgeProductMenuNativeGuard(global) {
	"use strict";

	if (!global?.document) return;

	const ARTIFACT_IDS = [
		"edge-product-menu-host",
		"edge-product-menu-dropdown",
		"edge-product-menu-slot",
		"edge-product-menu-navbar-bridge",
		"vetedge-product-menu-slot",
		"vetedge-product-menu-trigger",
		"vetedge-product-menu-panel",
	];
	let scheduled = false;

	function visibleElement(element) {
		if (!element?.isConnected) return false;
		const view = element.ownerDocument?.defaultView;
		let current = element;
		while (current?.nodeType === 1) {
			if (current.hidden || current.getAttribute?.("aria-hidden") === "true") return false;
			const style = view?.getComputedStyle?.(current);
			if (
				style?.display === "none" ||
				style?.visibility === "hidden" ||
				style?.contentVisibility === "hidden"
			) {
				return false;
			}
			current = current.parentElement;
		}
		const rects = element.getClientRects?.();
		if (rects?.length) return true;
		const box = element.getBoundingClientRect?.();
		return Boolean(box && box.width > 0 && box.height > 0);
	}

	function activeEdgeShell() {
		return Array.from(
			global.document.querySelectorAll(".edge-app-shell[data-edge-product]"),
		).find(visibleElement) || null;
	}

	function removeProductNavigationArtifacts() {
		global.EdgeSuiteUI?.closeProductMenu?.();
		ARTIFACT_IDS.forEach((id) => global.document.getElementById(id)?.remove());
		return true;
	}

	function reconcile() {
		scheduled = false;
		if (!activeEdgeShell()) {
			removeProductNavigationArtifacts();
			return;
		}
		if (
			!global.document.getElementById("edge-product-menu-trigger") &&
			!global.document.getElementById("vetedge-product-menu-trigger")
		) {
			global.VetedgeProductMenu?.remount?.("native-guard-active-shell");
		}
	}

	function scheduleReconcile() {
		if (scheduled) return;
		scheduled = true;
		(global.requestAnimationFrame || global.setTimeout)?.(reconcile, 0);
	}

	["DOMContentLoaded", "toolbar_setup", "sidebar_setup", "desktop_screen", "page-change"].forEach(
		(eventName) => global.document.addEventListener(eventName, scheduleReconcile),
	);
	global.document.addEventListener("visibilitychange", scheduleReconcile);
	["hashchange", "popstate", "pageshow", "resize", "orientationchange"].forEach((eventName) =>
		global.addEventListener?.(eventName, scheduleReconcile),
	);
	global.frappe?.router?.on?.("change", scheduleReconcile);

	if (global.MutationObserver && global.document.body) {
		const observer = new global.MutationObserver(scheduleReconcile);
		observer.observe(global.document.body, {
			childList: true,
			subtree: true,
			attributes: true,
			attributeFilter: ["class", "style", "hidden", "aria-hidden"],
		});
		global.VetedgeProductMenuNativeGuardObserver = observer;
	}

	global.VetedgeProductMenuNativeGuard = {
		activeEdgeShell,
		reconcile,
		removeProductNavigationArtifacts,
	};

	scheduleReconcile();
})(window);
