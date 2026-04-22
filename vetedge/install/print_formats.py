from __future__ import annotations

from textwrap import dedent

import frappe


OWNER_INVOICE_PRINT_FORMAT = "VetEdge Owner Invoice"


OWNER_INVOICE_TEMPLATE = dedent(
	"""
	{% set company_name = doc.company or frappe.db.get_value("Global Defaults", "Global Defaults", "default_company") %}
	{% set invoice_heading = doc.select_print_heading or "Sales Invoice" %}
	<div class="vetedge-invoice">
		{% if letter_head and not no_letterhead %}
		<div class="letter-head">{{ letter_head }}</div>
		{% endif %}
		<div class="invoice-header">
			<div>
				<div class="eyebrow">Veterinary Invoice</div>
				<h1>{{ company_name }}</h1>
				<p class="muted">{{ invoice_heading }}</p>
			</div>
			<div class="invoice-meta">
				<div><span>Invoice #</span><strong>{{ doc.name }}</strong></div>
				<div><span>Status</span><strong>{{ doc.status or "Draft" }}</strong></div>
				<div><span>Posting Date</span><strong>{{ doc.get_formatted("posting_date") }}</strong></div>
				{% if doc.due_date %}
				<div><span>Due Date</span><strong>{{ doc.get_formatted("due_date") }}</strong></div>
				{% endif %}
			</div>
		</div>

		<div class="invoice-grid">
			<div class="info-card">
				<div class="section-label">Bill To</div>
				<h3>{{ doc.customer_name or doc.customer }}</h3>
				{% if doc.address_display %}
				<div class="muted">{{ doc.address_display }}</div>
				{% endif %}
				{% if doc.contact_mobile or doc.contact_phone %}
				<div class="muted">{{ doc.contact_mobile or doc.contact_phone }}</div>
				{% endif %}
				{% if doc.contact_email %}
				<div class="muted">{{ doc.contact_email }}</div>
				{% endif %}
			</div>

			<div class="info-card">
				<div class="section-label">Clinic</div>
				<h3>{{ company_name }}</h3>
				{% if doc.company_address_display %}
				<div class="muted">{{ doc.company_address_display }}</div>
				{% endif %}
				{% if doc.branch %}
				<div class="muted"><strong>Branch:</strong> {{ doc.branch }}</div>
				{% endif %}
			</div>
		</div>

		<table class="invoice-table">
			<thead>
				<tr>
					<th>#</th>
					<th>Description</th>
					<th class="text-right">Qty</th>
					<th class="text-right">Rate</th>
					<th class="text-right">Amount</th>
				</tr>
			</thead>
			<tbody>
				{% for item in doc.items %}
				<tr>
					<td>{{ item.idx }}</td>
					<td>
						<div class="item-name">{{ item.item_name or item.item_code }}</div>
						{% if item.description and item.description != item.item_name %}
						<div class="item-description">{{ item.description }}</div>
						{% endif %}
					</td>
					<td class="text-right">{{ item.get_formatted("qty", doc) }}</td>
					<td class="text-right">{{ item.get_formatted("rate", doc) }}</td>
					<td class="text-right">{{ item.get_formatted("amount", doc) }}</td>
				</tr>
				{% endfor %}
			</tbody>
		</table>

		<div class="totals-wrap">
			<div class="totals-card">
				<div class="total-row"><span>Subtotal</span><strong>{{ doc.get_formatted("total", doc) }}</strong></div>
				{% if doc.discount_amount %}
				<div class="total-row"><span>Discount</span><strong>{{ doc.get_formatted("discount_amount", doc) }}</strong></div>
				{% endif %}
				{% if doc.total_taxes_and_charges %}
				<div class="total-row"><span>Taxes & Charges</span><strong>{{ doc.get_formatted("total_taxes_and_charges", doc) }}</strong></div>
				{% endif %}
				<div class="total-row grand-total"><span>Grand Total</span><strong>{{ doc.get_formatted("grand_total", doc) }}</strong></div>
				<div class="total-row balance"><span>Outstanding</span><strong>{{ doc.get_formatted("outstanding_amount", doc) }}</strong></div>
			</div>
		</div>

		{% if doc.remarks %}
		<div class="notes-card">
			<div class="section-label">Notes</div>
			<div class="muted">{{ doc.remarks }}</div>
		</div>
		{% endif %}
	</div>
	"""
).strip()


OWNER_INVOICE_CSS = dedent(
	"""
	.vetedge-invoice {
		font-family: "DejaVu Sans", Arial, sans-serif;
		color: #1f2937;
		font-size: 11px;
	}

	.vetedge-invoice .letter-head {
		margin-bottom: 18px;
	}

	.vetedge-invoice .eyebrow {
		color: #0f766e;
		font-size: 11px;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		margin-bottom: 6px;
	}

	.vetedge-invoice h1,
	.vetedge-invoice h3,
	.vetedge-invoice p {
		margin: 0;
	}

	.vetedge-invoice h1 {
		font-size: 24px;
		line-height: 1.2;
		margin-bottom: 4px;
	}

	.vetedge-invoice .invoice-header {
		border-bottom: 2px solid #0f766e;
		padding-bottom: 18px;
		margin-bottom: 18px;
		display: table;
		width: 100%;
	}

	.vetedge-invoice .invoice-header > div {
		display: table-cell;
		vertical-align: top;
	}

	.vetedge-invoice .invoice-meta {
		text-align: right;
		width: 34%;
	}

	.vetedge-invoice .invoice-meta div {
		margin-bottom: 8px;
	}

	.vetedge-invoice .invoice-meta span,
	.vetedge-invoice .section-label,
	.vetedge-invoice .muted {
		color: #6b7280;
	}

	.vetedge-invoice .invoice-meta span,
	.vetedge-invoice .section-label {
		display: block;
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		margin-bottom: 3px;
	}

	.vetedge-invoice .invoice-grid {
		display: table;
		width: 100%;
		margin-bottom: 22px;
	}

	.vetedge-invoice .info-card {
		display: table-cell;
		width: 50%;
		vertical-align: top;
		background: #f8fafc;
		border: 1px solid #e5e7eb;
		border-radius: 10px;
		padding: 14px 16px;
	}

	.vetedge-invoice .info-card:first-child {
		padding-right: 18px;
	}

	.vetedge-invoice .invoice-table {
		width: 100%;
		border-collapse: collapse;
		margin-bottom: 22px;
	}

	.vetedge-invoice .invoice-table th {
		background: #ecfeff;
		border-bottom: 1px solid #99f6e4;
		color: #134e4a;
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.04em;
		padding: 10px 8px;
		text-transform: uppercase;
	}

	.vetedge-invoice .invoice-table td {
		border-bottom: 1px solid #e5e7eb;
		padding: 10px 8px;
		vertical-align: top;
	}

	.vetedge-invoice .item-name {
		font-weight: 700;
		margin-bottom: 4px;
	}

	.vetedge-invoice .item-description {
		color: #6b7280;
		white-space: pre-wrap;
	}

	.vetedge-invoice .text-right {
		text-align: right;
	}

	.vetedge-invoice .totals-wrap {
		display: table;
		width: 100%;
	}

	.vetedge-invoice .totals-card {
		display: table;
		margin-left: auto;
		min-width: 280px;
		border: 1px solid #d1fae5;
		background: #f0fdf4;
		border-radius: 12px;
		padding: 14px 16px;
	}

	.vetedge-invoice .total-row {
		display: table-row;
	}

	.vetedge-invoice .total-row span,
	.vetedge-invoice .total-row strong {
		display: table-cell;
		padding: 5px 0;
	}

	.vetedge-invoice .total-row strong {
		text-align: right;
		padding-left: 20px;
	}

	.vetedge-invoice .grand-total strong,
	.vetedge-invoice .balance strong {
		color: #065f46;
	}

	.vetedge-invoice .notes-card {
		margin-top: 22px;
		border-top: 1px solid #e5e7eb;
		padding-top: 16px;
	}
	"""
).strip()


def ensure_print_formats() -> None:
	if not frappe.db.exists("DocType", "Print Format"):
		return

	values = {
		"doctype": "Print Format",
		"name": OWNER_INVOICE_PRINT_FORMAT,
		"print_format_for": "DocType",
		"doc_type": "Sales Invoice",
		"module": "Veterinary",
		"standard": "No",
		"disabled": 0,
		"custom_format": 1,
		"print_format_type": "Jinja",
		"pdf_generator": "chrome",
		"margin_top": 10,
		"margin_bottom": 10,
		"margin_left": 10,
		"margin_right": 10,
		"page_number": "Bottom Right",
		"html": OWNER_INVOICE_TEMPLATE,
		"css": OWNER_INVOICE_CSS,
	}

	if frappe.db.exists("Print Format", OWNER_INVOICE_PRINT_FORMAT):
		doc = frappe.get_doc("Print Format", OWNER_INVOICE_PRINT_FORMAT)
		changed = False
		for fieldname, value in values.items():
			if fieldname == "doctype":
				continue
			if doc.get(fieldname) != value:
				doc.set(fieldname, value)
				changed = True
		if changed:
			doc.save(ignore_permissions=True)
		return

	frappe.get_doc(values).insert(ignore_permissions=True)
