const VETEDGE_HOME_REFRESH_MAX_AGE_MS = 30000;
const VETEDGE_HOME_DRILLDOWN_METHOD = "vetedge.services.home_postqa.get_metric_drilldown";
const VETEDGE_HOME_DRILLDOWN_PAGE_LENGTH = 25;

function exactVetEdgeHomeRecordRoute(doctype, name) {
	const record = encodeURIComponent(String(name || "").trim());
	if (!record) return "";

	switch (String(doctype || "").trim()) {
		case "Veterinary Consultation":
			return `/desk/vetedge-clinical-workspace?consultation=${record}`;
		case "Veterinary Appointment":
			return `/desk/vetedge-resource-center?resource=appointments&name=${record}`;
		case "Veterinary Missed Appointment":
			return `/desk/vetedge-front-desk-action-center?tab=missed&name=${record}`;
		case "Veterinary Lab Order":
			return `/desk/vetedge-resource-center?resource=lab-orders&name=${record}`;
		case "Sales Invoice":
			return `/desk/sales-invoice/${record}`;
		default:
			return "";
	}
}

function installVetEdgeHomeFinalQaFixes(view) {
	if (!view || view.__vetedgeHomeFinalQaFixesInstalled) return false;
	view.__vetedgeHomeFinalQaFixesInstalled = true;

	view.loadDrilldown = async function loadFinalQaDrilldown(start = 0) {
		if (!this.drilldown?.metricKey) return;
		this.drilldown.loading = true;
		this.drilldown.error = "";
		try {
			const response = await frappe.call(VETEDGE_HOME_DRILLDOWN_METHOD, {
				metric_key: this.drilldown.metricKey,
				operational_date: this.selectedDate || undefined,
				branch: this.selectedBranch || undefined,
				limit_start: start,
				limit_page_length: this.drilldown.pageLength || VETEDGE_HOME_DRILLDOWN_PAGE_LENGTH,
			});
			const result = response?.message || {};
			this.drilldown = {
				...this.drilldown,
				open: true,
				loading: false,
				metric: result.metric || {},
				doctype: result.doctype || "",
				total: Number(result.total || 0),
				rows: result.rows || [],
				columns: result.columns || [],
				start: Number(result.limit_start || 0),
				pageLength: Number(result.limit_page_length || VETEDGE_HOME_DRILLDOWN_PAGE_LENGTH),
				context: result.context || {},
			};
			this.reconcileMetricCount?.(this.drilldown.metricKey, this.drilldown.total);
		} catch (error) {
			this.drilldown.loading = false;
			this.drilldown.error = error?.message || __("The exact card records could not be loaded.");
		}
	};

	view.openDrilldownRecord = function openFinalQaDrilldownRecord(row) {
		if (!row?.name || !this.drilldown?.doctype) return;
		const route = exactVetEdgeHomeRecordRoute(this.drilldown.doctype, row.name);
		if (route) {
			// Exact EdgeSuite deep links rely on their query string. The shared
			// navigation adapter intentionally normalises menu routes through
			// frappe.set_route(), which does not preserve these record parameters.
			// A same-origin Desk navigation keeps the canonical query intact so the
			// downstream workspace opens the selected record rather than its list.
			window.location.assign(route);
			return;
		}
		if (typeof frappe.set_route === "function") {
			frappe.set_route("Form", this.drilldown.doctype, row.name);
			return;
		}
		const slug = this.drilldown.doctype.toLowerCase().replace(/\s+/g, "-");
		window.location.assign(`/desk/${slug}/${encodeURIComponent(row.name)}`);
	};

	return true;
}

async function refreshMountedVetEdgeHome(wrapper) {
	const view = wrapper.vue_app?.view;
	if (!view) return false;
	installVetEdgeHomeFinalQaFixes(view);
	const stale = Date.now() - Number(wrapper.vetedge_home_last_refresh_at || 0) >= VETEDGE_HOME_REFRESH_MAX_AGE_MS;
	if (stale) {
		await view.loadHome?.();
		wrapper.vetedge_home_last_refresh_at = Date.now();
	}
	return true;
}

frappe.pages["vetedge"].on_page_load = function (wrapper) {
	wrapper.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Veterinary Home"),
		single_column: true,
	});
};

frappe.pages["vetedge"].on_page_show = function (wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app?.view) {
		Promise.resolve(refreshMountedVetEdgeHome(wrapper)).catch((error) => {
			console.error("Error refreshing Veterinary Home:", error);
		});
		return;
	}

	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(__("Loading Veterinary Home..."))
		.appendTo(page.body);
	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __("Veterinary Home failed to load."))
			.appendTo(page.body);
	};

	frappe.require("edgeui.bundle.js", () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = [
			"EdgeAppShell",
			"EdgePageLayout",
			"EdgePageHeader",
			"EdgeDashboardLayout",
			"EdgeStatCard",
			"EdgeDataTable",
			"EdgeLoadingState",
			"EdgeErrorState",
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(
				missing.length
					? __("Veterinary Home requires the current EdgeSuite UI runtime. Missing: {0}", [missing.join(", ")])
					: __("The standalone EdgeSuite UI runtime is unavailable.")
			);
			return;
		}

		const mountHome = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			if (!professional?.installed) {
				showFailure(professional?.message || __("The VetEdge professional shell is unavailable."));
				return;
			}
			frappe.require("vetedge_home.bundle.js", () => {
				if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeHome) return;
				try {
					$loading.remove();
					const root = $('<div class="vetedge-home-root" data-edge-product="vetedge"></div>').appendTo(page.body);
					wrapper.vue_app = window.mountVetEdgeHome(root[0]);
					installVetEdgeHomeFinalQaFixes(wrapper.vue_app?.view);
					wrapper.vetedge_home_last_refresh_at = Date.now();
				} catch (error) {
					console.error("Error mounting Veterinary Home:", error);
					showFailure(__("Error mounting Veterinary Home: {0}", [error.message || String(error)]));
				}
			});
		};

		if (window.VetEdgeProfessionalUI?.install) mountHome();
		else frappe.require("/assets/vetedge/js/vetedge_professional_ui.js", mountHome);
	});
};