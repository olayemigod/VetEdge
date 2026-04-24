window.vetedgeInvoiceSummary = {
	...(window.vetedgeInvoiceSummary || {}),
	open(invoiceName) {
		if (!invoiceName) {
			frappe.msgprint(__("No invoice is linked yet."));
			return;
		}

		frappe.call({
			method: "vetedge.services.billing.get_invoice_access_summary",
			args: { invoice: invoiceName },
			freeze: true,
			freeze_message: __("Loading invoice summary..."),
			callback: (result) => {
				const invoice = result.message;
				if (!invoice?.name) {
					return;
				}

				const dialog = new frappe.ui.Dialog({
					title: __("Invoice Summary"),
					fields: [
						{ fieldname: "summary_html", fieldtype: "HTML" },
					],
					primary_action_label: __("Close"),
					primary_action() {
						dialog.hide();
					},
				});

				dialog.fields_dict.summary_html.$wrapper.html(renderInvoiceSummary(invoice));
				dialog.fields_dict.summary_html.$wrapper.find(".vetedge-open-invoice-link").on("click", function (event) {
					event.preventDefault();
					event.stopPropagation();
					openInvoiceInNewTab($(this).attr("data-invoice-name"));
				});
				dialog.show();
			},
		});
	},

	openHistory(invoices) {
		const rows = (invoices || []).filter((row) => row?.name);
		if (!rows.length) {
			frappe.msgprint(__("No invoice is linked yet."));
			return;
		}

		const dialog = new frappe.ui.Dialog({
			title: __("Consultation Invoices"),
			fields: [{ fieldname: "history_html", fieldtype: "HTML" }],
			primary_action_label: __("Close"),
			primary_action() {
				dialog.hide();
			},
		});

		dialog.fields_dict.history_html.$wrapper.html(renderInvoiceHistory(rows));
		dialog.fields_dict.history_html.$wrapper.find("[data-invoice-name]").on("click", function () {
			const invoiceName = $(this).attr("data-invoice-name");
			dialog.hide();
			window.vetedgeInvoiceSummary.open(invoiceName);
		});
		dialog.show();
	},
};

function openInvoiceInNewTab(invoiceName) {
	const url = buildInvoiceUrl(invoiceName);
	const newTab = window.open("", "_blank", "noopener,noreferrer");
	if (newTab) {
		newTab.opener = null;
		newTab.location.replace(url);
		return;
	}
	window.location.href = url;
}

function buildInvoiceUrl(invoiceName) {
	const route = `/app/${frappe.router.slug("Sales Invoice")}/${encodeURIComponent(invoiceName)}`;
	return frappe.urllib.get_full_url(route);
}

function renderInvoiceSummary(invoice) {
	const currency = invoice.currency || frappe.defaults.get_default("currency");
	const total = format_currency(invoice.grand_total || 0, currency);
	const outstanding = format_currency(invoice.outstanding_amount || 0, currency);
	const postingDate = invoice.posting_date ? frappe.datetime.str_to_user(invoice.posting_date) : __("Unknown");
	const dueDate = invoice.due_date ? frappe.datetime.str_to_user(invoice.due_date) : __("Unknown");
	const invoiceUrl = invoice.name ? buildInvoiceUrl(invoice.name) : "";

	return `
		<div class="vetedge-invoice-summary">
			<div class="frappe-card p-3">
				<div class="small text-muted mb-2">${__("Invoice")}</div>
				<div class="h5 mb-1">${frappe.utils.escape_html(invoice.name)}</div>
				<div class="text-muted small mb-3">${frappe.utils.escape_html(invoice.customer || __("Unknown Customer"))}</div>
				<div class="row">
					<div class="col-sm-6 mb-3">
						<div class="small text-muted">${__("Status")}</div>
						<div class="indicator-pill ${getInvoiceSummaryPill(invoice.status)} mt-1">${__(invoice.status || "Unknown")}</div>
					</div>
					<div class="col-sm-6 mb-3">
						<div class="small text-muted">${__("Branch")}</div>
						<div class="mt-1">${frappe.utils.escape_html(invoice.branch || __("Not set"))}</div>
					</div>
					<div class="col-sm-6 mb-3">
						<div class="small text-muted">${__("Posting Date")}</div>
						<div class="mt-1">${postingDate}</div>
					</div>
					<div class="col-sm-6 mb-3">
						<div class="small text-muted">${__("Due Date")}</div>
						<div class="mt-1">${dueDate}</div>
					</div>
					<div class="col-sm-6 mb-3">
						<div class="small text-muted">${__("Grand Total")}</div>
						<div class="mt-1">${total}</div>
					</div>
					<div class="col-sm-6 mb-3">
						<div class="small text-muted">${__("Outstanding")}</div>
						<div class="mt-1">${outstanding}</div>
					</div>
				</div>
				${invoice.can_open_full_form
					? `
						<div class="mt-3">
							<a
								href="${frappe.utils.escape_html(invoiceUrl)}"
								target="_blank"
								rel="noopener noreferrer"
								class="btn btn-primary vetedge-open-invoice-link"
								data-invoice-name="${frappe.utils.escape_html(invoice.name)}"
							>
								${__("Open Invoice In New Tab")}
							</a>
						</div>
						<div class="text-muted small mt-2">${__("Use this link to keep the consultation open while reviewing the ERPNext invoice form.")}</div>
					`
					: `<div class="text-muted small">${__("This summary is available for operational review. Full ERPNext invoice form access is limited by finance permissions.")}</div>`}
			</div>
		</div>
	`;
}

function getInvoiceSummaryPill(status) {
	return {
		Draft: "gray",
		Submitted: "blue",
		Unpaid: "orange",
		"Partly Paid": "yellow",
		Paid: "green",
		Overdue: "red",
		Cancelled: "red",
		"Credit Note Issued": "purple",
		"Internal Transfer": "cyan",
	}[status] || "gray";
}

function renderInvoiceHistory(invoices) {
	return `
		<div class="vetedge-invoice-history">
			${invoices
				.map((invoice) => {
					const currency = invoice.currency || frappe.defaults.get_default("currency");
					const total = format_currency(invoice.grand_total || 0, currency);
					const outstanding = format_currency(invoice.outstanding_amount || 0, currency);
					const postingDate = invoice.posting_date ? frappe.datetime.str_to_user(invoice.posting_date) : __("Unknown");

					return `
						<div class="frappe-card p-3 mb-3" data-invoice-name="${frappe.utils.escape_html(invoice.name)}" style="cursor: pointer;">
							<div class="d-flex justify-content-between align-items-start gap-3">
								<div>
									<div class="small text-muted mb-1">${__("Invoice")}</div>
									<div class="h6 mb-1">${frappe.utils.escape_html(invoice.name)}</div>
									<div class="text-muted small">${postingDate}</div>
								</div>
								<div class="text-end">
									<div class="indicator-pill ${getInvoiceSummaryPill(invoice.status)}">${__(invoice.status || "Unknown")}</div>
									<div class="small text-muted mt-2">${__("Outstanding")}: ${outstanding}</div>
									<div class="small text-muted">${__("Total")}: ${total}</div>
								</div>
							</div>
						</div>
					`;
				})
				.join("")}
			<div class="text-muted small">${__("Click an invoice to review the summary and open the ERPNext form in a new tab.")}</div>
		</div>
	`;
}
