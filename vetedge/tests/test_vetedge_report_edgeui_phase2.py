from __future__ import annotations

from pathlib import Path

try:
	from frappe.tests.utils import FrappeTestCase
except ImportError:
	FrappeTestCase = None

ROOT = Path(__file__).resolve().parents[2]


def read(*parts: str) -> str:
	return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_service_reports_use_the_shared_edgesuite_surface():
	reports = {
		"lab_order_report": ("Lab Order Report", "Laboratory Operations", "Laboratory Report"),
		"vaccination_report": ("Vaccination Report", "Preventive Care", "Vaccination Report"),
		"boarding_report": ("Boarding Report", "Boarding Operations", "Boarding Report"),
		"grooming_report": ("Grooming Report", "Grooming Operations", "Grooming Report"),
	}
	for folder, contracts in reports.items():
		content = read("vetedge", "veterinary", "report", folder, f"{folder}.js")
		for contract in contracts:
			assert contract in content
		assert "vetedgeReportEdgeUI?.register" in content
		assert "vetedgeReportVisibility?.apply" in content
		assert "vetedgeReportEdgeUI?.attach" in content
		assert content.index("vetedgeReportVisibility?.apply") < content.index("vetedgeReportEdgeUI?.attach")
		assert "frappe.datetime.month_start()" in content
		assert "frappe.datetime.add_days" not in content


def test_service_report_clients_do_not_change_backend_or_accounting_state():
	for folder in ("lab_order_report", "vaccination_report", "boarding_report", "grooming_report"):
		content = read("vetedge", "veterinary", "report", folder, f"{folder}.js")
		for forbidden in (
			"frappe.db.set_value",
			"frappe.call({",
			"ignore_permissions",
			"window.open",
			"coreedge/public",
		):
			assert forbidden not in content


if FrappeTestCase is not None:
	class TestVetEdgeServiceReportMetadata(FrappeTestCase):
		def _cards(self, report_name: str, rows: list[dict]) -> dict:
			from vetedge.services.report_insights import build_report_summary

			summary = build_report_summary(
				report_name,
				rows,
				{"from_date": "2026-07-01", "to_date": "2026-07-31"},
			)
			return {row.get("id"): row for row in summary if row.get("id")}

		def test_laboratory_cards_use_existing_report_rows(self):
			cards = self._cards(
				"Lab Order Report",
				[
					{"status": "Requested", "linked_invoice": None},
					{"status": "Reviewed", "linked_invoice": "SINV-1"},
				],
			)
			self.assertEqual(cards["total"]["value"], 2)
			self.assertEqual(cards["pending"]["value"], 1)
			self.assertEqual(cards["completed"]["value"], 1)
			self.assertEqual(cards["unbilled"]["value"], 1)

		def test_vaccination_cards_use_existing_report_rows(self):
			cards = self._cards(
				"Vaccination Report",
				[
					{"status": "Administered", "due_status": "Administered"},
					{"status": "Pending Administration", "due_status": "Overdue"},
				],
			)
			self.assertEqual(cards["total"]["value"], 2)
			self.assertEqual(cards["administered"]["value"], 1)
			self.assertEqual(cards["overdue"]["value"], 1)

		def test_boarding_and_grooming_cards_use_existing_rows(self):
			boarding = self._cards(
				"Boarding Report",
				[
					{"status": "Checked In", "stay_days": 3, "total_boarding_charge": 30000, "linked_invoice": "SINV-1"},
					{"status": "Reserved", "stay_days": 2, "total_boarding_charge": 20000, "linked_invoice": None},
				],
			)
			self.assertEqual(boarding["total"]["value"], 1)
			self.assertEqual(boarding["upcoming"]["value"], 1)
			self.assertEqual(boarding["revenue"]["value"], 50000)
			self.assertEqual(boarding["unbilled"]["value"], 1)

			grooming = self._cards(
				"Grooming Report",
				[
					{"status": "Completed", "total_charge": 15000, "linked_invoice": "SINV-2", "grooming_service": "Bath"},
					{"status": "In Progress", "total_charge": 10000, "linked_invoice": None, "grooming_service": "Bath"},
				],
			)
			self.assertEqual(grooming["total"]["value"], 2)
			self.assertEqual(grooming["completed"]["value"], 1)
			self.assertEqual(grooming["revenue"]["value"], 25000)
			self.assertEqual(grooming["unpaid"]["value"], 1)
			self.assertEqual(grooming["popular"]["value"], "Bath")
