(function () {
	"use strict";

	if (window.__vetedgeResourceCenterHardeningInstalled) return;
	window.__vetedgeResourceCenterHardeningInstalled = true;

	const CLINICAL_RESOURCES = new Set(["lab-orders", "vaccinations"]);
	const filterState = {};
	let lastPage = null;
	let mounted = null;
	let scheduled = false;

	function currentResource() {
		return new URLSearchParams(window.location.search || "").get("resource") || "patients";
	}

	function stateFor(resource) {
		if (!filterState[resource]) {
			const params = new URLSearchParams(window.location.search || "");
			filterState[resource] = {
				patient: params.get("patient") || "",
				service_branch: params.get("service_branch") || params.get("branch") || "",
				status: params.get("status") || "",
				from_date: params.get("from_date") || "",
				to_date: params.get("to_date") || "",
				vaccine: params.get("vaccine") || "",
				lab_test: params.get("lab_test") || "",
			};
		}
		return filterState[resource];
	}

	function installCallBridge() {
		if (frappe.call.__vetedgeResourceFilterBridge) return;
		const original = frappe.call.bind(frappe);
		const wrapped = function (methodOrOptions, args) {
			const method = typeof methodOrOptions === "string" ? methodOrOptions : methodOrOptions?.method;
			if (method === "vetedge.services.resource_center.get_resource_page") {
				const targetArgs = typeof methodOrOptions === "string"
					? (args || {})
					: (methodOrOptions.args || (methodOrOptions.args = {}));
				const resource = String(targetArgs.resource || currentResource());
				if (CLINICAL_RESOURCES.has(resource)) Object.assign(targetArgs, stateFor(resource));
			}
			const result = original(methodOrOptions, args);
			if (method === "vetedge.services.resource_center.get_resource_page" && result?.then) {
				result.then((response) => {
					lastPage = response?.message || null;
					scheduleAlign();
				}).catch(() => {});
			}
			return result;
		};
		wrapped.__vetedgeResourceFilterBridge = true;
		frappe.call = wrapped;
	}

	function searchLink(doctype, query) {
		return frappe.call("frappe.desk.search.search_link", {
			doctype,
			txt: String(query || ""),
			page_length: 20,
			ignore_user_permissions: 0,
		}).then((response) => response.message || []);
	}

	function syncUrl(resource, values) {
		const params = new URLSearchParams(window.location.search || "");
		params.set("resource", resource);
		for (const key of ["patient", "service_branch", "status", "from_date", "to_date", "vaccine", "lab_test"]) {
			if (values[key]) params.set(key, values[key]);
			else params.delete(key);
		}
		window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
	}

	function triggerApply(root) {
		const buttons = [...root.querySelectorAll(".edge-filter-bar__actions button")];
		const apply = buttons.find((button) => String(button.textContent || "").trim() === "Apply");
		apply?.click?.();
	}

	function filterComponent(resource, root) {
		const edge = window.EdgeSuiteUI || window.EdgeUI;
		const Vue = edge?.Vue;
		if (!Vue?.defineComponent || !Vue?.h) return null;
		const { EdgeLinkField, EdgeDropdown, EdgeInput } = edge.components || {};
		if (!EdgeLinkField || !EdgeDropdown || !EdgeInput) return null;
		const values = stateFor(resource);
		const statusOptions = (resource === "lab-orders"
			? ["Draft", "Ordered", "Sample Collected", "Sent to Lab", "In Progress", "Result Pending", "Result Entered", "Awaiting Review", "Reviewed", "Completed", "Cancelled"]
			: ["Draft", "Awaiting Payment", "Pending Administration", "Administered", "Cancelled"]
		).map((value) => ({ value, label: value }));
		return Vue.defineComponent({
			name: "VetEdgeResourceClinicalFilters",
			data: () => ({ values: { ...values } }),
			methods: {
				set(field, value) { this.values[field] = value || ""; },
				apply() {
					filterState[resource] = { ...this.values };
					syncUrl(resource, this.values);
					triggerApply(root);
				},
				reset() {
					this.values = { patient: "", service_branch: "", status: "", from_date: "", to_date: "", vaccine: "", lab_test: "" };
					filterState[resource] = { ...this.values };
					syncUrl(resource, this.values);
					triggerApply(root);
				},
			},
			render() {
				const h = Vue.h;
				const serviceField = resource === "lab-orders"
					? h(EdgeLinkField, { modelValue: this.values.lab_test, label: __("Lab Test"), placeholder: __("All Lab Tests"), searcher: (q) => searchLink("Veterinary Lab Test", q), "onUpdate:modelValue": (v) => this.set("lab_test", v) })
					: h(EdgeLinkField, { modelValue: this.values.vaccine, label: __("Vaccine"), placeholder: __("All Vaccines"), searcher: (q) => searchLink("Veterinary Vaccine", q), "onUpdate:modelValue": (v) => this.set("vaccine", v) });
				return h("div", { class: "vetedge-resource-clinical-filters" }, [
					h(EdgeLinkField, { modelValue: this.values.patient, label: __("Patient"), placeholder: __("All Patients"), searcher: (q) => searchLink("Veterinary Patient", q), "onUpdate:modelValue": (v) => this.set("patient", v) }),
					h(EdgeLinkField, { modelValue: this.values.service_branch, label: __("Branch"), placeholder: __("All permitted branches"), searcher: (q) => searchLink("Branch", q), "onUpdate:modelValue": (v) => this.set("service_branch", v) }),
					h(EdgeDropdown, { modelValue: this.values.status, label: __("Status"), placeholder: __("All statuses"), options: statusOptions, "onUpdate:modelValue": (v) => this.set("status", v) }),
					serviceField,
					h(EdgeInput, { modelValue: this.values.from_date, type: "date", label: __("From Date"), "onUpdate:modelValue": (v) => this.set("from_date", v) }),
					h(EdgeInput, { modelValue: this.values.to_date, type: "date", label: __("To Date"), "onUpdate:modelValue": (v) => this.set("to_date", v) }),
					h("div", { class: "vetedge-resource-clinical-filter-actions" }, [
						h("button", { type: "button", class: "edge-button edge-button--primary", onClick: this.apply }, __("Apply Clinical Filters")),
						h("button", { type: "button", class: "edge-button", onClick: this.reset }, __("Reset")),
					]),
				]);
			},
		});
	}

	function mountFilters(root, resource) {
		const existing = root.querySelector(".vetedge-resource-clinical-filter-host");
		if (!CLINICAL_RESOURCES.has(resource)) {
			if (mounted?.app) mounted.app.unmount?.();
			mounted = null;
			existing?.remove?.();
			return;
		}
		if (mounted?.resource === resource && existing) return;
		if (mounted?.app) mounted.app.unmount?.();
		existing?.remove?.();
		const filterBar = root.querySelector(".edge-filter-bar");
		if (!filterBar) return;
		const host = document.createElement("div");
		host.className = "vetedge-resource-clinical-filter-host";
		const actions = filterBar.querySelector(".edge-filter-bar__actions");
		if (actions) filterBar.insertBefore(host, actions);
		else filterBar.appendChild(host);
		const edge = window.EdgeSuiteUI || window.EdgeUI;
		const component = filterComponent(resource, root);
		if (!component || !edge?.createEdgeApp) return;
		const app = edge.createEdgeApp(component);
		app.mount(host);
		mounted = { resource, app, host };
	}

	function setTextIfChanged(node, value) {
		if (!node) return;
		const next = String(value ?? "");
		if (String(node.textContent || "").trim() !== next.trim()) node.textContent = next;
	}

	function alignSummary(root) {
		root.querySelector(".vetedge-resource-notice")?.remove?.();
		const cards = [...root.querySelectorAll(".vetedge-resource-summary > div")];
		if (cards.length >= 3) {
			setTextIfChanged(cards[2].querySelector("span"), lastPage?.summary_label || __("Branch Scope"));
			setTextIfChanged(cards[2].querySelector("strong"), lastPage?.summary_value || lastPage?.context_branch || __("All permitted branches"));
		}
	}

	function alignDisplayLabels(root) {
		if (!lastPage?.rows?.length || !lastPage?.columns?.length) return;
		const byName = new Map(lastPage.rows.map((row) => [String(row.name || ""), row]));
		root.querySelectorAll(".vetedge-resource-table tbody tr").forEach((tr) => {
			const cells = [...tr.querySelectorAll("td")];
			const name = String(cells[0]?.textContent || "").trim();
			const row = byName.get(name);
			if (!row?._display) return;
			lastPage.columns.forEach((column, index) => {
				const label = row._display[column.fieldname];
				const cell = cells[index];
				if (!label || !cell) return;
				setTextIfChanged(cell.querySelector("span") || cell, label);
			});
		});
	}

	function alignPatientShortcut(root, resource) {
		if (resource !== "patients") return;
		root.querySelectorAll(".vetedge-resource-row-actions").forEach((actions) => {
			const button = [...actions.querySelectorAll("button")].find((candidate) => String(candidate.textContent || "").trim() === "New Lab Order");
			if (!button) return;
			const row = actions.closest("tr");
			const patient = String(row?.querySelector("td")?.textContent || "").trim();
			setTextIfChanged(button, __("New Consultation"));
			button.dataset.vetedgeNewConsultation = "1";
			button.dataset.patient = patient;
		});
	}

	function align() {
		scheduled = false;
		const root = document.querySelector(".vetedge-resource-center-root");
		if (!root) return;
		const resource = currentResource();
		mountFilters(root, resource);
		alignSummary(root);
		alignDisplayLabels(root);
		alignPatientShortcut(root, resource);
	}

	function scheduleAlign() {
		if (scheduled) return;
		scheduled = true;
		requestAnimationFrame(align);
	}

	document.addEventListener("click", (event) => {
		const button = event.target?.closest?.("button[data-vetedge-new-consultation]");
		if (!button) return;
		event.preventDefault();
		event.stopPropagation();
		event.stopImmediatePropagation?.();
		const patient = String(button.dataset.patient || "").trim();
		const suffix = patient ? `&patient=${encodeURIComponent(patient)}` : "";
		window.location.assign(`/desk/vetedge-clinical-workspace?new=1${suffix}`);
	}, true);

	installCallBridge();
	const observer = new MutationObserver((records) => {
		if (records.some((record) => record.type === "childList" && (record.addedNodes.length || record.removedNodes.length))) scheduleAlign();
	});
	observer.observe(document.body, { childList: true, subtree: true });
	window.addEventListener("popstate", scheduleAlign);
	window.setTimeout(scheduleAlign, 0);
})();
