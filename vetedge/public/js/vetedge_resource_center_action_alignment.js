(function () {
	"use strict";

	if (window.__vetedgeResourceCenterActionAlignmentInstalled) return;
	window.__vetedgeResourceCenterActionAlignmentInstalled = true;

	// Compatibility shim only.
	// Same-tab full-form navigation, registration billing actions and clinical
	// shortcuts are now rendered and handled directly by VetEdgeResourceCenter.vue.
	// Retaining this global avoids cached-loader errors without observing or
	// mutating the Resource Center DOM.
	window.VetEdgeResourceCenterActionAlignment = {
		align() {
			return true;
		},
	};
})();
