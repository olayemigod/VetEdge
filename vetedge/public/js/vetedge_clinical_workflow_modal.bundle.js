export function installVetEdgeClinicalWorkflowModal() {
	return Boolean(window.VetEdgeEdgeModalPresenter?.ready?.());
}

if (typeof window !== "undefined") {
	window.installVetEdgeClinicalWorkflowModal = installVetEdgeClinicalWorkflowModal;
}
