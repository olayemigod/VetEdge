import VetEdgePricingMasterWorkspace from './vetedge_pricing_master_workspace/VetEdgePricingMasterWorkspace.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

function installStatusFilterSemantics(component) {
	const methods = component?.methods;
	if (!methods || component.__vetedgePricingStatusFiltersInstalled) return component;

	const originalLoadCurrentRoute = methods.loadCurrentRoute;
	methods.loadCurrentRoute = async function (...args) {
		const result = await originalLoadCurrentRoute.apply(this, args);
		const filters = (this.definition?.filters || []).map((field) => {
			if (field.fieldname !== 'disabled') return field;
			return {
				...field,
				fieldname: 'is_active',
				label: __('Status'),
				source_fieldname: 'disabled',
			};
		});
		this.definition = { ...this.definition, filters };
		return result;
	};

	const originalLoadList = methods.loadList;
	methods.loadList = async function (...args) {
		const hasDisabledAlias = (this.definition?.filters || []).some(
			(field) => field.source_fieldname === 'disabled'
		);
		if (!hasDisabledAlias || !Object.prototype.hasOwnProperty.call(this.filters || {}, 'is_active')) {
			return originalLoadList.apply(this, args);
		}

		const originalFilters = this.filters;
		const translatedFilters = { ...originalFilters };
		const activeValue = translatedFilters.is_active;
		delete translatedFilters.is_active;
		if (activeValue !== '') {
			translatedFilters.disabled = String(activeValue) === '1' ? '0' : '1';
		}
		this.filters = translatedFilters;
		try {
			return await originalLoadList.apply(this, args);
		} finally {
			this.filters = originalFilters;
		}
	};

	component.__vetedgePricingStatusFiltersInstalled = true;
	return component;
}

installStatusFilterSemantics(VetEdgePricingMasterWorkspace);
applyWorkspaceSafety(VetEdgePricingMasterWorkspace);

export function mountVetEdgePricingMasterWorkspace(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	VetEdgePricingMasterWorkspace.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgePricingMasterWorkspace);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	window.VetEdgePricingMasterWorkspace = VetEdgePricingMasterWorkspace;
	window.mountVetEdgePricingMasterWorkspace = mountVetEdgePricingMasterWorkspace;
}

export default VetEdgePricingMasterWorkspace;
