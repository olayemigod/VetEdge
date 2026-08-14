// Compatibility shim retained for stale page loaders and cached assets.
//
// VetEdge has one canonical Billing & Payment renderer: public/js/billing_modal.js.
// That renderer is loaded globally from hooks.py and is shared by Consultation,
// Lab Order, Vaccination, Patient Registration, Grooming, Boarding and
// Hospitalisation. This bundle must never replace window.vetedgeBillingModal.

export function installVetEdgeBillingEdgeSuite() {
	return Boolean(window.vetedgeBillingModal?.open);
}

if (typeof window !== "undefined") {
	window.installVetEdgeBillingEdgeSuite = installVetEdgeBillingEdgeSuite;
}

export default installVetEdgeBillingEdgeSuite;
