const VETEDGE_HOME_REFRESH_MAX_AGE_MS = 30000;

async function refreshMountedVetEdgeHome(wrapper) {
	const view = wrapper.vue_app?.view;
	if (!view) return false;
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
