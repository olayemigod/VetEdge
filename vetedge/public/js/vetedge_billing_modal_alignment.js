(function () {
	"use strict";

	if (window.__vetedgeBillingModalAlignmentInstalled) return;
	window.__vetedgeBillingModalAlignmentInstalled = true;

	function panelByTitle(root, title) {
		return [...root.querySelectorAll(".ve-billing-panel")].find((panel) => {
			const heading = panel.querySelector("h4");
			return String(heading?.textContent || "").trim() === title;
		});
	}

	function align(root) {
		if (!root || root.dataset.edgeBillingAligned === "1") return;
		const paymentPanel = panelByTitle(root, __("Payment Summary"));
		const actions = root.querySelector(":scope > .ve-billing-actions");
		if (!paymentPanel || !actions) return;

		root.dataset.edgeBillingAligned = "1";
		root.classList.add("ve-billing-modern-aligned");
		const actionMessage = root.querySelector(":scope > .ve-billing-action-message");
		const inline = document.createElement("div");
		inline.className = "ve-billing-payment-actions";
		if (actionMessage) inline.appendChild(actionMessage);
		inline.appendChild(actions);
		paymentPanel.appendChild(inline);
	}

	function scan() {
		document.querySelectorAll(".ve-billing-edge-modal").forEach(align);
	}

	const style = document.createElement("style");
	style.id = "vetedge-billing-modal-alignment-style";
	style.textContent = `
		.ve-billing-edge-modal {
			--ve-primary: var(--edge-color-brand-600, #0f64ab) !important;
			--ve-bg: var(--edge-color-surface-muted, #f5f8fc) !important;
			--ve-surface: var(--edge-color-surface, #fff) !important;
			--ve-border: var(--edge-color-border, #dce5ef) !important;
			--ve-text: var(--edge-color-ink-950, #122033) !important;
			--ve-muted: var(--edge-color-ink-500, #6b7d90) !important;
			--ve-success: var(--edge-color-success, #138a58) !important;
			--ve-warning: var(--edge-color-warning, #a85f00) !important;
			--ve-danger: var(--edge-color-danger, #c53a3a) !important;
			border-radius: var(--edge-radius-lg, 1rem) !important;
		}
		.ve-billing-modern-aligned .ve-billing-panel,
		.ve-billing-modern-aligned .ve-billing-metric,
		.ve-billing-modern-aligned .ve-billing-empty,
		.ve-billing-modern-aligned .ve-billing-badge-group {
			border-color: var(--edge-color-border, #dce5ef) !important;
		}
		.ve-billing-payment-actions {
			border-top: 1px solid var(--edge-color-border, #dce5ef);
			display: grid;
			gap: .65rem;
			margin-top: 1rem;
			padding-top: .9rem;
		}
		.ve-billing-payment-actions .ve-billing-actions {
			background: transparent !important;
			border-top: 0 !important;
			justify-content: flex-start !important;
			padding: 0 !important;
		}
		.ve-billing-payment-actions .ve-billing-action-message {
			padding: 0 !important;
			text-align: left !important;
		}
		.ve-billing-action-primary {
			background: var(--edge-color-brand-600, #0f64ab) !important;
			border-color: var(--edge-color-brand-600, #0f64ab) !important;
		}
		:root[data-edge-appearance="dark"] .ve-billing-badge,
		:root[data-edge-appearance="dark"] .ve-billing-badge-success,
		:root[data-edge-appearance="dark"] .ve-billing-badge-warning,
		:root[data-edge-appearance="dark"] .ve-billing-badge-danger,
		:root[data-edge-appearance="dark"] .ve-billing-gate-allowed,
		:root[data-edge-appearance="dark"] .ve-billing-gate-blocked {
			background: var(--edge-color-surface-soft, #1b2a38) !important;
		}
	`;
	document.head.appendChild(style);

	const observer = new MutationObserver(scan);
	observer.observe(document.documentElement, { childList: true, subtree: true });
	document.addEventListener("frappe.ui.form.on_refresh", scan);
	window.setTimeout(scan, 0);
})();