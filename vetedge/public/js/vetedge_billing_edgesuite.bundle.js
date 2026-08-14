const API = Object.freeze({
	state: "vetedge.services.billing_modal.get_billing_modal_state",
	invoice: "vetedge.services.billing_modal.create_or_update_modal_invoice",
	submit: "vetedge.services.billing_modal.submit_modal_invoice",
	payment: "vetedge.services.billing_modal.record_modal_invoice_payment",
});

let installed = false;
const presenter = () => window.VetEdgeEdgeModalPresenter;
const call = (method, args = {}) => frappe.call({ method, args }).then((response) => response.message || {});
const sourceContext = (frm) => ({ source_doctype: frm.doc.doctype, source_name: frm.doc.name });

function money(value, currency) {
	const code = currency || frappe.boot?.sysdefaults?.currency || frappe.defaults?.get_default?.("currency") || "NGN";
	try {
		return new Intl.NumberFormat(undefined, { style: "currency", currency: code }).format(Number(value || 0));
	} catch (_error) {
		return `${code} ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
	}
}

function invoiceStatus(invoice = {}) {
	if (!invoice.name) return __("No Invoice");
	if (Number(invoice.docstatus) === 0) return __("Draft");
	if (Number(invoice.docstatus) === 2) return __("Cancelled");
	return invoice.payment_status || invoice.status || __("Submitted");
}

function tone(value) {
	const text = String(value || "").toLowerCase();
	if (["paid", "submitted", "allowed", "completed", "closed"].some((token) => text.includes(token))) return "success";
	if (["blocked", "cancelled", "overdue", "failed"].some((token) => text.includes(token))) return "danger";
	if (["draft", "open", "unpaid", "partly", "pending"].some((token) => text.includes(token))) return "warning";
	return "neutral";
}

const historyRows = (state = {}) => state.invoice_history || state.billing_group_invoice_history || state.billing_session?.invoices || [];

function payableRows(state = {}) {
	const rows = historyRows(state).filter((row) => (row.can_pay_outstanding || row.can_pay) && Number(row.outstanding_amount || 0) > 0);
	const current = state.invoice;
	const currentCanPay = Boolean(state.actions?.can_record_payment || current?.can_pay_outstanding || current?.can_pay);
	if (current?.name && Number(current.docstatus) === 1 && Number(current.outstanding_amount || 0) > 0 && currentCanPay && !rows.some((row) => (row.name || row.invoice) === current.name)) rows.unshift(current);
	return rows;
}

function metrics(state = {}) {
	const currency = state.currency || state.invoice?.currency || state.billing_session?.currency;
	const outstanding = state.billing_session_outstanding ?? state.outstanding_amount ?? 0;
	return [
		{ label: __("Billing Cycle Total"), value: money(state.billing_session_total ?? state.total_amount, currency), tone: "primary" },
		{ label: __("Total Paid"), value: money(state.billing_session_paid ?? state.paid_amount, currency), tone: "success" },
		{ label: __("Total Outstanding"), value: money(outstanding, currency), tone: Number(outstanding) > 0 ? "warning" : "success" },
		{ label: __("Linked Invoices"), value: Number(state.linked_invoice_count || historyRows(state).length || 0), tone: "info" },
	];
}

function sourceMetrics(state = {}) {
	const source = state.source || {};
	return [
		{ label: __("Patient"), value: source.patient_name || source.patient || "—" },
		{ label: __("Owner / Customer"), value: source.owner_name || source.owner || "—" },
		{ label: __("Branch"), value: source.service_branch || source.branch || "—" },
		{ label: __("Company"), value: source.company || "—" },
	];
}

function openInvoice(invoice) {
	if (invoice) frappe.set_route("Form", "Sales Invoice", invoice);
}

function invoiceActionGroups(state, rows, controller) {
	const currentName = state.invoice?.name || "";
	return (rows || []).filter((row) => row?.name || row?.invoice).map((row) => {
		const invoiceName = row.name || row.invoice;
		const current = invoiceName === currentName;
		const canSubmit = Boolean(row.can_submit_invoice || (current && state.actions?.can_submit_invoice));
		const canPay = Number(row.outstanding_amount || 0) > 0 && Boolean(row.can_pay_outstanding || row.can_pay || (current && state.actions?.can_record_payment));
		const actions = [
			{ label: __("Open Invoice"), onClick: () => openInvoice(invoiceName) },
		];
		if (canSubmit) actions.push({ label: __("Submit Invoice"), primary: true, onClick: () => controller.submit(invoiceName) });
		if (canPay) actions.push({ label: __(row.action_label || "Pay Outstanding"), primary: true, onClick: () => controller.payment(row) });
		return {
			key: invoiceName,
			label: invoiceName,
			helper: `${invoiceStatus(row)} · ${money(row.outstanding_amount, row.currency)} ${__("outstanding")}`,
			row,
			actions,
		};
	});
}

function sections(state = {}, controller) {
	const invoice = state.invoice || {};
	const result = [{ title: __("Source Summary"), metrics: sourceMetrics(state) }];
	if (invoice.name) result.push({
		title: __("Current Invoice Items"),
		message: `${invoice.name} · ${invoiceStatus(invoice)}`,
		columns: [
			{ fieldname: "item_code", label: __("Item") },
			{ fieldname: "item_name", label: __("Description") },
			{ fieldname: "qty", label: __("Qty") },
			{ fieldname: "rate", label: __("Rate") },
			{ fieldname: "amount", label: __("Amount") },
		],
		rows: (invoice.items || []).map((row, index) => ({ name: `${invoice.name}-${index + 1}`, item_code: row.item_code || "", item_name: row.item_name || row.description || row.item_code || "", qty: Number(row.qty || 0), rate: money(row.rate, invoice.currency), amount: money(row.amount, invoice.currency) })),
		rowKey: "name",
		emptyTitle: __("No invoice items"),
	});
	const linkedRows = historyRows(state);
	result.push({
		title: __("Linked Invoice History"),
		message: __("All invoices in this VetEdge billing cycle are shown here. Invoice actions are available immediately below the table."),
		columns: [
			{ fieldname: "name", label: __("Invoice") },
			{ fieldname: "status", label: __("Status"), fieldtype: "Status" },
			{ fieldname: "posting_date", label: __("Posting Date"), fieldtype: "Date" },
			{ fieldname: "grand_total", label: __("Grand Total") },
			{ fieldname: "paid_amount", label: __("Paid") },
			{ fieldname: "outstanding_amount", label: __("Outstanding") },
		],
		rows: linkedRows.map((row) => ({ name: row.name || row.invoice, status: row.payment_status || row.status || (Number(row.docstatus) === 0 ? __("Draft") : __("Submitted")), posting_date: row.posting_date || "", grand_total: money(row.grand_total || row.rounded_total, row.currency), paid_amount: money(row.paid_amount, row.currency), outstanding_amount: money(row.outstanding_amount, row.currency) })),
		rowKey: "name",
		onRowClick: (row) => openInvoice(row?.name),
		rowActions: invoiceActionGroups(state, linkedRows, controller),
		emptyTitle: __("No linked invoices"),
	});
	const patientRows = state.patient_outstanding_context || [];
	const otherOutstanding = patientRows.map((row) => ({ name: row.name || row.invoice, posting_date: row.posting_date || "", outstanding_amount: money(row.outstanding_amount, row.currency), status: row.payment_status || row.status || __("Outstanding") }));
	if (otherOutstanding.length) result.push({
		title: __("Patient Outstanding Context"),
		message: __("Other patient invoices are shown for context and are not merged into the current billing cycle. Available invoice actions are shown below."),
		columns: [
			{ fieldname: "name", label: __("Invoice") },
			{ fieldname: "posting_date", label: __("Posting Date"), fieldtype: "Date" },
			{ fieldname: "outstanding_amount", label: __("Outstanding") },
			{ fieldname: "status", label: __("Status"), fieldtype: "Status" },
		],
		rows: otherOutstanding,
		rowKey: "name",
		onRowClick: (row) => openInvoice(row?.name),
		rowActions: invoiceActionGroups(state, patientRows, controller),
	});
	return result;
}

function paymentFields(state, invoice) {
	const payable = payableRows(state);
	return [
		{
			fieldname: "invoice", label: __("Invoice"), type: "select", required: true,
			options: payable.map((row) => ({ value: row.name || row.invoice, label: `${row.name || row.invoice} · ${money(row.outstanding_amount, row.currency)}` })),
			default: invoice.name || invoice.invoice,
			onChange(value, values, modalView) {
				const selected = payable.find((row) => (row.name || row.invoice) === value);
				if (selected) modalView.update({ values: { ...values, invoice: value, amount: selected.outstanding_amount || 0 } });
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

function openPayment(frm, state, invoice, returnToBilling) {
	const view = presenter().open({
		title: __("Record Payment"), subtitle: __("Select a payable invoice in the current billing cycle."), size: "md",
		fields: paymentFields(state, invoice),
		values: { invoice: invoice.name || invoice.invoice, amount: invoice.outstanding_amount || 0, mode_of_payment: state.payment_modes?.[0] || "", posting_date: frappe.datetime?.get_today?.() || "" },
		actions: [{ label: __("Submit Payment"), primary: true, async onClick(values) {
			view.update({ busy: true, error: "" });
			try {
				await call(API.payment, { ...sourceContext(frm), ...values });
				frappe.show_alert({ message: __("Payment recorded."), indicator: "green" });
				await frm.reload_doc?.();
				await returnToBilling();
			} catch (error) {
				view.update({ busy: false, error: error?.message || __("Payment could not be recorded."), errorTitle: __("Payment failed") });
			}
		} }],
	});
}

function buildSpec(frm, state, controller) {
	const invoice = state.invoice || {};
	const actions = state.actions || {};
	const gate = state.payment_gate || {};
	const buttons = [];
	if (actions.can_create_or_update_invoice || actions.can_create_invoice) buttons.push({ label: actions.invoice_action_label || (invoice.name ? __("Update Draft Invoice") : __("Create Invoice")), primary: true, onClick: controller.invoice });
	if (actions.can_submit_invoice && invoice.name) buttons.push({ label: __("Submit Invoice"), primary: true, onClick: () => controller.submit(invoice.name) });
	const payable = payableRows(state)[0];
	if (payable) buttons.push({ label: __("Pay Outstanding"), primary: true, onClick: () => controller.payment(payable) });
	const openName = actions.open_invoice_name || state.open_invoice_name || invoice.name;
	if (openName) buttons.push({ label: actions.open_invoice_label || __("Open Invoice"), onClick: () => openInvoice(openName) });
	return {
		title: __("Billing & Payment"), subtitle: `${state.source?.doctype || frm.doc.doctype} ${state.source?.name || frm.doc.name}`, size: "xl",
		metrics: metrics(state),
		badges: [
			{ label: `${__("Invoice Status")}: ${invoiceStatus(invoice)}`, status: invoiceStatus(invoice), tone: tone(invoiceStatus(invoice)) },
			{ label: `${__("Payment Status")}: ${state.payment_status || invoice.payment_status || __("Not Billed")}`, status: state.payment_status || invoice.payment_status, tone: tone(state.payment_status || invoice.payment_status) },
			...(state.payment_gate ? [{ label: `${__("Payment Gate")}: ${gate.can_proceed ? __("Allowed") : __("Blocked")}`, status: gate.can_proceed ? "Allowed" : "Blocked", tone: gate.can_proceed ? "success" : "danger" }] : []),
		],
		message: gate.message || state.billing_session?.session_warning || "",
		sections: sections(state, controller), actions: buttons,
	};
}

function openBilling(frm) {
	if (!frm || frm.is_new?.()) return frappe.msgprint(__("Save this document before billing."));
	if (frm.is_dirty?.()) return frappe.msgprint(__("Please save or discard changes before opening billing and payment."));
	const modal = presenter().open({ title: __("Billing & Payment"), subtitle: `${frm.doc.doctype} ${frm.doc.name}`, size: "xl", loading: true, loadingMessage: __("Loading billing details...") });
	let state = {};
	let controller;
	const refresh = async () => {
		modal.update({ loading: true, busy: false, error: "" });
		try {
			state = await call(API.state, sourceContext(frm));
			modal.update({ loading: false, busy: false, ...buildSpec(frm, state, controller) });
		} catch (error) {
			modal.update({ loading: false, busy: false, error: error?.message || __("Unable to load billing details."), errorTitle: __("Billing Details Unavailable"), onRetry: refresh });
		}
	};
	const run = async (method, args, message) => {
		modal.update({ busy: true, error: "" });
		try {
			const result = await call(method, args);
			state = result.state || state;
			await frm.reload_doc?.();
			modal.update({ busy: false, ...buildSpec(frm, state, controller) });
			frappe.show_alert({ message, indicator: "green" });
		} catch (error) {
			modal.update({ busy: false, error: error?.message || __("Billing action failed."), errorTitle: __("Billing action failed") });
		}
	};
	controller = {
		invoice: () => run(API.invoice, sourceContext(frm), __("Invoice updated.")),
		submit: (invoice) => run(API.submit, { ...sourceContext(frm), invoice }, __("Invoice submitted.")),
		payment: (invoice) => openPayment(frm, state, invoice, refresh),
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

if (typeof window !== "undefined") window.installVetEdgeBillingEdgeSuite = installVetEdgeBillingEdgeSuite;
