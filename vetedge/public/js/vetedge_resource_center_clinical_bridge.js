(function () {
	if (window.__vetedgeResourceClinicalBridgeInstalled) return;
	window.__vetedgeResourceClinicalBridgeInstalled = true;

	const RESOURCE_DOCTYPES = Object.freeze({
		"lab-orders": "Veterinary Lab Order",
		vaccinations: "Veterinary Vaccination Record",
	});

	function currentResource() {
		return new URLSearchParams(window.location.search || "").get("resource") || "patients";
	}

	function recordName(row) {
		const first = row?.querySelector?.("td");
		return String(first?.textContent || "").trim();
	}

	function decorate(root) {
		const doctype = RESOURCE_DOCTYPES[currentResource()];
		if (!doctype || !root) return;
		root.querySelectorAll(".vetedge-resource-table tbody tr").forEach((row) => {
			const name = recordName(row);
			const actions = row.querySelector(".vetedge-resource-row-actions");
			if (!name || !actions || actions.querySelector("[data-edge-clinical-editor]")) return;
			const button = document.createElement("button");
			button.type = "button";
			button.className = "edge-button edge-button--compact edge-button--primary";
			button.dataset.edgeClinicalEditor = "1";
			button.textContent = "View / Edit";
			button.addEventListener("click", (event) => {
				event.preventDefault();
				event.stopPropagation();
				window.VetEdgeClinicalRecordEditor?.open?.({ doctype, name });
			});
			actions.prepend(button);
		});
	}

	function install() {
		const root = document.querySelector(".vetedge-resource-center-root");
		if (!root) return false;
		decorate(root);
		const observer = new MutationObserver(() => decorate(root));
		observer.observe(root, { childList: true, subtree: true });
		window.addEventListener("popstate", () => decorate(root));
		return true;
	}

	window.VetEdgeResourceClinicalBridge = { install };
	window.setTimeout(install, 0);
})();
