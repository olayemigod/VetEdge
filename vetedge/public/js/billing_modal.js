(function () {
	function escapeHtml(value) {
		return frappe.utils.escape_html(value == null || value === "" ? "" : String(value));
	}

	function money(value, currency) {
		return format_currency(value || 0, currency || frappe.defaults.get_default("currency"));
	}

	function labelValue(label, value) {
		return `
			<div class="ve-billing-row">
				<div class="text-muted">${escapeHtml(label)}</div>
				<div>${escapeHtml(value || "-")}</div>
			</div>
		`;
	}

	function actionButton(action, label, primary, disabled) {
		return `
			<button class="btn btn-${primary ? "primary" : "default"} btn-sm ve-billing-action-btn${primary ? " ve-billing-action-primary" : ""}" data-action="${action}" ${disabled ? "disabled" : ""}>
				${escapeHtml(label)}
			</button>
		`;
	}

	function statusTheme(value) {
		const status = String(value || "").toLowerCase();
		if (["paid", "submitted", "completed", "allowed", "active", "closed"].includes(status)) {
			return "success";
		}
		if (["draft", "open", "partly paid", "partial payment gate", "pending", "unpaid"].includes(status)) {
			return "warning";
		}
		if (["cancelled", "blocked", "overdue", "failed"].includes(status)) {
			return "danger";
		}
		return "muted";
	}

	function badge(label, value, theme) {
		const display = value || __("Unknown");
		return `
			<div class="ve-billing-badge-group" aria-label="${escapeHtml(label)}">
				<span class="ve-billing-badge-label">${escapeHtml(label)}</span>
				<span class="ve-billing-badge ve-billing-badge-${escapeHtml(theme || statusTheme(display))}">
					${escapeHtml(display)}
				</span>
			</div>
		`;
	}

	function panel(title, body, extraClass) {
		return `
			<section class="ve-billing-panel ${extraClass || ""}">
				<h4>${escapeHtml(title)}</h4>
				${body}
			</section>
		`;
	}

	function metric(label, value) {
		return `
			<div class="ve-billing-metric">
				<div class="ve-billing-metric-label">${escapeHtml(label)}</div>
				<div class="ve-billing-metric-value">${escapeHtml(value || "-")}</div>
			</div>
		`;
	}

	function renderLoadingState(message) {
		return `
			<div class="ve-billing-edge-modal ve-billing-state" data-edge-product="vetedge">
				<div class="ve-billing-loading-card">
					<div class="ve-billing-spinner"></div>
					<div>${escapeHtml(message || __("Loading billing details..."))}</div>
				</div>
			</div>
		`;
	}

	function renderErrorState(message) {
		return `
			<div class="ve-billing-edge-modal ve-billing-state" data-edge-product="vetedge">
				<div class="ve-billing-error-card">
					<h4>${__("Billing Details Unavailable")}</h4>
					<p>${escapeHtml(message || __("Unable to load billing details. Please try again."))}</p>
					<button class="btn btn-default btn-sm" data-action="refresh">${__("Retry")}</button>
				</div>
			</div>
		`;
	}

	function renderEmptyState(message) {
		return `
			<div class="ve-billing-empty">
				<div class="ve-billing-empty-title">${__("No Billing Activity Yet")}</div>
				<div class="ve-billing-empty-copy">${escapeHtml(message || __("Create an invoice when billing is ready."))}</div>
			</div>
		`;
	}

	function renderItems(invoice) {
		const items = invoice?.items || [];
		if (!items.length) {
			return `<div class="text-muted">${__("No invoice items found.")}</div>`;
		}
		return `
			<table class="table table-bordered table-condensed ve-billing-table">
				<thead>
					<tr>
						<th>${__("Item / Service")}</th>
						<th class="text-right">${__("Qty")}</th>
						<th class="text-right">${__("Rate")}</th>
						<th class="text-right">${__("Amount")}</th>
					</tr>
				</thead>
				<tbody>
					${items.map((row) => `
						<tr>
							<td>
								<div>${escapeHtml(row.item_name || row.item_code)}</div>
								${row.description && row.description !== row.item_name ? `<div class="text-muted small">${escapeHtml(row.description)}</div>` : ""}
							</td>
							<td class="text-right">${escapeHtml(row.qty)}</td>
							<td class="text-right">${money(row.rate, invoice.currency)}</td>
							<td class="text-right">${money(row.amount, invoice.currency)}</td>
						</tr>
					`).join("")}
				</tbody>
			</table>
		`;
	}

	function renderSessionSummary(state) {
		const session = state.billing_session || null;
		if (!session) {
			return "";
		}
		const ledger = session.invoice_ledger || {};
		const currency = ledger.currency || session.currency || state.invoice?.currency;
		const gate = state.payment_gate || session.payment_gate || {};
		const warning = session.session_warning || (ledger.outstanding_amount > 0 ? __("This billing session still has unpaid balance from earlier invoice(s).") : "");
		return panel(__("Current Billing Cycle"), `
				<div class="ve-billing-metric-grid">
					${metric(__("Billing Session"), session.name)}
					${metric(__("Session Total"), money(session.total_invoiced || ledger.total_invoiced || session.total_charges, currency))}
					${metric(__("Total Paid"), money(session.total_paid || ledger.total_paid, currency))}
					${metric(__("Total Outstanding"), money(session.outstanding_amount || ledger.outstanding_amount, currency))}
					${metric(__("Current Billing Cycle Status"), session.payment_status || ledger.payment_status)}
					${metric(__("Gate Mode"), session.payment_gate_mode || gate.gate)}
					${metric(__("Gate Result"), gate.can_proceed ? __("Allowed") : __("Blocked"))}
				</div>
				${warning ? `<div class="ve-billing-notice ve-billing-session-warning">${escapeHtml(warning)}</div>` : ""}
		`);
	}

	function renderLinkedInvoiceAction(row) {
		const invoiceName = row.name || row.invoice;
		const openButton = `<button class="btn btn-default btn-xs" data-action="open-ledger-invoice" data-invoice="${escapeHtml(invoiceName)}">${__("Open")}</button>`;
		if (row.can_pay_outstanding || row.can_pay) {
			return `${openButton} <button class="btn btn-primary btn-xs" data-action="pay-ledger-invoice" data-invoice="${escapeHtml(invoiceName)}">${__(row.action_label || "Pay Outstanding")}</button>`;
		}
		if (row.can_submit_invoice) {
			return `${openButton} <button class="btn btn-primary btn-xs" data-action="submit-ledger-invoice" data-invoice="${escapeHtml(invoiceName)}">${__("Submit Invoice")}</button>`;
		}
		return `${openButton} <span class="text-muted small">${escapeHtml(__(row.action_label || ""))}</span>`;
	}

	function getLinkedInvoiceRows(state) {
		const session = state.billing_session || {};
		const history = state.invoice_history || state.billing_group_invoice_history || [];
		if (history.length) {
			return history;
		}
		return session?.invoices || session?.invoice_ledger?.invoices || [];
	}

	function renderLinkedInvoices(state) {
		const session = state.billing_session || null;
		const invoices = getLinkedInvoiceRows(state);
		if (!invoices.length) {
			return "";
		}
		return panel(__("Linked Invoice History"), `
				<table class="table table-bordered table-condensed ve-billing-table">
					<thead>
						<tr>
							<th>${__("Invoice")}</th>
							<th>${__("Status")}</th>
							<th>${__("Posting Date")}</th>
							<th>${__("Due Date")}</th>
							<th class="text-right">${__("Grand Total")}</th>
							<th class="text-right">${__("Paid")}</th>
							<th class="text-right">${__("Outstanding")}</th>
							<th>${__("Source")}</th>
							<th>${__("Action")}</th>
						</tr>
					</thead>
					<tbody>
						${invoices.map((row) => `
							<tr>
								<td>${escapeHtml(row.name || row.invoice)}</td>
								<td>${escapeHtml(row.payment_status || row.payment_state || row.status || (row.docstatus === 0 ? __("Draft") : row.docstatus === 1 ? __("Submitted") : __("Cancelled")))}</td>
								<td>${escapeHtml(row.posting_date || "")}</td>
								<td>${escapeHtml(row.due_date || "")}</td>
								<td class="text-right">${money(row.grand_total || row.rounded_total, row.currency)}</td>
								<td class="text-right">${money(row.paid_amount, row.currency)}</td>
								<td class="text-right">${money(row.outstanding_amount, row.currency)}</td>
								<td>${escapeHtml(row.source_label || row.relation_type || "")}</td>
								<td>${renderLinkedInvoiceAction(row)}</td>
							</tr>
						`).join("")}
					</tbody>
				</table>
		`);
	}

	function renderPatientOutstandingContext(state) {
		const invoices = state.patient_outstanding_context || [];
		if (!invoices.length) {
			return "";
		}
		return panel(__("Other Outstanding Invoices for this Patient"), `
				<div class="ve-billing-notice">
					${__("These invoices are not part of this consultation billing group. Paying them will not satisfy this consultation's payment gate unless explicitly linked.")}
				</div>
				<table class="table table-bordered table-condensed ve-billing-table">
					<thead>
						<tr>
							<th>${__("Invoice")}</th>
							<th>${__("Status")}</th>
							<th class="text-right">${__("Grand Total")}</th>
							<th class="text-right">${__("Paid")}</th>
							<th class="text-right">${__("Outstanding")}</th>
							<th>${__("Action")}</th>
						</tr>
					</thead>
					<tbody>
						${invoices.map((row) => `
							<tr>
								<td>${escapeHtml(row.name || row.invoice)}</td>
								<td>${escapeHtml(row.payment_status || row.payment_state || row.status || "")}</td>
								<td class="text-right">${money(row.grand_total || row.rounded_total, row.currency)}</td>
								<td class="text-right">${money(row.paid_amount, row.currency)}</td>
								<td class="text-right">${money(row.outstanding_amount, row.currency)}</td>
								<td>${renderLinkedInvoiceAction(row)}</td>
							</tr>
						`).join("")}
					</tbody>
				</table>
		`);
	}

	function renderTaxes(invoice) {
		const taxes = invoice?.taxes || [];
		if (!taxes.length && !invoice?.discount_amount) {
			return `<div class="text-muted">${__("No taxes or discounts recorded.")}</div>`;
		}
		return `
			<div class="ve-billing-grid">
				${invoice.discount_amount ? labelValue(__("Discount"), money(invoice.discount_amount, invoice.currency)) : ""}
				${labelValue(__("Taxes and Charges"), money(invoice.total_taxes_and_charges, invoice.currency))}
			</div>
			${taxes.length ? `
				<table class="table table-bordered table-condensed ve-billing-table">
					<thead>
						<tr>
							<th>${__("Tax / Charge")}</th>
							<th class="text-right">${__("Rate")}</th>
							<th class="text-right">${__("Amount")}</th>
						</tr>
					</thead>
					<tbody>
						${taxes.map((row) => `
							<tr>
								<td>${escapeHtml(row.description || row.account_head)}</td>
								<td class="text-right">${escapeHtml(row.rate || 0)}%</td>
								<td class="text-right">${money(row.tax_amount, invoice.currency)}</td>
							</tr>
						`).join("")}
					</tbody>
				</table>
			` : ""}
		`;
	}

	function renderState(state, busy) {
		const source = state.source || {};
		const invoice = state.invoice || null;
		const gate = state.payment_gate || null;
		const actions = state.actions || {};
		const invoiceStatus = invoice?.status || (invoice?.is_submitted ? __("Submitted") : invoice?.is_draft ? __("Draft") : "");
		const paymentCurrency = state.currency || invoice?.currency;
		const hasSession = Boolean(state.billing_session);
		const hasBillingActivity = Boolean(invoice || hasSession || getLinkedInvoiceRows(state).length);

		const invoiceBlock = invoice
			? `
				<div class="ve-billing-grid">
					${labelValue(__("Invoice"), invoice.name)}
					${labelValue(__("Customer"), invoice.customer)}
					${labelValue(__("Status"), invoiceStatus)}
					${labelValue(__("Posting Date"), invoice.posting_date)}
					${labelValue(__("Grand Total"), money(invoice.grand_total, invoice.currency))}
					${labelValue(__("Outstanding"), money(invoice.outstanding_amount, invoice.currency))}
				</div>
			`
			: renderEmptyState(__("No invoice is linked yet."));

		const paymentBlock = hasSession || invoice
			? `
					<div class="ve-billing-metric-grid">
						${metric(__("Billing Group Payment Status"), state.payment_status || invoice?.payment_status)}
						${hasSession ? metric(__("Current Billing Cycle Status"), state.billing_session_status) : ""}
						${metric(hasSession ? __("Billing Group Total") : __("Invoice Total"), money(state.total_amount ?? invoice?.grand_total, paymentCurrency))}
						${metric(__("Paid Amount"), money(state.paid_amount ?? invoice?.paid_amount, paymentCurrency))}
						${metric(__("Outstanding Amount"), money(state.outstanding_amount ?? invoice?.outstanding_amount, paymentCurrency))}
						${hasSession ? metric(__("Linked Invoices"), state.linked_invoice_count || 0) : ""}
				</div>
				${state.outstanding_amount <= 0 && (hasSession || actions.is_paid) ? `<div class="ve-billing-notice ve-billing-notice-success">${__("Paid / No outstanding amount.")}</div>` : ""}
			`
			: renderEmptyState(__("Create and submit an invoice before recording payment."));

		const currentInvoicePaymentBlock = hasSession && invoice
			? `
				${panel(invoice.is_draft ? __("Current Draft Invoice") : __("Current / Latest Invoice"), `
					<div class="ve-billing-grid">
						${labelValue(__("Invoice"), state.current_invoice_name || invoice.name)}
						${labelValue(__("Status"), state.current_invoice_status || invoice.payment_status || invoice.status)}
						${labelValue(__("Invoice Total"), money(state.current_invoice_total, paymentCurrency))}
						${labelValue(__("Invoice Paid"), money(state.current_invoice_paid, paymentCurrency))}
						${labelValue(__("Invoice Outstanding"), money(state.current_invoice_outstanding, paymentCurrency))}
					</div>
				`)}
			`
			: "";

		const gateBlock = gate
			? `
				<div class="ve-billing-gate ve-billing-gate-${gate.can_proceed ? "allowed" : "blocked"}">
					<div class="ve-billing-gate-header">
						${badge(__("Payment Gate"), gate.gate || __("Payment Gate"), gate.can_proceed ? "success" : "warning")}
						${badge(__("Gate Result"), gate.can_proceed ? __("Allowed") : __("Blocked"), gate.can_proceed ? "success" : "danger")}
					</div>
					<div class="ve-billing-gate-message">${escapeHtml(gate.message || "")}</div>
				</div>
			`
			: "";

		const invoiceActionLabel = actions.invoice_action_label || __("Create Invoice");
		const openInvoiceLabel = actions.open_invoice_label || __("Open Latest Invoice");
		const invoiceActionMessage = !actions.can_create_or_update_invoice && actions.invoice_action_label
			? `<div class="ve-billing-action-message">${escapeHtml(__(actions.invoice_action_label))}</div>`
			: "";
		const buttons = [
			actions.can_create_or_update_invoice ? actionButton("create-invoice", __(invoiceActionLabel), true, busy) : "",
			actions.can_submit_invoice ? actionButton("submit-invoice", __("Submit Invoice"), true, busy) : "",
			actions.can_record_payment ? actionButton("record-payment", __("Record Payment"), true, busy) : "",
			actions.can_open_full_invoice ? actionButton("open-invoice", __(openInvoiceLabel), false, busy) : "",
			actionButton("refresh", __("Refresh Status"), false, busy),
		].filter(Boolean).join(" ");

		return `
			<style>
				.ve-billing-edge-modal {
					--ve-primary: var(--edge-primary, #1677ff);
					--ve-bg: var(--edge-bg, #f7f9fc);
					--ve-surface: var(--edge-surface, #ffffff);
					--ve-border: var(--edge-border, #dfe5ef);
					--ve-text: var(--edge-text, #172033);
					--ve-muted: var(--edge-text-muted, #667085);
					--ve-success: var(--edge-success, #0f9f6e);
					--ve-warning: var(--edge-warning, #b7791f);
					--ve-danger: var(--edge-danger, #d92d20);
					color: var(--ve-text);
					background: var(--ve-bg);
					border: 1px solid var(--ve-border);
					border-radius: 8px;
					overflow: hidden;
					font-family: var(--edge-font, inherit);
				}
				.ve-billing-hero {
					display: flex;
					align-items: flex-start;
					justify-content: space-between;
					gap: 16px;
					padding: 18px 20px;
					background: var(--ve-surface);
					border-bottom: 1px solid var(--ve-border);
				}
				.ve-billing-product {
					font-size: 11px;
					font-weight: 700;
					color: var(--ve-primary);
					text-transform: uppercase;
					letter-spacing: .08em;
				}
				.ve-billing-title {
					margin-top: 4px;
					font-size: 20px;
					font-weight: 700;
					line-height: 1.25;
				}
				.ve-billing-subtitle {
					margin-top: 4px;
					color: var(--ve-muted);
					font-size: 13px;
				}
				.ve-billing-badge-row {
					display: flex;
					flex-wrap: wrap;
					gap: 8px;
					justify-content: flex-end;
				}
				.ve-billing-body {
					padding: 16px;
					display: flex;
					flex-direction: column;
					gap: 14px;
				}
				.ve-billing-panel {
					background: var(--ve-surface);
					border: 1px solid var(--ve-border);
					border-radius: 8px;
					padding: 14px;
					box-shadow: 0 1px 2px rgba(16, 24, 40, .04);
				}
				.ve-billing-grid {
					display: grid;
					grid-template-columns: repeat(2, minmax(0, 1fr));
					gap: 10px 18px;
				}
				.ve-billing-panel h4 {
					margin: 0 0 10px;
					font-size: 13px;
					font-weight: 700;
					color: var(--ve-text);
				}
				.ve-billing-row { min-width: 0; }
				.ve-billing-row > div:first-child { font-size: 12px; }
				.ve-billing-row > div:last-child {
					font-weight: 500;
					word-break: break-word;
				}
				.ve-billing-metric-grid {
					display: grid;
					grid-template-columns: repeat(4, minmax(0, 1fr));
					gap: 10px;
				}
				.ve-billing-metric {
					border: 1px solid var(--ve-border);
					border-radius: 8px;
					padding: 10px;
					background: var(--ve-bg);
					min-width: 0;
				}
				.ve-billing-metric-label {
					color: var(--ve-muted);
					font-size: 12px;
					margin-bottom: 4px;
				}
				.ve-billing-metric-value {
					font-weight: 700;
					word-break: break-word;
				}
				.ve-billing-badge-group {
					display: inline-flex;
					align-items: center;
					gap: 6px;
					border: 1px solid var(--ve-border);
					border-radius: 999px;
					padding: 4px 8px;
					background: var(--ve-bg);
				}
				.ve-billing-badge-label {
					color: var(--ve-muted);
					font-size: 11px;
					font-weight: 600;
				}
				.ve-billing-badge {
					border-radius: 999px;
					padding: 2px 7px;
					font-size: 11px;
					font-weight: 700;
					background: #eef2f7;
					color: var(--ve-muted);
				}
				.ve-billing-badge-success { background: #e7f8ef; color: var(--ve-success); }
				.ve-billing-badge-warning { background: #fff6df; color: var(--ve-warning); }
				.ve-billing-badge-danger { background: #fee4e2; color: var(--ve-danger); }
				.ve-billing-gate {
					border-radius: 8px;
					border: 1px solid var(--ve-border);
					padding: 12px;
				}
				.ve-billing-gate-allowed { background: #f0fdf4; }
				.ve-billing-gate-blocked { background: #fff7ed; }
				.ve-billing-gate-header {
					display: flex;
					flex-wrap: wrap;
					gap: 8px;
					margin-bottom: 8px;
				}
				.ve-billing-gate-message { color: var(--ve-text); }
				.ve-billing-actions {
					display: flex;
					flex-wrap: wrap;
					gap: 8px;
					justify-content: flex-end;
					padding: 14px 16px;
					background: var(--ve-surface);
					border-top: 1px solid var(--ve-border);
				}
				.ve-billing-action-btn {
					border-radius: 6px;
					font-weight: 600;
				}
				.ve-billing-action-primary {
					background: var(--ve-primary);
					border-color: var(--ve-primary);
				}
				.ve-billing-action-message {
					color: var(--ve-muted);
					font-size: 12px;
					text-align: right;
					padding: 0 16px 12px;
				}
				.ve-billing-notice {
					margin-top: 10px;
					border-radius: 8px;
					padding: 10px 12px;
					font-weight: 600;
				}
				.ve-billing-notice-success { background: #e7f8ef; color: var(--ve-success); }
				.ve-billing-session-warning { margin-top: 10px; margin-bottom: 0; }
				.ve-billing-table {
					margin-bottom: 8px;
					background: var(--ve-surface);
				}
				.ve-billing-table th {
					background: var(--ve-bg);
					color: var(--ve-muted);
					font-size: 12px;
					font-weight: 700;
				}
				.ve-billing-empty {
					border: 1px dashed var(--ve-border);
					border-radius: 8px;
					padding: 18px;
					text-align: center;
					background: var(--ve-bg);
				}
				.ve-billing-empty-title {
					font-weight: 700;
					margin-bottom: 4px;
				}
				.ve-billing-empty-copy { color: var(--ve-muted); }
				.ve-billing-state { padding: 24px; }
				.ve-billing-loading-card,
				.ve-billing-error-card {
					background: var(--ve-surface);
					border: 1px solid var(--ve-border);
					border-radius: 8px;
					padding: 22px;
					text-align: center;
				}
				.ve-billing-error-card p { color: var(--ve-muted); }
				.ve-billing-spinner {
					width: 28px;
					height: 28px;
					border: 3px solid #d9e2ef;
					border-top-color: var(--ve-primary);
					border-radius: 999px;
					margin: 0 auto 12px;
					animation: ve-billing-spin .8s linear infinite;
				}
				@keyframes ve-billing-spin { to { transform: rotate(360deg); } }
				@media (max-width: 767px) {
					.ve-billing-grid { grid-template-columns: 1fr; }
					.ve-billing-metric-grid { grid-template-columns: 1fr; }
					.ve-billing-hero { flex-direction: column; }
					.ve-billing-badge-row { justify-content: flex-start; }
				}
			</style>
			<div class="ve-billing-edge-modal" data-edge-product="vetedge">
				<div class="ve-billing-hero">
					<div>
						<div class="ve-billing-product">${__("VetEdge Billing")}</div>
						<div class="ve-billing-title">${__("Billing & Payment")}</div>
						<div class="ve-billing-subtitle">${escapeHtml(`${source.doctype || ""} ${source.name || ""}`.trim() || __("Source Document"))}</div>
					</div>
					<div class="ve-billing-badge-row">
						${badge(__("Invoice Status"), invoiceStatus || __("No Invoice"), invoice ? null : "muted")}
						${badge(__("Payment Status"), state.payment_status || invoice?.payment_status || __("Not Billed"))}
						${gate ? badge(__("Payment Gate"), gate.can_proceed ? __("Allowed") : __("Blocked"), gate.can_proceed ? "success" : "danger") : ""}
					</div>
				</div>
				<div class="ve-billing-body">
					${panel(__("Source Summary"), `
						<div class="ve-billing-grid">
							${labelValue(__("Document"), `${source.doctype || ""} ${source.name || ""}`)}
							${labelValue(__("Status"), source.status)}
							${labelValue(__("Patient"), source.patient_name || source.patient)}
							${labelValue(__("Owner / Customer"), source.owner_name || source.owner)}
							${labelValue(__("Branch"), source.service_branch)}
							${labelValue(__("Company"), source.company)}
						</div>
					`)}
					${!hasBillingActivity ? renderEmptyState(__("No invoice or billing group has been created for this source.")) : ""}
					${renderSessionSummary(state)}
					${renderLinkedInvoices(state)}
					${renderPatientOutstandingContext(state)}
					${panel(__("Invoice"), invoiceBlock)}
					${panel(__("Line Items"), renderItems(invoice))}
					${panel(__("Totals"), renderTaxes(invoice))}
					${panel(__("Payment Summary"), paymentBlock)}
					${currentInvoicePaymentBlock}
					${panel(__("Warnings / Blockers"), gateBlock || renderEmptyState(__("No consultation payment gate applies to this document.")))}
				</div>
				${invoiceActionMessage}
				<div class="ve-billing-actions">${buttons}</div>
			</div>
		`;
	}

	function callModalMethod(method, args, freezeMessage) {
		return frappe.call({ method, args, freeze: true, freeze_message: freezeMessage });
	}

	async function ensureCleanForm(frm, continueFn) {
		if (!frm.is_dirty()) {
			return continueFn();
		}
		frappe.msgprint(__("Please save or discard changes before opening billing and payment."));
	}

	function findLinkedInvoice(state, invoiceName) {
		const session = state.billing_session || null;
		const invoices = [...getLinkedInvoiceRows(state), ...(state.patient_outstanding_context || [])];
		return invoices.find((row) => (row.name || row.invoice) === invoiceName);
	}
	function openFullInvoice(invoice) {
		if (!invoice) {
			return;
		}
		frappe.open_in_new_tab = true;
		frappe.set_route("Form", "Sales Invoice", invoice);
	}

	function getDialogContext(frm) {
		return { source_doctype: frm.doc.doctype, source_name: frm.doc.name };
	}

	function showPaymentDialog(parentDialog, frm, ctx, state, onComplete, selectedInvoice) {
		const invoice = selectedInvoice || state.invoice;
		const paymentModes = state.payment_modes || [];
		const paymentDialog = new frappe.ui.Dialog({
			title: __("Record Payment"),
			fields: [
				{
					fieldname: "amount",
					fieldtype: "Currency",
					label: __("Amount"),
					default: invoice.outstanding_amount,
					reqd: 1,
				},
				{
					fieldname: "mode_of_payment",
					fieldtype: "Link",
					label: __("Mode of Payment"),
					options: "Mode of Payment",
					default: paymentModes[0] || "",
				},
				{
					fieldname: "paid_to",
					fieldtype: "Link",
					label: __("Paid To Account"),
					options: "Account",
				},
				{
					fieldname: "posting_date",
					fieldtype: "Date",
					label: __("Posting Date"),
					default: frappe.datetime.now_date(),
					reqd: 1,
				},
				{
					fieldname: "reference_no",
					fieldtype: "Data",
					label: __("Reference Number"),
				},
				{
					fieldname: "reference_date",
					fieldtype: "Date",
					label: __("Reference Date"),
				},
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: __("Remarks"),
				},
			],
			primary_action_label: __("Submit Payment"),
			primary_action(values) {
				paymentDialog.disable_primary_action();
				callModalMethod(
					"vetedge.services.billing_modal.record_modal_invoice_payment",
					{
						...ctx,
						invoice: invoice.name,
						amount: values.amount,
						mode_of_payment: values.mode_of_payment,
						paid_to: values.paid_to,
						posting_date: values.posting_date,
						reference_no: values.reference_no,
						reference_date: values.reference_date,
						remarks: values.remarks,
					},
					__("Submitting payment...")
				).then((response) => {
					paymentDialog.hide();
					frappe.show_alert({ message: __("Payment recorded."), indicator: "green" });
					onComplete(response.message?.state);
				}).catch(() => {
					paymentDialog.enable_primary_action();
				});
			},
		});
		paymentDialog.show();
		parentDialog.$wrapper.css("z-index", 1040);
	}

	function showDialog(frm) {
		const dialog = new frappe.ui.Dialog({
			title: __("Billing & Payment"),
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
			primary_action_label: __("Close"),
			primary_action() {
				dialog.hide();
			},
		});
		const ctx = getDialogContext(frm);
		let state = null;
		let busy = false;
		let errorMessage = "";

		function setLoading() {
			errorMessage = "";
			dialog.fields_dict.body.$wrapper.html(renderLoadingState(__("Loading billing details...")));
		}

		function paint(newState) {
			if (newState) {
				state = newState;
			}
			if (errorMessage) {
				dialog.fields_dict.body.$wrapper.html(renderErrorState(errorMessage));
				bindActions();
				return;
			}
			dialog.fields_dict.body.$wrapper.html(renderState(state || {}, busy));
			bindActions();
		}

		async function refreshSourceForm() {
			await frm.reload_doc();
		}

		async function refreshState() {
			setLoading();
			try {
				const response = await callModalMethod(
					"vetedge.services.billing_modal.get_billing_modal_state",
					ctx,
					__("Loading billing details...")
				);
				state = response.message || {};
				errorMessage = "";
				paint();
				return state;
			} catch (error) {
				errorMessage = error?._server_messages || error?.message || __("Unable to load billing details.");
				paint();
				return null;
			}
		}

		async function runAction(method, args, message) {
			if (busy) {
				return;
			}
			busy = true;
			paint();
			try {
				const response = await callModalMethod(method, args, message);
				state = response.message?.state || state;
				await refreshSourceForm();
				paint();
			} finally {
				busy = false;
				paint();
			}
		}

		function bindActions() {
			const wrapper = dialog.fields_dict.body.$wrapper;
			wrapper.find("[data-action='refresh']").on("click", () => refreshState());
			wrapper.find("[data-action='create-invoice']").on("click", () => {
				runAction("vetedge.services.billing_modal.create_or_update_modal_invoice", ctx, __("Creating invoice..."));
			});
			wrapper.find("[data-action='submit-invoice']").on("click", () => {
				runAction(
					"vetedge.services.billing_modal.submit_modal_invoice",
					{ ...ctx, invoice: state?.invoice?.name },
					__("Submitting invoice...")
				);
			});
			wrapper.find("[data-action='record-payment']").on("click", () => {
				showPaymentDialog(dialog, frm, ctx, state, async (newState) => {
					state = newState || state;
					await refreshSourceForm();
					paint();
				});
			});
			wrapper.find("[data-action='open-invoice']").on("click", () => {
				openFullInvoice(state?.actions?.open_invoice_name || state?.open_invoice_name || state?.invoice?.name);
			});
			wrapper.find("[data-action='open-ledger-invoice']").on("click", (event) => {
				openFullInvoice(event.currentTarget.dataset.invoice);
			});
			wrapper.find("[data-action='pay-ledger-invoice']").on("click", (event) => {
				const invoiceName = event.currentTarget.dataset.invoice;
				const invoice = findLinkedInvoice(state, invoiceName);
				if (!invoice || !(invoice.can_pay_outstanding || invoice.can_pay)) {
					frappe.msgprint(__("This invoice cannot be paid from here."));
					return;
				}
				showPaymentDialog(dialog, frm, ctx, state, async (newState) => {
					state = newState || state;
					await refreshSourceForm();
					paint();
				}, invoice);
			});
			wrapper.find("[data-action='submit-ledger-invoice']").on("click", (event) => {
				runAction(
					"vetedge.services.billing_modal.submit_modal_invoice",
					{ ...ctx, invoice: event.currentTarget.dataset.invoice },
					__("Submitting invoice...")
				);
			});
		}

		dialog.show();
		refreshState();
	}

	window.vetedgeBillingModal = {
		open(frm) {
			if (!frm || frm.is_new()) {
				frappe.msgprint(__("Save this document before billing."));
				return;
			}
			return ensureCleanForm(frm, () => showDialog(frm));
		},
	};
})();
