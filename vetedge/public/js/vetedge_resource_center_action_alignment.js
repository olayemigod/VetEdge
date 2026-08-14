(function () {
	"use strict";

	if (window.__vetedgeResourceCenterActionAlignmentInstalled) return;
	window.__vetedgeResourceCenterActionAlignmentInstalled = true;

	const FULL_FORM_ROUTES = Object.freeze({
		patients: "/desk/veterinary-patient",
		appointments: "/desk/veterinary-appointment",
		"missed-appointments": "/desk/veterinary-missed-appointment",
		consultations: "/desk/veterinary-consultation",
		"lab-orders": "/desk/veterinary-lab-order",
		vaccinations: "/desk/veterinary-vaccination-record",
		grooming: "/desk/pet-grooming-appointment",
		boarding: "/desk/pet-boarding-booking",
		kennels: "/desk/kennel",
	});

	function currentResource() {
		return new URLSearchParams(window.location.search || "").get("resource") || "patients";
	}

	function rowName(button) {
		const row = button.closest(".vetedge-resource-table tbody tr");
		return String(row?.querySelector("td")?.textContent || "").trim();
	}

	function sameTabFullForm(button) {
		const base = FULL_FORM_ROUTES[currentResource()];
		if (!base) return false;
		const name = rowName(button);
		const route = name ? `${base}/${encodeURIComponent(name)}` : base;
		window.location.assign(route);
		return true;
	}

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

	document.addEventListener("click", (event) => {
		const button = event.target?.closest?.(".vetedge-resource-center-root button");
		if (!button) return;
		const label = String(button.textContent || "").trim().toLowerCase();
		if (label !== "open full form") return;
		if (!sameTabFullForm(button)) return;
		event.preventDefault();
		event.stopImmediatePropagation();
	}, true);

	const observer = new MutationObserver((records) => {
		if (records.some((record) => record.type === "childList" && record.addedNodes.length)) {
			window.requestAnimationFrame(() => align(document));
		}
	});
	observer.observe(document.body, { childList: true, subtree: true });
	align(document);

	window.VetEdgeResourceCenterActionAlignment = { align, sameTabFullForm };
})();
