(function () {
	"use strict";

	if (window.__vetedgeSharedBillingEdgeSuiteInstalled) return;
	window.__vetedgeSharedBillingEdgeSuiteInstalled = true;

	const API = Object.freeze({
		state: "vetedge.services.billing_modal.get_billing_modal_state",
		invoice: "vetedge.services.billing_modal.create_or_update_modal_invoice",
		submit: "vetedge.services.billing_modal.submit_modal_invoice",
		payment: "vetedge.services.billing_modal.record_modal_invoice_payment",
	});

	const call = (method, args = {}) => frappe.call({ method, args }).then((response) => response.message || {});
	const money = (value, currency) => format_currency(Number(value || 0), currency || frappe.defaults.get_default("currency"));
	const invoiceName = (row) => String(row?.name || row?.invoice || "");

	function ensurePresenter() {
		return new Promise((resolve, reject) => {
			if (window.VetEdgeEdgeModalPresenter?.ready?.()) {
				resolve(window.VetEdgeEdgeModalPresenter);
				return;
			}
			frappe.require("vetedge_edge_modal_presenter.bundle.js", () => {
				if (window.VetEdgeEdgeModalPresenter?.ready?.()) resolve(window.VetEdgeEdgeModalPresenter);
				else reject(new Error(__("The EdgeSuite billing modal runtime is unavailable.")));
			});
		});
	}

	function billingContext(frm) {
		return { source_doctype: frm.doc.doctype, source_name: frm.doc.name };
	}

	function invoiceStatus(row) {
		if (!row) return "Not Billed";
		return row.payment_status || row.payment_state || row.status || (Number(row.docstatus) === 0 ? "Draft" : Number(row.docstatus) === 1 ? "Submitted" : "Cancelled");
	}

	function openInvoice(name) {
		if (!name) return;
		window.location.assign(`/desk/sales-invoice/${encodeURIComponent(name)}`);
	}

	function accountSearch(query) {
		return frappe.call("frappe.desk.search.search_link", {
			doctype: "Account",
			txt: String(query || ""),
			page_length: 20,
			ignore_user_permissions: 0,
		}).then((response) => response.message || []);
	}

	function invoiceRows(state) {
		const history = state.invoice_history || state.billing_group_invoice_history || state.billing_session?.invoices || state.billing_session?.invoice_ledger?.invoices || [];
		return history;
	}

	function invoiceSection(state, actions) {
		const rows = invoiceRows(state);
		return {
			title: __("Linked Invoice History"),
			message: __("Each action belongs to the invoice on the same row."),
			columns: [
				{ fieldname: "name", label: __("Invoice") },
				{ fieldname: "display_status", label: __("Status"), fieldtype: "Status" },
				{ fieldname: "posting_date", label: __("Posting Date") },
				{ fieldname: "grand_total_display", label: __("Total") },
				{ fieldname: "paid_display", label: __("Paid") },
				{ fieldname: "outstanding_display", label: __("Outstanding") },
			],
			rows: rows.map((row) => ({
				...row,
				name: invoiceName(row),
				display_status: invoiceStatus(row),
				grand_total_display: money(row.grand_total || row.rounded_total, row.currency || state.currency),
				paid_display: money(row.paid_amount, row.currency || state.currency),
				outstanding_display: money(row.outstanding_amount, row.currency || state.currency),
			})),
			rowKey: "name",
			rowActions: rows.map((row) => {
				const name = invoiceName(row);
				const rowActions = [{ label: __("Open"), onClick: () => openInvoice(name) }];
				if (row.can_submit_invoice) rowActions.push({ label: __("Submit Invoice"), primary: true, onClick: () => actions.submit(name) });
				if (row.can_pay_outstanding || row.can_pay) rowActions.push({ label: __(row.action_label || "Pay Outstanding"), primary: true, onClick: () => actions.pay(row) });
				return { key: name, row, actions: rowActions };
			}),
			emptyTitle: __("No linked invoices"),
		};
	}

	function ownerOutstandingSection(state, actions) {
		const rows = state.patient_outstanding_context || [];
		return {
			title: __(state.outstanding_context_label || "Other Outstanding Invoices for this Owner"),
			message: __(state.outstanding_context_message || "These invoices belong to the same Pet Owner/Customer but are outside the current billing cycle."),
			columns: [
				{ fieldname: "name", label: __("Invoice") },
				{ fieldname: "patient_name", label: __("Patient") },
				{ fieldname: "display_status", label: __("Status"), fieldtype: "Status" },
				{ fieldname: "grand_total_display", label: __("Total") },
				{ fieldname: "paid_display", label: __("Paid") },
				{ fieldname: "outstanding_display", label: __("Outstanding") },
			],
			rows: rows.map((row) => ({
				...row,
				name: invoiceName(row),
				patient_name: row.patient_name || row.patient || __("Owner-level / Unlinked"),
				display_status: invoiceStatus(row),
				grand_total_display: money(row.grand_total || row.rounded_total, row.currency || state.currency),
				paid_display: money(row.paid_amount, row.currency || state.currency),
				outstanding_display: money(row.outstanding_amount, row.currency || state.currency),
			})),
			rowKey: "name",
			rowActions: rows.map((row) => {
				const name = invoiceName(row);
				const rowActions = [{ label: __("Open"), onClick: () => openInvoice(name) }];
				if (row.can_submit_invoice) rowActions.push({ label: __("Submit Invoice"), primary: true, onClick: () => actions.submit(name) });
				if (row.can_pay_outstanding || row.can_pay) rowActions.push({ label: __(row.action_label || "Pay Outstanding"), primary: true, onClick: () => actions.pay(row) });
				return { key: name, row, actions: rowActions };
			}),
			emptyTitle: __("No other owner invoices"),
		};
	}

	function lineItemSection(state) {
		const invoice = state.invoice || {};
		const rows = invoice.items || [];
		return {
			title: __("Invoice Line Items"),
			columns: [
				{ fieldname: "item", label: __("Item / Service") },
				{ fieldname: "qty", label: __("Qty") },
				{ fieldname: "rate_display", label: __("Rate") },
				{ fieldname: "amount_display", label: __("Amount") },
			],
			rows: rows.map((row, index) => ({
				name: row.name || `${row.item_code || "item"}-${index}`,
				item: row.item_name || row.item_code,
				qty: row.qty,
				rate_display: money(row.rate, invoice.currency || state.currency),
				amount_display: money(row.amount, invoice.currency || state.currency),
			})),
			rowKey: "name",
			emptyTitle: __("No invoice line items"),
		};
	}

	async function openSharedBilling(frm) {
		if (!frm || frm.is_new?.()) {
			frappe.msgprint(__("Save this document before billing."));
			return;
		}
		if (frm.is_dirty?.()) {
			frappe.msgprint(__("Please save or discard changes before opening Billing & Payment."));
			return;
		}
		const presenter = await ensurePresenter();
		const ctx = billingContext(frm);
		const modal = presenter.open({ title: __("Billing & Payment"), subtitle: `${frm.doc.doctype} ${frm.doc.name}`, size: "xl", loading: true, loadingMessage: __("Loading billing details...") });
		let state = {};

		const reloadSource = async () => {
			try { await frm.reload_doc?.(); } catch (_error) { /* synthetic frames may not require a form reload */ }
		};

		const refresh = async () => {
			modal.update({ loading: true, busy: false, error: "" });
			try {
				state = await call(API.state, ctx);
				paint();
			} catch (error) {
				modal.update({ loading: false, busy: false, error: error?.message || __("Billing details could not be loaded."), errorTitle: __("Billing unavailable"), onRetry: refresh });
			}
		};

		const run = async (method, args, success) => {
			modal.update({ busy: true, error: "" });
			try {
				const result = await call(method, args);
				state = result.state || state;
				await reloadSource();
				frappe.show_alert({ message: success, indicator: "green" });
				paint();
			} catch (error) {
				modal.update({ busy: false, error: error?.message || __("The billing action could not be completed."), errorTitle: __("Billing action failed") });
			}
		};

		const submit = (invoice) => run(API.submit, { ...ctx, invoice }, __("Invoice submitted."));

		const pay = async (selected) => {
			const invoice = selected || state.invoice;
			if (!invoiceName(invoice)) return;
			const modes = (state.payment_modes || []).map((value) => ({ value: String(value), label: String(value) }));
			const payment = presenter.open({
				title: __("Record Payment"),
				subtitle: invoiceName(invoice),
				size: "md",
				message: __("Payment will be allocated to the selected invoice. The server rechecks Payment Entry permission and invoice outstanding balance before submission."),
				fields: [
					{ fieldname: "invoice", label: __("Invoice"), type: "text", readOnly: true, default: invoiceName(invoice) },
					{ fieldname: "amount", label: __("Amount"), type: "number", min: 0.01, step: "0.01", required: true, default: Number(invoice.outstanding_amount || 0) },
					{ fieldname: "mode_of_payment", label: __("Mode of Payment"), type: "select", options: modes, required: true, default: modes[0]?.value || "" },
					{ fieldname: "paid_to", label: __("Paid To Account"), type: "link", searcher: accountSearch, placeholder: __("Search Account") },
					{ fieldname: "posting_date", label: __("Posting Date"), type: "date", required: true, default: frappe.datetime.now_date() },
					{ fieldname: "reference_no", label: __("Reference Number"), type: "text", default: "" },
					{ fieldname: "reference_date", label: __("Reference Date"), type: "date", default: "" },
					{ fieldname: "remarks", label: __("Remarks"), type: "textarea", rows: 3, default: "" },
				],
				values: {
					invoice: invoiceName(invoice), amount: Number(invoice.outstanding_amount || 0), mode_of_payment: modes[0]?.value || "", paid_to: "", posting_date: frappe.datetime.now_date(), reference_no: "", reference_date: "", remarks: "",
				},
				actions: [{
					label: __("Submit Payment"), primary: true, closeOnSuccess: false,
					async onClick(values) {
						if (!(Number(values.amount) > 0)) {
							payment.update({ error: __("Payment Amount must be greater than zero."), errorTitle: __("Invalid payment") });
							return;
						}
						payment.update({ busy: true, error: "" });
						try {
							const result = await call(API.payment, { ...ctx, invoice: invoiceName(invoice), amount: values.amount, mode_of_payment: values.mode_of_payment, paid_to: values.paid_to, posting_date: values.posting_date, reference_no: values.reference_no, reference_date: values.reference_date, remarks: values.remarks });
							state = result.state || state;
							await reloadSource();
							payment.update({ busy: false });
							payment.close();
							frappe.show_alert({ message: __("Payment recorded."), indicator: "green" });
							paint();
						} catch (error) {
							payment.update({ busy: false, error: error?.message || __("Payment could not be recorded."), errorTitle: __("Payment failed") });
						}
					},
				}],
			});
		};

		function paint() {
			const source = state.source || {};
			const invoice = state.invoice || {};
			const actions = state.actions || {};
			const currency = state.currency || invoice.currency;
			const sections = [];
			if (invoiceRows(state).length) sections.push(invoiceSection(state, { submit, pay }));
			if ((state.patient_outstanding_context || []).length) sections.push(ownerOutstandingSection(state, { submit, pay }));
			if ((invoice.items || []).length) sections.push(lineItemSection(state));
			const gate = state.payment_gate || state.billing_session?.payment_gate || {};
			sections.push({
				title: __("Workflow / Payment Gate"),
				message: gate.message || (gate.gate ? `${gate.gate}: ${gate.can_proceed ? __("Allowed") : __("Blocked")}` : __("No additional payment gate applies to this service.")),
			});
			const footerActions = [];
			if (actions.can_create_or_update_invoice) footerActions.push({ label: __(actions.invoice_action_label || "Create / Update Invoice"), primary: true, closeOnSuccess: false, onClick: () => run(API.invoice, ctx, __("Invoice updated.")) });
			if (actions.can_submit_invoice) footerActions.push({ label: __("Submit Invoice"), primary: true, closeOnSuccess: false, onClick: () => submit(actions.open_invoice_name || state.open_invoice_name || invoice.name) });
			if (actions.can_record_payment) footerActions.push({ label: __("Record Payment"), primary: true, closeOnSuccess: false, onClick: () => pay(invoice) });
			footerActions.push({ label: __("Refresh Status"), closeOnSuccess: false, onClick: refresh });
			modal.update({
				loading: false,
				busy: false,
				title: __("Billing & Payment"),
				subtitle: `${source.patient_name || source.patient || source.name || frm.doc.name} · ${source.owner_name || source.owner || ""}`,
				badges: [
					{ label: state.payment_status || invoiceStatus(invoice), status: state.payment_status || invoiceStatus(invoice) },
					...(state.billing_session_status ? [{ label: state.billing_session_status, status: state.billing_session_status }] : []),
				],
				metrics: [
					{ label: __("Service / Source"), value: source.doctype || frm.doc.doctype, helper: source.status || "" },
					{ label: __("Total"), value: money(state.total_amount ?? invoice.grand_total, currency), helper: `${state.linked_invoice_count || invoiceRows(state).length || (invoice.name ? 1 : 0)} ${__("invoice(s)")}` },
					{ label: __("Paid"), value: money(state.paid_amount ?? invoice.paid_amount, currency) },
					{ label: __("Outstanding"), value: money(state.outstanding_amount ?? invoice.outstanding_amount, currency) },
				],
				message: source.service_branch ? `${__("Branch")}: ${source.service_branch}` : "",
				sections,
				actions: footerActions,
			});
		}

		await refresh();
		return modal;
	}

	const legacy = window.vetedgeBillingModal;
	window.vetedgeBillingModal = {
		__sharedEdgeSuiteBilling: true,
		open(frm) {
			return openSharedBilling(frm).catch((error) => {
				console.error("Shared EdgeSuite billing modal failed", error);
				if (legacy?.open) return legacy.open(frm);
				frappe.msgprint(error?.message || __("Billing & Payment is unavailable."));
			});
		},
	};
})();
