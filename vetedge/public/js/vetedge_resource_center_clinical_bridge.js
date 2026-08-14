(function () {
	"use strict";

	if (window.__vetedgeResourceClinicalBridgeInstalled) return;
	window.__vetedgeResourceClinicalBridgeInstalled = true;

	const CLINICAL_DOCTYPES = Object.freeze({
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
	let decorationScheduled = false;

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

	function billingFrame(doctype, name, reload) {
		return {
			doc: { doctype, name },
			is_new: () => false,
			is_dirty: () => false,
			reload_doc: async () => reload?.(),
		};
	}

	function decorateCreateAction(root, resource, doctype) {
		const host = root.querySelector(".edge-page-header__actions");
		if (!host) return;
		const label = CREATE_LABELS[resource] || "New Record";
		const existing = host.querySelector("[data-edge-clinical-create]");
		if (existing) {
			if (String(existing.textContent || "").trim() !== label) existing.textContent = label;
			return;
		}
		const button = document.createElement("button");
		button.type = "button";
		button.className = "edge-button edge-button--primary";
		button.dataset.edgeClinicalCreate = "1";
		button.textContent = label;
		button.addEventListener("click", () => {
			window.VetEdgeClinicalRecordEditor?.create?.(doctype, () => refreshResourceCenter(root));
		});
		host.prepend(button);
	}

	function decorateClinicalRows(root, doctype) {
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
	}

	function decoratePatientBilling(root) {
		root.querySelectorAll(".vetedge-resource-table tbody tr").forEach((row) => {
			const name = recordName(row);
			const actions = row.querySelector(".vetedge-resource-row-actions");
			if (!name || !actions || actions.querySelector("[data-edge-registration-billing]")) return;
			const button = document.createElement("button");
			button.type = "button";
			button.className = "edge-button edge-button--compact edge-button--primary";
			button.dataset.edgeRegistrationBilling = "1";
			button.textContent = __("Registration Billing / Payment");
			button.addEventListener("click", (event) => {
				event.preventDefault();
				event.stopPropagation();
				if (!window.vetedgeBillingModal?.open) {
					frappe.msgprint(__("The shared VetEdge Billing & Payment modal is unavailable. Refresh the page and try again."));
					return;
				}
				window.vetedgeBillingModal.open(billingFrame("Veterinary Patient", name, () => refreshResourceCenter(root)));
			});
			actions.prepend(button);
		});
	}

	async function hydratePatientCells(root) {
		patientHydrationScheduled = false;
		if (!root || !CLINICAL_DOCTYPES[currentResource()]) return;
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
			const label = raw ? patientLabels.get(raw) : "";
			if (label && String(cell.textContent || "").trim() !== String(label)) cell.textContent = label;
		}
	}

	function schedulePatientHydration(root) {
		if (patientHydrationScheduled) return;
		patientHydrationScheduled = true;
		window.requestAnimationFrame(() => hydratePatientCells(root));
	}

	function decorate(root) {
		if (!root) return;
		const resource = currentResource();
		const doctype = CLINICAL_DOCTYPES[resource];
		if (doctype) {
			decorateCreateAction(root, resource, doctype);
			decorateClinicalRows(root, doctype);
			schedulePatientHydration(root);
		}
		if (resource === "patients") decoratePatientBilling(root);
	}

	function isBridgeOwnedNode(node) {
		const element = node?.nodeType === 1 ? node : node?.parentElement;
		if (!element) return false;
		return Boolean(element.closest?.(
			"[data-edge-clinical-create], [data-edge-clinical-editor], [data-edge-registration-billing], td[data-patient-id]"
		));
	}

	function mutationNeedsDecoration(record) {
		if (record.type !== "childList") return false;
		if (isBridgeOwnedNode(record.target)) return false;
		const changed = [...(record.addedNodes || []), ...(record.removedNodes || [])];
		if (!changed.length) return false;
		return changed.some((node) => !isBridgeOwnedNode(node));
	}

	function scheduleDecoration(root) {
		if (decorationScheduled) return;
		decorationScheduled = true;
		window.requestAnimationFrame(() => {
			decorationScheduled = false;
			decorate(root);
		});
	}

	function install(explicitRoot = null) {
		const root = explicitRoot || document.querySelector(".vetedge-resource-center-root");
		if (!root) return false;
		decorate(root);
		if (observedRoot === root && observer) return true;
		observer?.disconnect?.();
		observedRoot = root;
		observer = new MutationObserver((records) => {
			if (records.some(mutationNeedsDecoration)) scheduleDecoration(root);
		});
		observer.observe(root, { childList: true, subtree: true });
		return true;
	}

	window.VetEdgeResourceClinicalBridge = { install };
	window.addEventListener("popstate", () => observedRoot && scheduleDecoration(observedRoot));
	window.setTimeout(install, 0);
})();
