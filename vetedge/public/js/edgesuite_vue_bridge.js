// VetEdge product bundles must use the Vue instance that EdgeSuite UI mounted.
// Loading a second Vue runtime breaks resolveComponent() because its render context differs.
function getVue() {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	const vue = runtime?.Vue || window.Vue;
	if (!vue) throw new Error('EdgeSuite UI Vue runtime is unavailable.');
	return vue;
}

export const createApp = (...args) => getVue().createApp(...args);
export const defineComponent = (...args) => getVue().defineComponent(...args);
export const h = (...args) => getVue().h(...args);
export const ref = (...args) => getVue().ref(...args);
export const reactive = (...args) => getVue().reactive(...args);
export const computed = (...args) => getVue().computed(...args);
export const watch = (...args) => getVue().watch(...args);
export const nextTick = (...args) => getVue().nextTick(...args);
export const onMounted = (...args) => getVue().onMounted(...args);
export const onBeforeUnmount = (...args) => getVue().onBeforeUnmount(...args);

export const createElementVNode = (...args) => getVue().createElementVNode(...args);
export const createVNode = (...args) => getVue().createVNode(...args);
export const createBlock = (...args) => getVue().createBlock(...args);
export const createCommentVNode = (...args) => getVue().createCommentVNode(...args);
export const createElementBlock = (...args) => getVue().createElementBlock(...args);
export const openBlock = (...args) => getVue().openBlock(...args);
export const resolveComponent = (...args) => getVue().resolveComponent(...args);
export const withCtx = (...args) => getVue().withCtx(...args);
export const withDirectives = (...args) => getVue().withDirectives(...args);
export const withModifiers = (...args) => getVue().withModifiers(...args);
export const normalizeClass = (...args) => getVue().normalizeClass(...args);
export const pushScopeId = (...args) => getVue().pushScopeId(...args);
export const popScopeId = (...args) => getVue().popScopeId(...args);
export const renderList = (...args) => getVue().renderList(...args);
export const toDisplayString = (...args) => getVue().toDisplayString(...args);
export const vModelSelect = (...args) => getVue().vModelSelect(...args);
export const vModelText = (...args) => getVue().vModelText(...args);
export const Fragment = getVue().Fragment;
