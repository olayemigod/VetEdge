from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from vetedge.services import coreedge_context_reconciliation

ROOT = Path(__file__).resolve().parents[1]


def test_vetedge_normalizer_derives_company_from_accounting_mapping():
	with (
		patch.object(
			coreedge_context_reconciliation,
			"_get_branch_rows",
			return_value=[
				{
					"name": "Main Vet Branch",
					"cost_center": "Main Vet - VE",
					"vetedge_cost_center": "",
					"warehouse": "",
					"vetedge_dispensary_warehouse": "",
				}
			],
		),
		patch.object(
			coreedge_context_reconciliation.frappe.db,
			"get_value",
			return_value="Vet Company",
		),
	):
		rows = coreedge_context_reconciliation.get_context_reconciliation_rows(
			branch_names=["Main Vet Branch"]
		)

	assert rows[0]["local_doctype"] == "Branch"
	assert rows[0]["local_name"] == "Main Vet Branch"
	assert rows[0]["company"] == "Vet Company"
	assert rows[0]["normalization_issue"] == ""


def test_vetedge_normalizer_flags_conflicting_company_evidence():
	def get_value(doctype, name, fieldname):
		return "Vet Company A" if doctype == "Cost Center" else "Vet Company B"

	with (
		patch.object(
			coreedge_context_reconciliation,
			"_get_branch_rows",
			return_value=[
				{
					"name": "Main Vet Branch",
					"cost_center": "Main Vet - A",
					"warehouse": "Main Vet Store - B",
				}
			],
		),
		patch.object(coreedge_context_reconciliation.frappe.db, "get_value", side_effect=get_value),
	):
		rows = coreedge_context_reconciliation.get_context_reconciliation_rows(
			branch_names=["Main Vet Branch"]
		)

	assert rows[0]["company"] == ""
	assert "different Companies" in rows[0]["normalization_issue"]


def test_vetedge_normalizer_is_read_only_and_coreedge_decoupled():
	source = (ROOT / "services" / "coreedge_context_reconciliation.py").read_text(encoding="utf-8")
	assert "import coreedge" not in source
	assert "from coreedge" not in source
	for forbidden in (
		"ignore_permissions=True",
		".insert(",
		".save(",
		".submit(",
		"frappe.db.set_value(",
		"frappe.db.commit(",
	):
		assert forbidden not in source
