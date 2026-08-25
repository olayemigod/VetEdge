const VETEDGE_SETTINGS_REFRESH_MAX_AGE_MS = 15000;

function syncVeterinarySettingsWriteAccess(wrapper) {
	const view = wrapper.__veterinarySettingsApp?.view;
	if (!view || wrapper.settings_access_checked) return Promise.resolve(Boolean(view?.canWrite));
	if (view.canWrite) {
		wrapper.settings_access_checked = true;
		return Promise.resolve(true);
	}

	return frappe.call("vetedge.services.settings_page.get_veterinary_settings_access")
		.then((response) => {
			const payload = response.message || {};
			view.canWrite = payload.can_write === true || Number(payload.can_write || 0) === 1;
			view.writeRoles = payload.write_roles || view.writeRoles || [];
			wrapper.settings_access_checked = true;
			return view.canWrite;
		})
		.catch((error) => {
			console.error("Error reconciling Veterinary Settings write access:", error);
			return false;
		});
}

function reconcileVeterinarySettingsWriteAccess(wrapper) {
	const view = wrapper.__veterinarySettingsApp?.view;
	if (!view || wrapper.settings_access_checked) return;
	if (!view.loading) {
		void syncVeterinarySettingsWriteAccess(wrapper);
		return;
	}

	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (typeof runtime?.Vue?.watch !== "function") return;
	const stop = runtime.Vue.watch(
		() => Boolean(view.loading),
		(loading) => {
			if (loading) return;
			stop();
			void syncVeterinarySettingsWriteAccess(wrapper);
		},
	);
}

function showVeterinarySettingsMountFailure(root, message) {
	root.innerHTML = `<div class="alert alert-danger">${message}</div>`;
}

function mountVeterinarySettings(wrapper) {
	if (wrapper.__veterinarySettingsApp?.view || wrapper.settings_mounting) return;

	wrapper.settings_mounting = true;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;
	const page = wrapper.page;
	const root = document.createElement("div");
	root.className = "veterinary-settings-center-root";
	root.dataset.edgeProduct = "veterinary";
	page.body.empty().append(root);

	const finishMountAttempt = () => {
		if (wrapper.current_visit_id === visitId) wrapper.settings_mounting = false;
	};

	frappe.require("edgeui.bundle.js", () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = [
			"EdgeAppShell",
			"EdgePageLayout",
			"EdgePageHeader",
			"EdgeStatusBadge",
			"EdgeLinkField",
			"EdgeDropdown",
			"EdgeInput",
			"EdgeTextarea",
			"EdgeCheckbox",
			"EdgeLoadingState",
			"EdgeErrorState",
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showVeterinarySettingsMountFailure(
				root,
				__("EdgeSuite UI 0.6.3 or newer is required for Veterinary Settings. Missing: {0}", [missing.join(", ")]),
			);
			finishMountAttempt();
			return;
		}

		const mountWithProfessionalShell = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			if (!professional?.installed) {
				showVeterinarySettingsMountFailure(
					root,
					professional?.message || __("The Veterinary professional shell is unavailable."),
				);
				finishMountAttempt();
				return;
			}

			window.VetEdgeUIBridge?.install?.();
			frappe.require("veterinary_settings_center.bundle.js", () => {
				if (wrapper.current_visit_id !== visitId || !window.mountVeterinarySettingsCenter) return;
				wrapper.__veterinarySettingsApp?.unmount?.();
				wrapper.settings_access_checked = false;
				wrapper.__veterinarySettingsApp = window.mountVeterinarySettingsCenter(root);
				reconcileVeterinarySettingsWriteAccess(wrapper);
				wrapper.settings_last_refresh_at = Date.now();
				finishMountAttempt();
			});
		};

		if (window.VetEdgeProfessionalUI?.install) {
			mountWithProfessionalShell();
		} else {
			frappe.require("/assets/vetedge/js/vetedge_professional_ui.js", mountWithProfessionalShell);
		}
	});
}

function refreshMountedVeterinarySettings(wrapper) {
	const view = wrapper.__veterinarySettingsApp?.view;
	if (!view) return;
	reconcileVeterinarySettingsWriteAccess(wrapper);
	if (view.dirty) return;
	const stale = Date.now() - Number(wrapper.settings_last_refresh_at || 0) >= VETEDGE_SETTINGS_REFRESH_MAX_AGE_MS;
	if (!stale) return;
	Promise.resolve(view.load?.())
		.then(() => {
			wrapper.settings_access_checked = false;
			reconcileVeterinarySettingsWriteAccess(wrapper);
			wrapper.settings_last_refresh_at = Date.now();
		})
		.catch((error) => console.error("Error refreshing Veterinary Settings:", error));
}

frappe.pages["veterinary-settings-center"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Veterinary Settings"),
		single_column: true,
	});
	page.main.addClass("veterinary-settings-center-page");
	wrapper.page = page;
};

frappe.pages["veterinary-settings-center"].on_page_show = function (wrapper) {
	window.VetEdgeUIBridge?.install?.();
	if (wrapper.__veterinarySettingsApp?.view) {
		refreshMountedVeterinarySettings(wrapper);
		return;
	}
	mountVeterinarySettings(wrapper);
};

frappe.pages["veterinary-settings-center"].on_page_unload = function (wrapper) {
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	wrapper.__veterinarySettingsApp?.unmount?.();
	wrapper.__veterinarySettingsApp = null;
	wrapper.settings_access_checked = false;
	wrapper.settings_mounting = false;
};