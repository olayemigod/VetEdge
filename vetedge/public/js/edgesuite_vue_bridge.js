// VetEdge product bundles must use the Vue instance EdgeSuite UI has already loaded.
// A second runtime breaks resolveComponent() because its render context differs.
const REQUIRED_SFC_HELPERS = [
	'vModelText',
	'vModelCheckbox',
	'vModelRadio',
	'vModelSelect',
	'withDirectives',
	'resolveComponent',
	'resolveDirective',
	'createVNode',
	'createBlock',
	'openBlock',
];

function helperAvailability(candidate) {
	return Object.fromEntries(
		REQUIRED_SFC_HELPERS.map((helper) => [helper, typeof candidate?.[helper] === 'function'])
	);
}

function getVue() {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	const candidates = [runtime?.Vue, window.Vue].filter(Boolean);
	const diagnostics = candidates.map((candidate) => helperAvailability(candidate));
	console.info('[VetEdge Vue bridge] evaluating shared Vue runtime', diagnostics);

	const vue = candidates.find((candidate) =>
		REQUIRED_SFC_HELPERS.every((helper) => typeof candidate[helper] === 'function')
	);
	if (!vue) {
		const error = new Error('EdgeSuite UI Vue runtime is missing required SFC helpers.');
		console.error('[VetEdge Vue bridge] first bundle evaluation exception', {
			diagnostics,
			stack: error.stack
		});
		throw error;
	}
	return vue;
}

window.setTimeout(() => {
	console.info('[VetEdge Vue bridge] product globals after bundle evaluation', {
		executiveDashboard: window.VetedgeExecutiveDashboard,
		stockExpiryMonitor: window.VetedgeStockExpiryMonitor,
		executiveDashboardApp: window.VetedgeExecutiveDashboardApp,
		stockExpiryMonitorApp: window.VetedgeStockExpiryMonitorApp
	});
}, 0);

// Export the verified EdgeSuite runtime itself for product code that needs the full API.
const Vue = getVue();
export { Vue };
export default Vue;

// Static named exports are required for Vue SFC compiler output. Each is a direct
// reference to the verified shared runtime, not a separately bundled Vue copy.
export const createApp = Vue.createApp;
export const defineComponent = Vue.defineComponent;
export const h = Vue.h;
export const ref = Vue.ref;
export const reactive = Vue.reactive;
export const computed = Vue.computed;
export const watch = Vue.watch;
export const nextTick = Vue.nextTick;
export const onMounted = Vue.onMounted;
export const onUnmounted = Vue.onUnmounted;
export const onBeforeUnmount = Vue.onBeforeUnmount;

export const createElementVNode = Vue.createElementVNode;
export const createVNode = Vue.createVNode;
export const createBlock = Vue.createBlock;
export const createCommentVNode = Vue.createCommentVNode;
export const createElementBlock = Vue.createElementBlock;
export const openBlock = Vue.openBlock;
export const resolveComponent = Vue.resolveComponent;
export const resolveDirective = Vue.resolveDirective;
export const withCtx = Vue.withCtx;
export const withDirectives = Vue.withDirectives;
export const withModifiers = Vue.withModifiers;
export const normalizeClass = Vue.normalizeClass;
export const pushScopeId = Vue.pushScopeId;
export const popScopeId = Vue.popScopeId;
export const renderList = Vue.renderList;
export const toDisplayString = Vue.toDisplayString;
export const vModelText = Vue.vModelText;
export const vModelCheckbox = Vue.vModelCheckbox;
export const vModelRadio = Vue.vModelRadio;
export const vModelSelect = Vue.vModelSelect;
export const Fragment = Vue.Fragment;
