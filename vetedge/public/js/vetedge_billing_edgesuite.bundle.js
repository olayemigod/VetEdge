const API = Object.freeze({
	state: "vetedge.services.billing_modal.get_billing_modal_state",
	invoice: "vetedge.services.billing_modal.create_or_update_modal_invoice",
	submit: "vetedge.services.billing_modal.submit_modal_invoice",
	payment: "vetedge.services.billing_modal.record_modal_invoice_payment",
});

let installed = false;

function presenter() {
	return window.VetEdgeEdgeModalPresenter;
}

function call(method, args = {}) {
	return frappe.call({ method, args }).then((response) => response.message || {});
}

function sourceContext(frm) {
	return { source_doctype: frm.doc.doctype, source_name: frm.doc.name };
}

function money(value, currency) {
	const code = currency || frappe.boot?.sysdefaults?.currency || frappe.defaults?.get_default?.("currency") || "NGN";
	try {
		return new Intl.NumberFormat(undefined, { style: "currency", currency: code }).format(Number(value || 0));
	} catch (_error) {
		return `${code} ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
	}
}

function invoiceStatus(invoice = {}) {
	if (!invoice?.name) return __("No Invoice");
	if (Number(invoice.docstatus) === 0) return __("Draft");
	if (Number(invoice.docstatus) === 2) return __("Cancelled");
	return invoice.payment_status || invoice.status || __("Submitted");
}

function statusTone(value) {
	const text = String(value || "").toLowerCase();
	if (["paid", "submitted", "allowed", "completed", "closed"].some((token) => text.includes(token))) return "success";
	if (["draft", "open", "unpaid", "partly", "pending"].some((token) => text.includes(token))) return "warning";
	if (["blocked", "cancelled", "overdue", "failed"].some((token) => text.includes(token))) return "danger";
	return "neutral";
}

function invoiceHistory(state = {}) {
	return state.invoice_history || state.billing_group_invoice_history || state.billing_session?.invoices || [];
}

function payableInvoices(state = {}) {
	const rows = invoiceHistory(state).filter((row) => (row.can_pay_outstanding || row.can_pay) && Number(row.outstanding_amount || 0) > 0);
	const current = state.invoice;
	if (current?.name && Number(current.docstatus) === 1 && Number(current.outstanding_amount || 0) > 0 && !rows.some((row) => (row.name || row.invoice) === current.name)) {
		rows.unshift(current);
	}
	return rows;
}

function ledgerRows(state = {}) {
	return invoiceHistory(state).map((row) => ({
		name: row.name || row.invoice,
		status: row.payment_status || row.payment_state || row.status || (Number(row.docstatus) === 0 ? __("Draft") : __("Submitted")),
		posting_date: row.posting_date || "",
		due_date: row.due_date || "",
		grand_total: money(row.grand_total || row.rounded_total, row.currency),
		paid_amount: money(row.paid_amount, row.currency),
		outstanding_amount: money(row.outstanding_amount, row.currency),
		source: row.source_label || row.relation_type || "",
	}));
}

function currentInvoiceItemRows(state = {}) {
	const invoice = state.invoice || {};
	return (invoice.items || []).map((row, index) => ({
		name: `${invoice.name || "invoice"}-${index + 1}`,
		item_code: row.item_code || "",
		item_name: row.item_name || row.description || row.item_code || "",
		qty: Number(row.qty || 0),
		rate: money(row.rate, invoice.currency),
		amount: money(row.amount, invoice.currency),
	}));
}

function patientOutstandingRows(state = {}) {
	return (state.patient_outstanding_context || []).map((row) => ({
		name: row.name || row.invoice,
		posting_date: row.posting_date || "",
		outstanding_amount: money(row.outstanding_amount, row.currency),
		status: row.payment_status || row.status || __("Outstanding"),
	}));
}

function stateMetrics(state = {}) {
	const currency = state.currency || state.invoice?.currency || state.billing_session?.currency;
	return [
		{ label: __("Billing Cycle Total"), value: money(state.billing_session_total ?? state.total_amount, currency), tone: "primary" },
		{ label: __("Total Paid"), value: money(state.billing_session_paid ?? state.paid_amount, currency), tone: "success" },
		{ label: __("Total Outstanding"), value: money(state.billing_session_outstanding ?? state.outstanding_amount, currency), tone: Number(state.billing_session_outstanding ?? state.outstanding_amount || 0) > 0 ? "warning" : "success" },
		{ label: __("Linked Invoices"), value: Number(state.linked_invoice_count || invoiceHistory(state).length || 0), tone: "info" },
	];
}

function sourceMetrics(state = {}) {
	const source = state.source || {};
	return [
		{ label: __("Patient"), value: source.patient_name || source.patient || "—", tone: "neutral" },
		{ label: __("Owner / Customer"), value: source.owner_name || source.owner || "—", tone: "neutral" },
		{ label: __("Branch"), value: source.service_branch || "—", tone: "neutral" },
		{ label: __("Company"), value: source.company || "—", tone: "neutral" },
	];
}

function billingSections(state = {}) {
	const sections = [
		{
			title: __("Source Summary"),
			metrics: sourceMetrics(state),
		},
	];
	const itemRows = currentInvoiceItemRows(state);
	if (state.invoice?.name) {
		sections.push({
			title: __("Current Invoice Items"),
			message: `${state.invoice.name} · ${invoiceStatus(state.invoice)}`,
			columns: [
				{ fieldname: "item_code", label: __("Item") },
				{ fieldname: "item_name", label: __("Description") },
				{ fieldname: "qty", label: __("Qty") },
				{ fieldname: "rate", label: __("Rate") },
				{ fieldname: "amount", label: __("Amount") },
			],
			rows: itemRows,
			rowKey: "name",
			emptyTitle: __("No invoice items"),
			emptyDescription: __("The current invoice does not contain billable items yet."),
		});
	}
	const ledger = ledgerRows(state);
	sections.push({
		title: __("Linked Invoice History"),
		message: __("All invoices in this VetEdge billing cycle are shown here. Select a row to open that invoice in the same tab."),
		columns: [
			{ fieldname: "name", label: __("Invoice") },
			{ fieldname: "status", label: __("Status"), fieldtype: "Status" },
			{ fieldname: "posting_date", label: __("Posting Date"), fieldtype: "Date" },
			{ fieldname: "due_date", label: __("Due Date"), fieldtype: "Date" },
			{ fieldname: "grand_total", label: __("Grand Total") },
			{ fieldname: "paid_amount", label: __("Paid") },
			{ fieldname: "outstanding_amount", label: __("Outstanding") },
			{ fieldname: "source", label: __("Source") },
		],
		rows: ledger,
		rowKey: "name",
		onRowClick: (row) => openInvoiceSameTab(row?.name),
		emptyTitle: __("No linked invoices"),
		emptyDescription: __("Create the first invoice when billing is ready."),
	});
	const outstanding = patientOutstandingRows(state);
	if (outstanding.length) {
		sections.push({
			title: __("Patient Outstanding Context"),
			message: __("Other outstanding invoices for this patient are shown for context and are not merged into the current billing cycle."),
			columns: [
				{ fieldname: "name", label: __("Invoice") },
				{ fieldname: "posting_date", label: __("Posting Date"), fieldtype: "Date" },
				{ fieldname: "outstanding_amount", label: __("Outstanding") },
				{ fieldname: "status", label: __("Status"), fieldtype: "Status" },
			],
			rows: outstanding,
			rowKey: "name",
			onRowClick: (row) => openInvoiceSameTab(row?.name),
		});
	}
	return sections;
}

function openInvoiceSameTab(invoice) {
	if (!invoice) return;
	frappe.set_route("Form", "Sales Invoice", invoice);
}

function findPayableInvoice(state = {}) {
	return payableInvoices(state)[0] || null;
}

function paymentFields(state, invoice) {
	const payable = payableInvoices(state);
	const selectedName = invoice?.name || invoice?.invoice || "";
	return [
		{
			fieldname: "invoice",
			label: __("Invoice"),
			type: "select",
			required: true,
			options: payable.map((row) => {
				const name = row.name || row.invoice;
				return { value: name, label: `${name} · ${money(row.outstanding_amount, row.currency)} ${__("outstanding")}` };
			}),
			default: selectedName,
			onChange(value, values, modalView) {
				const selected = payable.find((row) => (row.name || row.invoice) === value);
				if (!selected) return;
				modalView.update({ values: { ...values, invoice: value, amount: selected.outstanding_amount || 0 } });
			},
		},
		{ fieldname: "amount", label: __("Amount"), type: "number", required: true, min: 0, step: "0.01", default: invoice.outstanding_amount || 0 },
		{ fieldname: "mode_of_payment", label: __("Mode of Payment"), type: "select", options: (state.payment_modes || []).map((value) => ({ value, label: value })), default: state.payment_modes?.[0] || "" },
		{ fieldname: "posting_date", label: __("Posting Date"), type: "date", required: true, default: frappe.datetime?.get_today?.() || "" },
		{ fieldname: "reference_no", label: __("Reference Number"), type: "text" },
		{ fieldname: "reference_date", label: __("Reference Date"), type: "date" },
		{ fieldname: "remarks", label: __("Remarks"), type: "textarea", rows: 3 },
	];
}

function openPaymentModal(frm, state, invoice, reopen) {
	if (!invoice?.name && !invoice?.invoice) return;
	const invoiceName = invoice.name || invoice.invoice;
	let paymentModal;
	paymentModal = presenter().open({
		title: __("Record Payment"),
		subtitle: __("Select any payable invoice in the current billing cycle."),
		size: "md",
		fields: paymentFields(state, invoice),
		values: {
			invoice: invoiceName,
			amount: invoice.outstanding_amount || 0,
			mode_of_payment: state.payment_modes?.[0] || "",
			posting_date: frappe.datetime?.get_today?.() || "",
			reference_no: "",
			reference_date: "",
			remarks: "",
		},
		actions: [{
			label: __("Submit Payment"),
			primary: true,
			async onClick(values) {
				paymentModal.update({ busy: true, error: "" });
				try {
					await call(API.payment, {
						...sourceContext(frm),
						invoice: values.invoice,
						amount: values.amount,
						mode_of_payment: values.mode_of_payment,
						posting_date: values.posting_date,
						reference_no: values.reference_no || undefined,
						reference_date: values.reference_date || undefined,
						remarks: values.remarks || undefined,
					});
					paymentModal.close();
					frappe.show_alert({ message: __("Payment recorded."), indicator: "green" });
					await frm.reload_doc?.();
					reopen();
				} catch (error) {
					paymentModal.update({ busy: false, error: error?.message || __("Payment could not be recorded."), errorTitle: __("Payment failed") });
				}
			},
		}],
	});
}

function buildBillingSpec(frm, state, controller) {
	const source = state.source || {};
	const invoice = state.invoice || {};
	const actions = state.actions || {};
	const gate = state.payment_gate || {};
	const buttons = [];
	if (actions.can_create_or_update_invoice || actions.can_create_invoice) {
		buttons.push({
			label: actions.invoice_action_label || (invoice?.name ? __("Update Draft Invoice") : __("Create Invoice")),
			primary: true,
			onClick: () => controller.invoice(),
		});
	}
	if (actions.can_submit_invoice && invoice?.name) {
		buttons.push({ label: __("Submit Invoice"), primary: true, onClick: () => controller.submit(invoice.name) });
	}
	const payable = findPayableInvoice(state);
	if (payable) buttons.push({ label: __("Pay Outstanding"), primary: true, onClick: () => controller.payment(payable) });
	const openInvoice = actions.open_invoice_name || state.open_invoice_name || invoice?.name;
	if (openInvoice) buttons.push({ label: actions.open_invoice_label || __("Open Invoice"), onClick: () => openInvoiceSameTab(openInvoice) });

	const message = gate.message || state.billing_session?.session_warning || "";
	return {
		title: __("Billing & Payment"),
		subtitle: `${source.doctype || frm.doc.doctype} ${source.name || frm.doc.name}`,
		size: "xl",
		metrics: stateMetrics(state),
		badges: [
			{ label: `${__("Invoice Status")}: ${invoiceStatus(invoice)}`, status: invoiceStatus(invoice), tone: statusTone(invoiceStatus(invoice)) },
			{ label: `${__("Payment Status")}: ${state.payment_status || invoice.payment_status || __("Not Billed")}`, status: state.payment_status || invoice.payment_status, tone: statusTone(state.payment_status || invoice.payment_status) },
			...(state.payment_gate ? [{ label: `${__("Payment Gate")}: ${gate.can_proceed ? __("Allowed") : __("Blocked")}`, status: gate.can_proceed ? "Allowed" : "Blocked", tone: gate.can_proceed ? "success" : "danger" }] : []),
		],
		message,
		sections: billingSections(state),
		actions: buttons,
	};
}

function openBilling(frm) {
	if (!frm || frm.is_new?.()) {
		frappe.msgprint(__("Save this document before billing."));
		return;
	}
	if (frm.is_dirty?.()) {
		frappe.msgprint(__("Please save or discard changes before opening billing and payment."));
		return;
	}
	const modal = presenter().open({
		title: __("Billing & Payment"),
		subtitle: `${frm.doc.doctype} ${frm.doc.name}`,
		size: "xl",
		loading: true,
		loadingMessage: __("Loading billing details..."),
	});
	let state = {};
	const refresh = async () => {
		modal.update({ loading: true, busy: false, error: "" });
		try {
			state = await call(API.state, sourceContext(frm));
			modal.update({ loading: false, busy: false, ...buildBillingSpec(frm, state, controller) });
		} catch (error) {
			modal.update({ loading: false, busy: false, error: error?.message || __("Unable to load billing details."), errorTitle: __("Billing Details Unavailable"), onRetry: refresh });
		}
	};
	const run = async (method, args, successMessage) => {
		modal.update({ busy: true, error: "" });
		try {
			const result = await call(method, args);
			state = result.state || state;
			await frm.reload_doc?.();
			modal.update({ busy: false, ...buildBillingSpec(frm, state, controller) });
			frappe.show_alert({ message: successMessage, indicator: "green" });
		} catch (error) {
			modal.update({ busy: false, error: error?.message || __("Billing action failed."), errorTitle: __("Billing action failed") });
		}
	};
	const controller = {
		invoice: () => run(API.invoice, sourceContext(frm), __("Invoice updated.")),
		submit: (invoiceName) => run(API.submit, { ...sourceContext(frm), invoice: invoiceName }, __("Invoice submitted.")),
		payment: (payable) => openPaymentModal(frm, state, payable, refresh),
	};
	refresh();
}

export function installVetEdgeBillingEdgeSuite() {
	if (installed) return true;
	if (!presenter()?.ready?.()) return false;
	window.vetedgeBillingModal = { open: openBilling };
	installed = true;
	return true;
}

if (typeof window !== "undefined") {
	window.installVetEdgeBillingEdgeSuite = installVetEdgeBillingEdgeSuite;
}
