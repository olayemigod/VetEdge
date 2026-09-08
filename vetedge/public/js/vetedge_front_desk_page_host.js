(function () {
	"use strict";
	if (typeof window === "undefined") return;

	const REFRESH_MAX_AGE_MS = 15000;
	const VALID_TABS = new Set(["queue", "guest", "missed"]);

	function requestedName() {
		return String(new URLSearchParams(window.location.search || "").get("name") || "").trim();
	}

	async function refreshMounted(wrapper, fixedTab) {
		const view = wrapper.vue_app?.view;
		if (!view) return false;
		const name = requestedName();
		const routeKey = `${fixedTab}:${name}`;
		const stale = Date.now() - Number(wrapper.front_desk_last_refresh_at || 0) >= REFRESH_MAX_AGE_MS;
		if (wrapper.front_desk_route_key !== routeKey || stale) await view.refreshAll?.();

		if (name) {
			if (fixedTab === "guest") await view.openGuestDetail?.({ name });
			else if (fixedTab === "missed") await view.openMissedDetail?.({ name });
			else await view.openQueueDetail?.({ name });
		} else if (view.detail?.open) {
			view.closeDetail?.();
		}

		wrapper.front_desk_route_key = routeKey;
		wrapper.front_desk_last_refresh_at = Date.now();
		return true;
	}

	function showFailure(page, loading, message) {
		loading?.remove?.();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __("This Front Desk page failed to load."))
			.appendTo(page.body);
	}

	function mount(wrapper, config) {
		const fixedTab = String(config?.fixedTab || "").trim();
		if (!VALID_TABS.has(fixedTab)) throw new Error(`Invalid Front Desk page mode: ${fixedTab}`);
		const page = wrapper.page;
		wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
		const visitId = wrapper.current_visit_id;

		if (wrapper.vue_app?.view) {
			Promise.resolve(refreshMounted(wrapper, fixedTab)).catch((error) => {
				console.error("Error refreshing Front Desk page:", error);
			});
			return;
		}

		wrapper.vue_app?.unmount?.();
		wrapper.vue_app = null;
		$(page.body).empty();
		const loading = $('<div class="p-6 text-center text-muted"></div>')
			.text(__("Loading {0}...", [config.title || "Front Desk"]))
			.appendTo(page.body);

		frappe.require("edgeui.bundle.js", () => {
			if (wrapper.current_visit_id !== visitId) return;
			const runtime = window.EdgeSuiteUI || window.EdgeUI;
			const required = ["EdgeAppShell", "EdgePageLayout", "EdgePageHeader", "EdgeFilterBar", "EdgeStatCard", "EdgeDataTable", "EdgeStatusBadge", "EdgeLinkField", "EdgeDropdown", "EdgeInput", "EdgeTextarea", "EdgeModal", "EdgeLoadingState", "EdgeErrorState"];
			const missing = required.filter((name) => !runtime?.components?.[name]);
			if (!runtime?.createEdgeApp || missing.length) {
				showFailure(page, loading, missing.length
					? __("This Front Desk page requires EdgeSuite UI 0.6.3 or newer. Missing: {0}", [missing.join(", ")])
					: __("The standalone EdgeSuite UI runtime is unavailable."));
				return;
			}

			const mountWorkspace = () => {
				if (wrapper.current_visit_id !== visitId) return;
				const professional = window.VetEdgeProfessionalUI?.install?.();
				window.VetEdgeUIBridge?.install?.();
				if (!professional?.installed) {
					showFailure(page, loading, professional?.message || __("The VetEdge professional shell is unavailable."));
					return;
				}
				frappe.require("vetedge_front_desk_action_center.bundle.js", () => {
					if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeFrontDeskActionCenter) return;
					try {
						loading.remove();
						const root = $('<div class="vetedge-front-desk-action-center-root" data-edge-product="vetedge"></div>').appendTo(page.body);
						wrapper.vue_app = window.mountVetEdgeFrontDeskActionCenter(root[0], { fixedTab });
						const name = requestedName();
						wrapper.front_desk_route_key = `${fixedTab}:${name}`;
						wrapper.front_desk_last_refresh_at = Date.now();
						if (name) {
							const view = wrapper.vue_app?.view;
							const opener = fixedTab === "guest" ? view?.openGuestDetail : fixedTab === "missed" ? view?.openMissedDetail : view?.openQueueDetail;
							window.setTimeout(() => opener?.call(view, { name }), 0);
						}
					} catch (error) {
						console.error("Error mounting Front Desk page:", error);
						showFailure(page, loading, __("Error mounting {0}: {1}", [config.title || "Front Desk", error.message || String(error)]));
					}
				});
			};

			if (window.VetEdgeProfessionalUI?.install) mountWorkspace();
			else frappe.require("/assets/vetedge/js/vetedge_professional_ui.js", mountWorkspace);
		});
	}

	window.VetEdgeFrontDeskPageHost = Object.freeze({ mount });
})();
