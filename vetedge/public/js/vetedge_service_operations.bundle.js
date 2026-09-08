import VetEdgeServiceOperations from './vetedge_service_operations/VetEdgeServiceOperations.vue';

const GROOMING_APPOINTMENTS_TAB = Object.freeze({
	value: 'grooming-appointments',
	label: 'Grooming Appointments',
	description: 'Scheduled grooming work and session hand-off',
});

function requestedServiceResource() {
	const params = new URLSearchParams(window.location.search || '');
	return String(params.get('resource') || '').trim();
}

function buildServiceOperationsRoot(runtime) {
	const originalData = VetEdgeServiceOperations.data;
	const originalComputed = VetEdgeServiceOperations.computed || {};
	const originalMethods = VetEdgeServiceOperations.methods || {};
	const originalOpenCreate = originalMethods.openCreate;

	return {
		...VetEdgeServiceOperations,
		components: { ...runtime.components, ...(VetEdgeServiceOperations.components || {}) },
		data() {
			const state = typeof originalData === 'function' ? originalData.call(this) : {};
			const tabs = Array.isArray(state.tabs) ? [...state.tabs] : [];
			if (!tabs.some((tab) => tab.value === GROOMING_APPOINTMENTS_TAB.value)) {
				tabs.push({ ...GROOMING_APPOINTMENTS_TAB });
			}
			state.tabs = tabs;
			if (requestedServiceResource() === GROOMING_APPOINTMENTS_TAB.value) {
				state.resource = GROOMING_APPOINTMENTS_TAB.value;
			}
			return state;
		},
		computed: {
			...originalComputed,
			activeTab() {
				return (this.tabs || []).find((tab) => tab.value === this.resource) || (this.tabs || [])[0] || {};
			},
			createLabel() {
				if (this.resource === 'grooming-appointments' || this.resource === 'grooming-sessions') return 'New Grooming Appointment';
				if (['boarding-bookings', 'boarding-stays'].includes(this.resource)) return 'New Boarding Booking';
				return 'New Record';
			},
		},
		methods: {
			...originalMethods,
			openCreate() {
				if (this.resource === 'grooming-appointments' || this.resource === 'grooming-sessions') {
					this.openRoute('/desk/vetedge-resource-center?resource=appointments&new=1&appointment_type=Grooming');
					return;
				}
				return originalOpenCreate?.call(this);
			},
		},
	};
}

export function mountVetEdgeServiceOperations(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	const Root = buildServiceOperationsRoot(runtime);
	const app = runtime.createEdgeApp(Root);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgeServiceOperations = VetEdgeServiceOperations;
	window.mountVetEdgeServiceOperations = mountVetEdgeServiceOperations;
}

export default VetEdgeServiceOperations;
