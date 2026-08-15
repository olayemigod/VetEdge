(function () {
	"use strict";

	if (window.__vetedgeResourceCenterHardeningInstalled) return;
	window.__vetedgeResourceCenterHardeningInstalled = true;

	// Compatibility shim only.
	// Resource Center filtering, readable labels, Branch Scope and patient shortcuts
	// are now implemented directly in VetEdgeResourceCenter.vue. Keeping this global
	// avoids breaking cached pages or older loaders while preventing DOM mutation or
	// frappe.call argument rewriting from overriding the Vue source of truth.
	window.VetEdgeResourceCenterHardening = {
		install() {
			return true;
		},
	};
})();
