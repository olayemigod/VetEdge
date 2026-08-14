(function () {
	"use strict";

	const TITLE = "Reverse / Resolve Completed Consultation";
	const TERMINAL = new Set(["Completed", "Rejected"]);
	let installed = false;

	function appendGuidance(message, guidance) {
		const base = String(message || "").trim();
		if (base.includes(guidance)) return base;
		return [base, guidance].filter(Boolean).join("\n\n");
	}

	function terminalStatus(spec = {}) {
		for (const badge of spec.badges || []) {
			const status = String(badge?.status || "").trim();
			if (TERMINAL.has(status)) return status;
		}
		return "";
	}

	function emptyResolutionSelector(spec = {}) {
		return (spec.fields || []).find((field) =>
			field?.fieldname === "resolution_action" &&
			Array.isArray(field.options) &&
			field.options.length === 0
		);
	}

	function normalize(spec = {}) {
		if (String(spec.title || "") !== TITLE) return spec;

		const status = terminalStatus(spec);
		if (status === "Completed") {
			return {
				...spec,
				fields: [],
				actions: [],
				message: appendGuidance(
					spec.message,
					__("This reversal resolution is completed and is read-only. No further Save or Record action is required."),
				),
			};
		}
		if (status === "Rejected") {
			return {
				...spec,
				fields: [],
				actions: [],
				message: appendGuidance(
					spec.message,
					__("This reversal resolution was rejected and is read-only. Resolve the underlying blocker through the permitted workflow before recording a new decision."),
				),
			};
		}

		if (emptyResolutionSelector(spec)) {
			return {
				...spec,
				fields: [],
				actions: [],
				message: appendGuidance(
					spec.message,
					__("No self-service reversal action is available for this state. Resolve the submitted invoice or accounting blocker through Accounts/Admin, then reopen this dialog to continue."),
				),
			};
		}
		return spec;
	}

	function install() {
		if (installed) return true;
		const presenter = window.VetEdgeEdgeModalPresenter;
		if (!presenter?.open) return false;

		const originalOpen = presenter.open.bind(presenter);
		presenter.open = function guardedOpen(spec = {}) {
			const modal = originalOpen(normalize(spec));
			if (!modal?.update) return modal;
			const originalUpdate = modal.update.bind(modal);
			modal.update = (patch = {}) => originalUpdate(normalize(patch));
			return modal;
		};

		installed = true;
		window.VetEdgeClinicalResolutionStateGuard = { installed: true, normalize };
		return true;
	}

	window.installVetEdgeClinicalResolutionStateGuard = install;
})();
