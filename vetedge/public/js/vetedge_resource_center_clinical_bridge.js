(function () {
	"use strict";

	if (window.__vetedgeResourceClinicalBridgeInstalled) return;
	window.__vetedgeResourceClinicalBridgeInstalled = true;

	// Compatibility shim only.
	// Clinical create/edit actions, patient display labels and registration billing
	// now render directly from the Resource Center Vue source. This keeps older page
	// loaders harmless without adding duplicate buttons or mutating table cells.
	window.VetEdgeResourceClinicalBridge = {
		install() {
			return true;
		},
	};
})();
