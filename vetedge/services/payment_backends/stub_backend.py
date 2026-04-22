from __future__ import annotations


def initiate(context) -> dict:
	return {
		"success": True,
		"action": "message",
		"backend_mode": "stub",
		"payment_provider": "stub",
		"payment_status_snapshot": "not_started",
		"message": "Payment ownership and eligibility are validated. Configure a real backend before collecting live payments.",
		"creates_payment_entry": False,
		"backend_payload": {
			"mode": "stub",
			"reference_doctype": context.reference_doctype,
			"reference_name": context.invoice_name,
			"source_context": context.source_context,
		},
	}


def get_payment_status(reference: str) -> dict:
	return {
		"reference": reference,
		"backend_mode": "stub",
		"payment_status_snapshot": "unknown",
		"message": "Stub backend does not track real payment status.",
	}
