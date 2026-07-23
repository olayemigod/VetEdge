function emptyConfirmation() {
	return {
		open: false,
		title: "",
		subtitle: "",
		message: "",
		confirmLabel: typeof __ === "function" ? __("Continue") : "Continue",
		danger: false,
		busy: false,
		handler: null,
	};
}

function wrapHook(original, enhancement) {
	return function (...args) {
		if (typeof original === "function") original.apply(this, args);
		enhancement.apply(this, args);
	};
}

function wrapGuardedMethod(methods, methodName) {
	const original = methods[methodName];
	if (typeof original !== "function" || original.__vetedgeUnsavedGuardWrapped) return;

	const wrapped = function (...args) {
		if (!this.dirty || typeof this.confirmDiscard !== "function") {
			return original.apply(this, args);
		}
		return this.confirmDiscard(() => original.apply(this, args));
	};
	wrapped.__vetedgeUnsavedGuardWrapped = true;
	methods[methodName] = wrapped;
}

export function applyWorkspaceSafety(component, { guardNavigation = false } = {}) {
	if (!component || component.__vetedgeWorkspaceSafetyApplied) return component;
	component.__vetedgeWorkspaceSafetyApplied = true;
	component.methods = component.methods || {};
	const methods = component.methods;

	methods.handleBeforeUnload = methods.handleBeforeUnload || function (event) {
		if (!this.dirty) return;
		event.preventDefault();
		event.returnValue = "";
	};

	methods.confirmDiscard = methods.confirmDiscard || function (action) {
		if (!this.dirty) return action();
		this.openConfirmation({
			title: typeof __ === "function" ? __("Discard unsaved changes?") : "Discard unsaved changes?",
			message:
				typeof __ === "function"
					? __("You have unsaved changes. Continue without saving them?")
					: "You have unsaved changes. Continue without saving them?",
			confirmLabel: typeof __ === "function" ? __("Discard Changes") : "Discard Changes",
			danger: true,
			handler: async () => {
				this.dirty = false;
				return action();
			},
		});
	};

	methods.closeConfirmation = function (force = false) {
		if (this.confirmation?.busy && !force) return;
		this.confirmation = emptyConfirmation();
	};

	methods.confirmPendingAction = async function () {
		const handler = this.confirmation?.handler;
		if (typeof handler !== "function" || this.confirmation?.busy) return;
		this.confirmation.busy = true;
		try {
			await handler();
			this.closeConfirmation(true);
		} catch (error) {
			this.confirmation.busy = false;
			window.frappe?.msgprint?.({
				title: typeof __ === "function" ? __("Action failed") : "Action failed",
				message: error?.message || error?._server_messages || String(error),
				indicator: "red",
			});
		}
	};

	if (guardNavigation) {
		for (const methodName of ["backToList", "openRoute", "reloadCurrentView"]) {
			wrapGuardedMethod(methods, methodName);
		}
	}

	component.mounted = wrapHook(component.mounted, function () {
		window.addEventListener("beforeunload", this.handleBeforeUnload);
	});
	component.beforeUnmount = wrapHook(component.beforeUnmount, function () {
		window.removeEventListener("beforeunload", this.handleBeforeUnload);
	});

	return component;
}

export default applyWorkspaceSafety;
