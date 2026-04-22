from __future__ import annotations


def initiate(context) -> dict:
	"""
	ProcessEdge Core integration contract.

	VetEdge owns invoice access control and payment eligibility checks before
	delegating initiation to the shared ProcessEdge Core Payment layer. This
	module intentionally defines a stable handoff shape without embedding any
	provider-specific gateway behavior in VetEdge.

	Expected future handoff request:
	{
		"reference_doctype": "Sales Invoice",
		"reference_name": "<invoice>",
		"customer": "<customer>",
		"amount": <outstanding_amount>,
		"currency": "<currency>",
		"company": "<company>",
		"access_context": {...},
		"source_context": {...}
	}

	Expected future response:
	{
		"success": true,
		"action": "redirect" | "message",
		"payment_reference": "<core_intent_id>",
		"payment_status_snapshot": "initiated" | "pending" | "failed",
		"redirect_url": "<hosted_checkout_url>",
		"message": "<human_message>"
	}
	"""
	return {
		"success": True,
		"action": "message",
		"backend_mode": "processedge_core",
		"payment_provider": "processedge_core",
		"payment_reference": f"pecore::{context.invoice_name}",
		"payment_status_snapshot": "integration_pending",
		"message": "ProcessEdge Core payment backend is configured as the target, but the integration transport is not connected yet.",
		"creates_payment_entry": False,
		"backend_payload": {
			"backend_mode": "processedge_core",
			"request_contract": {
				"reference_doctype": context.reference_doctype,
				"reference_name": context.invoice_name,
				"customer": context.customer,
				"amount": context.amount,
				"currency": context.currency,
				"company": context.company,
				"access_context": context.access_context,
				"source_context": context.source_context,
			}
		},
	}


def get_payment_status(reference: str) -> dict:
	return {
		"reference": reference,
		"backend_mode": "processedge_core",
		"payment_status_snapshot": "integration_pending",
		"message": "ProcessEdge Core payment status polling is not connected yet.",
	}
