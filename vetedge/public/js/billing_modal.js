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
			<button class="btn btn-${primary ? "primary" : "default"} btn-sm" data-action="${action}" ${disabled ? "disabled" : ""}>
				${escapeHtml(label)}
			</button>
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
		return `
			<div class="ve-billing-section">
				<h4>${__("Billing Session")}</h4>
				<div class="ve-billing-grid">
					${labelValue(__("Billing Session"), session.name)}
					${labelValue(__("Session Total"), money(session.total_invoiced || ledger.total_invoiced || session.total_charges, currency))}
					${labelValue(__("Total Paid"), money(session.total_paid || ledger.total_paid, currency))}
					${labelValue(__("Total Outstanding"), money(session.outstanding_amount || ledger.outstanding_amount, currency))}
					${labelValue(__("Payment Status"), session.payment_status || ledger.payment_status)}
					${labelValue(__("Gate Mode"), session.payment_gate_mode || gate.gate)}
					${labelValue(__("Gate Result"), gate.can_proceed ? __("Allowed") : __("Blocked"))}
				</div>
				${warning ? `<div class="alert alert-warning ve-billing-session-warning">${escapeHtml(warning)}</div>` : ""}
			</div>
		`;
	}

	function renderLinkedInvoices(state) {
		const session = state.billing_session || null;
		const invoices = session?.invoices || session?.invoice_ledger?.invoices || [];
		if (!invoices.length) {
			return "";
		}
		return `
			<div class="ve-billing-section">
				<h4>${__("Linked Invoices")}</h4>
				<table class="table table-bordered table-condensed ve-billing-table">
					<thead>
						<tr>
							<th>${__("Invoice")}</th>
							<th>${__("Status")}</th>
							<th class="text-right">${__("Grand Total")}</th>
							<th class="text-right">${__("Paid")}</th>
							<th class="text-right">${__("Outstanding")}</th>
							<th></th>
						</tr>
					</thead>
					<tbody>
						${invoices.map((row) => `
							<tr>
								<td>${escapeHtml(row.name || row.invoice)}</td>
								<td>${escapeHtml(row.status || (row.docstatus === 0 ? __("Draft") : row.docstatus === 1 ? __("Submitted") : __("Cancelled")))}</td>
								<td class="text-right">${money(row.grand_total || row.rounded_total, row.currency)}</td>
								<td class="text-right">${money(row.paid_amount, row.currency)}</td>
								<td class="text-right">${money(row.outstanding_amount, row.currency)}</td>
								<td class="text-right"><button class="btn btn-default btn-xs" data-action="open-ledger-invoice" data-invoice="${escapeHtml(row.name || row.invoice)}">${__("Open")}</button></td>
							</tr>
						`).join("")}
					</tbody>
				</table>
			</div>
		`;
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
			: `<div class="text-muted">${__("No invoice is linked yet.")}</div>`;

		const paymentCurrency = state.currency || invoice?.currency;
		const hasSession = Boolean(state.billing_session);
		const paymentBlock = hasSession || invoice
			? `
				<div class="ve-billing-grid">
					${labelValue(__("Payment Status"), state.payment_status || invoice?.payment_status)}
					${labelValue(hasSession ? __("Billing Session Total") : __("Invoice Total"), money(state.total_amount ?? invoice?.grand_total, paymentCurrency))}
					${labelValue(__("Paid Amount"), money(state.paid_amount ?? invoice?.paid_amount, paymentCurrency))}
					${labelValue(__("Outstanding Amount"), money(state.outstanding_amount ?? invoice?.outstanding_amount, paymentCurrency))}
					${hasSession ? labelValue(__("Linked Invoices"), state.linked_invoice_count || 0) : ""}
				</div>
				${state.outstanding_amount <= 0 && (hasSession || actions.is_paid) ? `<div class="alert alert-success" style="margin-top: 10px;">${__("Paid / No outstanding amount.")}</div>` : ""}
			`
			: `<div class="text-muted">${__("Create and submit an invoice before recording payment.")}</div>`;

		const currentInvoicePaymentBlock = hasSession && invoice
			? `
				<div class="ve-billing-section">
					<h4>${invoice.is_draft ? __("Current Draft Invoice") : __("Current / Latest Invoice")}</h4>
					<div class="ve-billing-grid">
						${labelValue(__("Invoice"), state.current_invoice_name || invoice.name)}
						${labelValue(__("Status"), state.current_invoice_status || invoice.payment_status || invoice.status)}
						${labelValue(__("Invoice Total"), money(state.current_invoice_total, paymentCurrency))}
						${labelValue(__("Invoice Paid"), money(state.current_invoice_paid, paymentCurrency))}
						${labelValue(__("Invoice Outstanding"), money(state.current_invoice_outstanding, paymentCurrency))}
					</div>
				</div>
			`
			: "";

		const gateBlock = gate
			? `
				<div class="alert ${gate.can_proceed ? "alert-success" : "alert-warning"}">
					<div><strong>${escapeHtml(gate.gate || __("Payment Gate"))}</strong></div>
					<div>${escapeHtml(gate.message || "")}</div>
				</div>
			`
			: "";

		const invoiceActionLabel = actions.invoice_action_label || (invoice ? __("Update Draft Invoice") : __("Create Invoice"));
		const openInvoiceLabel = actions.open_invoice_label || __("Open Latest Invoice");
		const invoiceActionMessage = !actions.can_create_or_update_invoice && actions.invoice_action_label
			? `<div class="text-muted small ve-billing-action-message">${escapeHtml(__(actions.invoice_action_label))}</div>`
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
				.ve-billing-grid {
					display: grid;
					grid-template-columns: repeat(2, minmax(0, 1fr));
					gap: 10px 18px;
				}
				.ve-billing-section { margin-bottom: 16px; }
				.ve-billing-section h4 {
					margin: 0 0 10px;
					font-size: 13px;
					font-weight: 600;
				}
				.ve-billing-row > div:last-child {
					font-weight: 500;
					word-break: break-word;
				}
				.ve-billing-actions {
					display: flex;
					flex-wrap: wrap;
					gap: 8px;
					margin-top: 12px;
				}
				.ve-billing-action-message { margin-top: 8px; }
				.ve-billing-session-warning { margin-top: 10px; margin-bottom: 0; }
				.ve-billing-table { margin-bottom: 8px; }
				@media (max-width: 767px) {
					.ve-billing-grid { grid-template-columns: 1fr; }
				}
			</style>
			<div class="ve-billing-section">
				<h4>${__("Source Document")}</h4>
				<div class="ve-billing-grid">
					${labelValue(__("Document"), `${source.doctype || ""} ${source.name || ""}`)}
					${labelValue(__("Status"), source.status)}
					${labelValue(__("Patient"), source.patient_name || source.patient)}
					${labelValue(__("Owner / Customer"), source.owner_name || source.owner)}
					${labelValue(__("Service Branch"), source.service_branch)}
				</div>
			</div>
			${renderSessionSummary(state)}
			${renderLinkedInvoices(state)}
			<div class="ve-billing-section">
				<h4>${__("Invoice")}</h4>
				${invoiceBlock}
			</div>
			<div class="ve-billing-section">
				<h4>${__("Invoice Items")}</h4>
				${renderItems(invoice)}
			</div>
			<div class="ve-billing-section">
				<h4>${__("Taxes / Discounts")}</h4>
				${renderTaxes(invoice)}
			</div>
			<div class="ve-billing-section">
				<h4>${__("Payment")}</h4>
				${paymentBlock}
			</div>
			${currentInvoicePaymentBlock}
			<div class="ve-billing-section">
				<h4>${__("Payment Gate / Proceed Status")}</h4>
				${gateBlock || `<div class="text-muted">${__("No consultation payment gate applies to this document.")}</div>`}
			</div>
			${invoiceActionMessage}
			<div class="ve-billing-actions">${buttons}</div>
		`;
	}

	function callModalMethod(method, args, freezeMessage) {
		return frappe.call({ method, args, freeze: true, freeze_message: freezeMessage });
	}

	async function ensureCleanForm(frm, continueFn) {
		if (!frm.is_dirty()) {
			return continueFn();
		}
		frappe.confirm(
			__("Save changes before opening billing and payment?"),
			async () => {
				await frm.save();
				continueFn();
			},
			() => frappe.msgprint(__("Please save or discard changes before billing."))
		);
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

	function showPaymentDialog(parentDialog, frm, ctx, state, onComplete) {
		const invoice = state.invoice;
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

		function setLoading() {
			dialog.fields_dict.body.$wrapper.html(`<div class="text-muted">${__("Loading billing details...")}</div>`);
		}

		function paint(newState) {
			if (newState) {
				state = newState;
			}
			dialog.fields_dict.body.$wrapper.html(renderState(state || {}, busy));
			bindActions();
		}

		async function refreshSourceForm() {
			await frm.reload_doc();
		}

		async function refreshState() {
			setLoading();
			const response = await callModalMethod(
				"vetedge.services.billing_modal.get_billing_modal_state",
				ctx,
				__("Loading billing details...")
			);
			state = response.message || {};
			paint();
			return state;
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
