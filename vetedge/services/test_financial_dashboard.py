from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from vetedge.services.financial_dashboard import get_branch_performance_data, get_financial_dashboard_view


class TestFinancialDashboard(TestCase):
	def test_dashboard_view_degrades_gracefully_without_payment_entry_access(self):
		frappe_stub = SimpleNamespace(
			defaults=SimpleNamespace(
				get_global_default=lambda key: "NGN",
				get_default=lambda key: "NGN",
			),
			_dict=lambda value: value,
		)

		with (
			patch("vetedge.services.financial_dashboard.frappe", frappe_stub),
			patch("vetedge.services.financial_dashboard._", side_effect=lambda value: value),
			patch("vetedge.services.financial_dashboard.require_read_permission"),
			patch(
				"vetedge.services.financial_dashboard.can_read_doctype",
				side_effect=lambda doctype: doctype == "Sales Invoice",
			),
			patch("vetedge.services.financial_dashboard.can_read_report", return_value=False),
			patch("vetedge.services.financial_dashboard.get_today_revenue", return_value={"value": 10}),
			patch("vetedge.services.financial_dashboard.get_week_revenue", return_value={"value": 20}),
			patch("vetedge.services.financial_dashboard.get_month_revenue", return_value={"value": 30}),
			patch("vetedge.services.financial_dashboard.get_outstanding_receivables", return_value={"value": 40}),
			patch("vetedge.services.financial_dashboard.get_payments_today", return_value={"value": 50}),
			patch("vetedge.services.financial_dashboard.get_daily_revenue_chart", return_value={"type": "line", "data": {}}),
			patch(
				"vetedge.services.financial_dashboard.get_revenue_by_cost_center_chart",
				return_value={"type": "bar", "data": {}},
			),
			patch(
				"vetedge.services.financial_dashboard.get_revenue_by_service_type_chart",
				return_value={"type": "bar", "data": {}},
			),
			patch(
				"vetedge.services.financial_dashboard.get_paid_vs_outstanding_chart",
				return_value={"type": "bar", "data": {}},
			),
			patch(
				"vetedge.services.financial_dashboard.get_payment_method_breakdown_chart",
				return_value={"type": "bar", "data": {}},
			),
		):
			view = get_financial_dashboard_view(filters={"from_date": "2026-04-01", "to_date": "2026-04-23"})

		self.assertEqual([card["label"] for card in view["cards"]], [
			"Today Revenue",
			"Week Revenue",
			"Month Revenue",
			"Outstanding Receivables",
		])
		self.assertEqual(
			[chart["key"] for chart in view["charts"]],
			[
				"daily_revenue_trend",
				"revenue_by_cost_center",
				"revenue_by_service_type",
				"paid_vs_outstanding",
			],
		)
		self.assertEqual(
			view["shortcuts"],
			[{"label": "Sales Invoice", "route": {"type": "DocType", "name": "Sales Invoice"}}],
		)
		self.assertFalse(view["capabilities"]["can_read_payment_entry"])

	def test_dashboard_view_includes_payment_widgets_when_payment_entry_access_exists(self):
		frappe_stub = SimpleNamespace(
			defaults=SimpleNamespace(
				get_global_default=lambda key: "NGN",
				get_default=lambda key: "NGN",
			),
			_dict=lambda value: value,
		)

		with (
			patch("vetedge.services.financial_dashboard.frappe", frappe_stub),
			patch("vetedge.services.financial_dashboard._", side_effect=lambda value: value),
			patch("vetedge.services.financial_dashboard.require_read_permission"),
			patch("vetedge.services.financial_dashboard.can_read_doctype", return_value=True),
			patch("vetedge.services.financial_dashboard.can_read_report", return_value=True),
			patch("vetedge.services.financial_dashboard.get_today_revenue", return_value={"value": 10}),
			patch("vetedge.services.financial_dashboard.get_week_revenue", return_value={"value": 20}),
			patch("vetedge.services.financial_dashboard.get_month_revenue", return_value={"value": 30}),
			patch("vetedge.services.financial_dashboard.get_outstanding_receivables", return_value={"value": 40}),
			patch("vetedge.services.financial_dashboard.get_payments_today", return_value={"value": 50}),
			patch("vetedge.services.financial_dashboard.get_daily_revenue_chart", return_value={"type": "line", "data": {}}),
			patch(
				"vetedge.services.financial_dashboard.get_revenue_by_cost_center_chart",
				return_value={"type": "bar", "data": {}},
			),
			patch(
				"vetedge.services.financial_dashboard.get_revenue_by_service_type_chart",
				return_value={"type": "bar", "data": {}},
			),
			patch(
				"vetedge.services.financial_dashboard.get_paid_vs_outstanding_chart",
				return_value={"type": "bar", "data": {}},
			),
			patch(
				"vetedge.services.financial_dashboard.get_payment_method_breakdown_chart",
				return_value={"type": "bar", "data": {}},
			),
		):
			view = get_financial_dashboard_view(filters={"from_date": "2026-04-01", "to_date": "2026-04-23"})

		self.assertIn("Payments Today", [card["label"] for card in view["cards"]])
		self.assertIn("payment_method_breakdown", [chart["key"] for chart in view["charts"]])
		self.assertEqual(len(view["shortcuts"]), 4)
		self.assertTrue(view["capabilities"]["can_read_payment_entry"])

	def test_branch_performance_data_applies_branch_filter_when_available(self):
		captured = {}
		frappe_stub = SimpleNamespace(
			_dict=lambda value=None: value or {},
			db=SimpleNamespace(
				sql=lambda query, params=None, as_dict=None: captured.update({"query": query, "params": params}) or [],
				table_exists=lambda table: False,
			),
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: fieldname == "branch"),
		)

		with patch("vetedge.services.financial_dashboard.frappe", frappe_stub):
			get_branch_performance_data({"from_date": "2026-05-01", "to_date": "2026-05-06", "branch": "Main"})

		self.assertIn("si.branch = %(branch)s", captured["query"])
		self.assertEqual(captured["params"]["branch"], "Main")
