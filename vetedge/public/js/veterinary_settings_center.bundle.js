import VeterinarySettingsCenter from "./veterinary_settings_center/VeterinarySettingsCenter.vue";

function normalizeBooleanMethod(name) {
	const methods = VeterinarySettingsCenter.methods || {};
	const original = methods[name];
	if (typeof original !== "function" || original.__vetedgeBooleanNormalized) return;
	const normalized = function (...args) {
		return Boolean(original.apply(this, args));
	};
	normalized.__vetedgeBooleanNormalized = true;
	methods[name] = normalized;
	VeterinarySettingsCenter.methods = methods;
}

for (const method of ["isReadOnly", "isRequired", "isChildReadOnly", "isChildRequired"]) {
	normalizeBooleanMethod(method);
}

export function mountVeterinarySettingsCenter(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime?.createEdgeApp) throw new Error("Standalone EdgeSuite UI runtime is unavailable.");
	VeterinarySettingsCenter.components = runtime.components;
	const app = runtime.createEdgeApp(VeterinarySettingsCenter);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== "undefined") {
	window.VeterinarySettingsCenter = VeterinarySettingsCenter;
	window.mountVeterinarySettingsCenter = mountVeterinarySettingsCenter;
}

export default VeterinarySettingsCenter;
