export function installWorkspaceRuntime(component) {
	const methods = component?.methods;
	if (!methods || component.__vetedgeWorkspaceRuntimeInstalled) return component;

	methods.closeConfirmation = function () {
		this.confirmation = {
			open: false,
			title: "",
			subtitle: "",
			message: "",
			confirmLabel: __("Continue"),
			danger: false,
			busy: false,
			handler: null,
		};
	};

	const originalBackToList = methods.backToList;
	methods.backToList = function () {
		if (this.definition?.is_single) {
			window.location.assign("/app/vetedge");
			return;
		}
		return originalBackToList.call(this);
	};

	component.__vetedgeWorkspaceRuntimeInstalled = true;
	return component;
}
