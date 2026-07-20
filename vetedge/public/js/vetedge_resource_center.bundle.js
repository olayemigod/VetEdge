import VetEdgeAppointmentQuickCreate from './vetedge_resource_center/VetEdgeAppointmentQuickCreate.vue';
import VetEdgeResourceCenter from './vetedge_resource_center/VetEdgeResourceCenter.vue';

export function mountVetEdgeResourceCenter(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	if (!runtime.components?.EdgeLinkField || !runtime.components?.EdgeModal) {
		throw new Error('VetEdge Resource Center requires EdgeSuite UI 0.4.0 or newer.');
	}

	const quickHost = document.createElement('div');
	quickHost.className = 'vetedge-appointment-quick-create-host';
	document.body.appendChild(quickHost);

	let resourceView = null;
	const quickApp = runtime.createEdgeApp(VetEdgeAppointmentQuickCreate, {
		onCreated: async () => {
			await resourceView?.loadPage?.();
		},
	});
	const quickView = quickApp.mount(quickHost);
	const originalOpenEditor = VetEdgeResourceCenter.methods?.openEditor;
	const ResourceCenterRoot = {
		...VetEdgeResourceCenter,
		components: { ...runtime.components, ...(VetEdgeResourceCenter.components || {}) },
		methods: {
			...(VetEdgeResourceCenter.methods || {}),
			openEditor(name = null) {
				if (this.resource === 'appointments' && !name) {
					quickView?.open?.();
					return;
				}
				return originalOpenEditor?.call(this, name);
			},
		},
	};

	const app = runtime.createEdgeApp(ResourceCenterRoot);
	resourceView = app.mount(target);
	return {
		unmount() {
			app.unmount();
			quickApp.unmount();
			quickHost.remove();
		},
	};
}

if (typeof window !== 'undefined') {
	window.VetEdgeResourceCenter = VetEdgeResourceCenter;
	window.VetEdgeAppointmentQuickCreate = VetEdgeAppointmentQuickCreate;
	window.mountVetEdgeResourceCenter = mountVetEdgeResourceCenter;
}

export default VetEdgeResourceCenter;
