frappe.pages['vetedge-billing-sessions'].on_page_load = function(wrapper) {
	wrapper.page = frappe.ui.make_app_page({ parent: wrapper, title: __('Billing Sessions'), single_column: true });
};

frappe.pages['vetedge-billing-sessions'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	const sessionName = new URLSearchParams(window.location.search || '').get('name') || '';
	if (wrapper.vue_app?.view && wrapper.billing_session_name === sessionName) {
		wrapper.vue_app.view.refresh?.();
		return;
	}

	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	wrapper.billing_session_name = sessionName;
	$(page.body).empty();
	const loadingText = sessionName ? __('Loading Billing Session...') : __('Loading Billing Sessions...');
	const loading = $('<div class="p-6 text-center text-muted"></div>').text(loadingText).appendTo(page.body);
	const showFailure = (message) => {
		loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>').text(message || __('Billing Sessions failed to load.')).appendTo(page.body);
	};

	frappe.require('edgeui.bundle.js', () => {
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ['EdgeAppShell', 'EdgePageLayout', 'EdgePageHeader', 'EdgeFilterBar', 'EdgeStatCard', 'EdgeDataTable', 'EdgeLinkField', 'EdgeDropdown', 'EdgeInput', 'EdgeLoadingState', 'EdgeErrorState'];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(missing.length
				? __('Billing Sessions requires EdgeSuite UI 0.6.3 or newer. Missing: {0}', [missing.join(', ')])
				: __('The standalone EdgeSuite UI runtime is unavailable.'));
			return;
		}

		const mountWorkspace = () => {
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			if (!professional?.installed) {
				showFailure(professional?.message || __('The VetEdge professional shell is unavailable.'));
				return;
			}
			frappe.require('vetedge_billing_center.bundle.js', () => {
				const mount = sessionName ? window.mountVetEdgeBillingSessionDetail : window.mountVetEdgeBillingCenter;
				if (!mount) {
					showFailure(sessionName ? __('Billing Session detail bundle is unavailable.') : __('Billing Sessions bundle is unavailable.'));
					return;
				}
				try {
					loading.remove();
					const rootClass = sessionName ? 'vetedge-billing-session-detail-root' : 'vetedge-billing-sessions-root';
					const root = $(`<div class="${rootClass}" data-edge-product="vetedge"></div>`).appendTo(page.body);
					wrapper.vue_app = mount(root[0]);
				} catch (error) {
					console.error('Error mounting Billing Sessions:', error);
					showFailure(__('Error mounting Billing Sessions: {0}', [error.message || String(error)]));
				}
			});
		};

		if (window.VetEdgeProfessionalUI?.install) mountWorkspace();
		else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountWorkspace);
	});
};
