export function installVetEdgeBillingEdgeSuite() {
	return Boolean(window.VetEdgeEdgeModalPresenter?.ready?.());
}

if (typeof window !== "undefined") {
	window.installVetEdgeBillingEdgeSuite = installVetEdgeBillingEdgeSuite;
}
