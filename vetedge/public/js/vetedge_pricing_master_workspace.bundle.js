import VetEdgePricingMasterWorkspace from './vetedge_pricing_master_workspace/VetEdgePricingMasterWorkspace.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

function installCanonicalDeskLocation(component, path) {
	const methods = component?.methods;
	if (!methods || component.__vetedgeCanonicalDeskLocationInstalled) return component;
	const writeLocation = (method, params = {}) => {
		const url = new URL(window.location.href);
		url.pathname = path;
		url.search = new URLSearchParams(params).toString();
		window.history?.[method]?.(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
	};
	methods.pushLocation = function (params) { writeLocation('pushState', params); };
	methods.replaceLocation = function (params) { writeLocation('replaceState', params); };
	component.__vetedgeCanonicalDeskLocationInstalled = true;
	return component;
}

function installStatusFilterSemantics(component) {
	const methods = component?.methods;
	if (!methods || component.__vetedgePricingStatusFiltersInstalled) return component;
	const originalLoadCurrentRoute = methods.loadCurrentRoute;
	methods.loadCurrentRoute = async function (...args) {
		const result = await originalLoadCurrentRoute.apply(this, args);
		const filters = (this.definition?.filters || []).map((field) => field.fieldname !== 'disabled' ? field : { ...field, fieldname: 'is_active', label: __('Status'), source_fieldname: 'disabled' });
		this.definition = { ...this.definition, filters };
		return result;
	};
	const originalLoadList = methods.loadList;
	methods.loadList = async function (...args) {
		const hasAlias = (this.definition?.filters || []).some((field) => field.source_fieldname === 'disabled');
		if (!hasAlias || !Object.prototype.hasOwnProperty.call(this.filters || {}, 'is_active')) return originalLoadList.apply(this, args);
		const originalFilters = this.filters;
		const translated = { ...originalFilters };
		const activeValue = translated.is_active;
		delete translated.is_active;
		if (activeValue !== '') translated.disabled = String(activeValue) === '1' ? '0' : '1';
		this.filters = translated;
		try { return await originalLoadList.apply(this, args); }
		finally { this.filters = originalFilters; }
	};
	component.__vetedgePricingStatusFiltersInstalled = true;
	return component;
}

installCanonicalDeskLocation(VetEdgePricingMasterWorkspace, '/desk/vetedge-pricing-master-workspace');
installStatusFilterSemantics(VetEdgePricingMasterWorkspace);
applyWorkspaceSafety(VetEdgePricingMasterWorkspace);

export function mountVetEdgePricingMasterWorkspace(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	VetEdgePricingMasterWorkspace.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgePricingMasterWorkspace);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgePricingMasterWorkspace = VetEdgePricingMasterWorkspace;
	window.mountVetEdgePricingMasterWorkspace = mountVetEdgePricingMasterWorkspace;
}

export default VetEdgePricingMasterWorkspace;
