(function () {
	if (window.__vetedgeResourceClinicalBridgeInstalled) return;
	window.__vetedgeResourceClinicalBridgeInstalled = true;

	const RESOURCE_DOCTYPES = Object.freeze({
		"lab-orders": "Veterinary Lab Order",
		vaccinations: "Veterinary Vaccination Record",
	});
	const CREATE_LABELS = Object.freeze({
		"lab-orders": "New Lab Order",
		vaccinations: "New Vaccination",
	});
	const patientLabels = new Map();
	let observedRoot = null;
	let observer = null;
	let patientHydrationScheduled = false;

	function currentResource() {
		return new URLSearchParams(window.location.search || "").get("resource") || "patients";
	}

	function recordName(row) {
		const first = row?.querySelector?.("td");
		return String(first?.textContent || "").trim();
	}

	function refreshResourceCenter(root) {
		const buttons = [...(root?.querySelectorAll?.(".edge-filter-bar__actions button") || [])];
		const apply = buttons.find((button) => String(button.textContent || "").trim() === "Apply");
		apply?.click?.();
	}

	function decorateCreateAction(root, resource, doctype) {
		const host = root.querySelector(".edge-page-header__actions");
		if (!host) return;
		const existing = host.querySelector("[data-edge-clinical-create]");
		if (existing) {
			existing.textContent = CREATE_LABELS[resource] || "New Record";
			return;
		}
		const button = document.createElement("button");
		button.type = "button";
		button.className = "edge-button edge-button--primary";
		button.dataset.edgeClinicalCreate = "1";
		button.textContent = CREATE_LABELS[resource] || "New Record";
		button.addEventListener("click", () => {
			window.VetEdgeClinicalRecordEditor?.create?.(doctype, () => refreshResourceCenter(root));
		});
		host.prepend(button);
	}

	async function hydratePatientCells(root) {
		patientHydrationScheduled = false;
		if (!root || !RESOURCE_DOCTYPES[currentResource()]) return;
		const headings = [...root.querySelectorAll(".vetedge-resource-table thead th")];
		const patientIndex = headings.findIndex((heading) => String(heading.textContent || "").trim().toLowerCase() === "patient");
		if (patientIndex < 0) return;
		const cells = [...root.querySelectorAll(".vetedge-resource-table tbody tr")]
			.map((row) => row.querySelectorAll("td")[patientIndex])
			.filter(Boolean);
		const ids = [];
		for (const cell of cells) {
			const raw = cell.dataset.patientId || String(cell.textContent || "").trim();
			if (!raw || raw === "—") continue;
			cell.dataset.patientId = raw;
			if (!patientLabels.has(raw)) ids.push(raw);
		}
		const unique = [...new Set(ids)];
		if (unique.length) {
			try {
				const response = await frappe.call("vetedge.services.display_names.get_patient_labels", { names: unique });
				for (const [key, value] of Object.entries(response.message || {})) patientLabels.set(key, value || key);
			} catch (_error) {
				// Keep the permission-safe record ID if display-name enrichment is unavailable.
			}
		}
		for (const cell of cells) {
			const raw = cell.dataset.patientId;
			if (raw && patientLabels.has(raw)) cell.textContent = patientLabels.get(raw);
		}
	}

	function schedulePatientHydration(root) {
		if (patientHydrationScheduled) return;
		patientHydrationScheduled = true;
		window.requestAnimationFrame(() => hydratePatientCells(root));
	}

	function decorate(root) {
		const resource = currentResource();
		const doctype = RESOURCE_DOCTYPES[resource];
		if (!doctype || !root) return;
		decorateCreateAction(root, resource, doctype);
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
				window.VetEdgeClinicalRecordEditor?.open?.({ doctype, name, onSaved: () => refreshResourceCenter(root) });
			});
			actions.prepend(button);
		});
		schedulePatientHydration(root);
	}

	function install() {
		const root = document.querySelector(".vetedge-resource-center-root");
		if (!root) return false;
		decorate(root);
		if (observedRoot === root && observer) return true;
		observer?.disconnect?.();
		observedRoot = root;
		observer = new MutationObserver(() => decorate(root));
		observer.observe(root, { childList: true, subtree: true });
		return true;
	}

	window.VetEdgeResourceClinicalBridge = { install };
	window.addEventListener("popstate", () => observedRoot && decorate(observedRoot));
	window.setTimeout(install, 0);
})();