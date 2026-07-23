import { h } from 'vue';

import VetEdgeClinicalWorkspace from './vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

const originalData = VetEdgeClinicalWorkspace.data;
if (typeof originalData === 'function') {
	VetEdgeClinicalWorkspace.data = function clinicalWorkspaceDataWithTableCompatibility() {
		const state = originalData.call(this) || {};
		state.listColumns = (state.listColumns || []).map((column) => ({
			...column,
			fieldname: column.fieldname || column.key,
			status: column.status === true || column.type === 'status',
		}));
		return state;
	};
}

const CLINICAL_ICON_ALIASES = Object.freeze({
	'file-pen-line': 'clipboard',
	'credit-card': 'wallet',
	'clipboard-check': 'clipboard',
	'circle-check': 'check',
});

const VetEdgeClinicalStatCard = {
	name: 'VetEdgeClinicalStatCard',
	inheritAttrs: false,
	props: {
		label: { type: String, default: '' },
		value: { type: [String, Number], default: '—' },
		helper: { type: String, default: '' },
		tone: { type: String, default: 'neutral' },
		icon: { type: String, default: '' },
		tooltip: { type: String, default: '' },
	},
	setup(props, { attrs, slots }) {
		return () => {
			const runtime = window.EdgeSuiteUI;
			const BaseStatCard = runtime?.components?.EdgeStatCard;
			const EdgeIcon = runtime?.components?.EdgeIcon;
			if (!BaseStatCard) return null;

			const iconName = CLINICAL_ICON_ALIASES[props.icon] || props.icon;
			const iconSlot = slots.icon || (
				iconName && EdgeIcon
					? () => h(EdgeIcon, { name: iconName, size: 'lg', label: `${props.label} icon` })
					: undefined
			);

			return h(
				BaseStatCard,
				{
					...attrs,
					label: props.label,
					value: props.value,
					helper: props.helper,
					tone: props.tone,
					icon: props.icon,
					tooltip: props.tooltip,
				},
				iconSlot ? { ...slots, icon: iconSlot } : slots,
			);
		};
	},
};

function installClinicalRuntimeComponents() {
	const runtime = window.EdgeSuiteUI;
	if (!runtime?.components) return false;
	VetEdgeClinicalWorkspace.components = {
		...runtime.components,
		EdgeStatCard: VetEdgeClinicalStatCard,
	};
	return true;
}

const originalTreatmentRowLocked = VetEdgeClinicalWorkspace.methods?.treatmentRowLocked;
VetEdgeClinicalWorkspace.methods.treatmentRowLocked = function treatmentRowLockedWithSourceProtection(row) {
	const sourceGenerated = Boolean(
		row?.source_document
		|| row?.source_detail_name
		|| ['Consultation', 'Lab Order', 'Vaccination'].includes(row?.source_type)
	);
	return sourceGenerated || originalTreatmentRowLocked?.call(this, row) === true;
};

const originalSaveVitals = VetEdgeClinicalWorkspace.methods?.saveVitals;
if (typeof originalSaveVitals === 'function') {
	VetEdgeClinicalWorkspace.methods.saveVitals = async function saveVitalsWithReliableClose() {
		const previousVitals = this.detail?.latest_vitals?.name || '';
		await originalSaveVitals.call(this);
		const currentVitals = this.detail?.latest_vitals?.name || '';
		if (!this.busy && currentVitals && currentVitals !== previousVitals) {
			this.vitalsDialog = { open: false, values: {} };
		}
	};
}

applyWorkspaceSafety(VetEdgeClinicalWorkspace, { guardNavigation: true });
installClinicalRuntimeComponents();

export function mountVetEdgeClinicalWorkspace(target) {
	const runtime = window.EdgeSuiteUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	installClinicalRuntimeComponents();
	const app = runtime.createEdgeApp(VetEdgeClinicalWorkspace);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	window.VetEdgeClinicalWorkspace = VetEdgeClinicalWorkspace;
	window.mountVetEdgeClinicalWorkspace = mountVetEdgeClinicalWorkspace;
}

export default VetEdgeClinicalWorkspace;
