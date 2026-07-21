import VeterinarySettingsCenter from "./veterinary_settings_center/VeterinarySettingsCenter.vue";

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
