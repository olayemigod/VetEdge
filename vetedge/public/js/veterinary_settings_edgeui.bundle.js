import VeterinarySettingsHeader from './veterinary_settings_edgeui/VeterinarySettingsHeader.vue';

export function mountVeterinarySettingsHeader(target, props = {}) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	const required = ['EdgePageHeader', 'EdgeStatusBadge'];
	const missing = required.filter((name) => !runtime.components?.[name]);
	if (missing.length) {
		throw new Error(`Missing EdgeSuite UI components: ${missing.join(', ')}.`);
	}
	const root = {
		...VeterinarySettingsHeader,
		props: VeterinarySettingsHeader.props,
		components: { ...runtime.components, ...(VeterinarySettingsHeader.components || {}) },
	};
	const app = runtime.createEdgeApp(root, props);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VeterinarySettingsHeader = VeterinarySettingsHeader;
	window.mountVeterinarySettingsHeader = mountVeterinarySettingsHeader;
}

export default VeterinarySettingsHeader;
