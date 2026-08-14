(function () {
	"use strict";

	if (window.__vetedgeResourceCenterActionAlignmentInstalled) return;
	window.__vetedgeResourceCenterActionAlignmentInstalled = true;

	function align(root = document) {
		root.querySelectorAll?.("[data-edge-registration-billing]").forEach((button) => {
			// Patient actions are now rendered from server billing state by the
			// Resource Center Vue table. Keep the legacy bridge sentinel in place
			// so it cannot re-inject a second generic button, but do not display it.
			button.hidden = true;
			button.setAttribute("aria-hidden", "true");
			button.tabIndex = -1;
		});
	}

	const observer = new MutationObserver((records) => {
		if (records.some((record) => record.type === "childList" && record.addedNodes.length)) {
			window.requestAnimationFrame(() => align(document));
		}
	});
	observer.observe(document.body, { childList: true, subtree: true });
	align(document);

	window.VetEdgeResourceCenterActionAlignment = { align };
})();
