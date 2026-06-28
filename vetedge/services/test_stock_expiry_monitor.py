from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services import stock_expiry_monitor


class TestStockExpiryMonitor(TestCase):
	def setUp(self):
		self.translate = patch.object(stock_expiry_monitor, "_", side_effect=lambda value, *args, **kwargs: value)
		self.translate.start()

	def tearDown(self):
		self.translate.stop()

	def test_expiry_bucket_parsing(self):
		self.assertEqual(stock_expiry_monitor.parse_expiry_buckets("60, 30,90,30,bad"), [30, 60, 90])

	def test_expired_classification(self):
		self.assertEqual(
			stock_expiry_monitor.classify_expiry("2026-06-28", [30, 60, 90], today="2026-06-28"),
			"Expired",
		)

	def test_expiring_soon_classification(self):
		self.assertEqual(
			stock_expiry_monitor.classify_expiry("2026-07-10", [30, 60, 90], today="2026-06-28"),
			"Expiring Soon",
		)

	def test_safe_classification(self):
		self.assertEqual(
			stock_expiry_monitor.classify_expiry("2027-01-01", [30, 60, 90], today="2026-06-28"),
			"Safe",
		)
		self.assertEqual(stock_expiry_monitor.classify_expiry(None, [30], today="2026-06-28"), "Safe")

	def test_rows_default_sort_by_closest_expiry_first(self):
		rows = [
			frappe._dict(
				item_code="MED-LATE",
				item_name="Late",
				item_group="Medicines",
				batch_no="B-LATE",
				warehouse="Main",
				company="Vet Co",
				qty=1,
				stock_uom="Nos",
				expiry_date="2026-08-01",
			),
			frappe._dict(
				item_code="MED-OLD",
				item_name="Old",
				item_group="Medicines",
				batch_no="B-OLD",
				warehouse="Main",
				company="Vet Co",
				qty=1,
				stock_uom="Nos",
				expiry_date="2026-06-01",
			),
			frappe._dict(
				item_code="MED-SOON",
				item_name="Soon",
				item_group="Medicines",
				batch_no="B-SOON",
				warehouse="Main",
				company="Vet Co",
				qty=1,
				stock_uom="Nos",
				expiry_date="2026-06-30",
			),
		]
		with (
			patch.object(stock_expiry_monitor, "_has_stock_expiry_source", return_value=True),
			patch.object(stock_expiry_monitor, "nowdate", return_value="2026-06-28"),
			patch.object(stock_expiry_monitor, "_query_batch_stock_rows", return_value=rows),
			patch.object(stock_expiry_monitor, "_get_warehouse_branch_map", return_value={"Main": "Branch A"}),
			patch.object(stock_expiry_monitor, "_settings_bucket_value", return_value="30,60,90"),
		):
			data = stock_expiry_monitor.get_stock_expiry_rows({})

		self.assertEqual([row["batch_no"] for row in data], ["B-OLD", "B-SOON", "B-LATE"])
		self.assertEqual(data[0]["expiry_status"], "Expired")
		self.assertEqual(data[1]["expiry_status"], "Expiring Soon")
		self.assertEqual(data[2]["expiry_status"], "Expiring Soon")

	def test_empty_no_batch_data_behavior(self):
		with patch.object(stock_expiry_monitor, "_has_stock_expiry_source", return_value=False):
			columns, data, _, chart, summary = stock_expiry_monitor.execute_report({})

		self.assertGreater(len(columns), 0)
		self.assertEqual(data, [])
		self.assertEqual([row["value"] for row in summary], [0, 0, 0, 0])
		self.assertEqual(chart["title"], "Stock Expiry Status")

	def test_query_applies_company_warehouse_branch_filters(self):
		captured = {}

		def sql(query, values, as_dict=False):
			captured["query"] = query
			captured["values"] = values
			return []

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=lambda doctype, name=None: True,
				sql=sql,
			),
		)
		with (
			patch.object(stock_expiry_monitor, "frappe", frappe_stub),
			patch.object(stock_expiry_monitor, "get_branch_dispensary_warehouse", return_value="Branch Store"),
		):
			stock_expiry_monitor._query_batch_stock_rows(
				frappe._dict(company="Vet Co", warehouse="Main Store", branch="Branch A", item_group="Medicines")
			)

		self.assertEqual(captured["values"]["company"], "Vet Co")
		self.assertEqual(captured["values"]["warehouse"], "Main Store")
		self.assertEqual(captured["values"]["branch_warehouse"], "Branch Store")
		self.assertEqual(captured["values"]["item_group"], "Medicines")

	def test_settings_defaults(self):
		frappe_stub = SimpleNamespace(db=SimpleNamespace(exists=lambda *args, **kwargs: False))
		with patch.object(stock_expiry_monitor, "frappe", frappe_stub):
			settings = stock_expiry_monitor.get_stock_expiry_monitor_settings()

		self.assertFalse(settings.enable_stock_expiry_monitor)
		self.assertEqual(settings.expiry_reminder_days, "30,60,90")
		self.assertTrue(settings.enable_internal_expiry_notifications)

	def test_notification_generation_is_idempotent(self):
		rows = [
			{
				"item_code": "MED-001",
				"batch_no": "B-001",
				"warehouse": "Main",
				"expiry_status": "Expired",
				"expiry_date": "2026-06-01",
			}
		]
		with (
			patch.object(
				stock_expiry_monitor,
				"get_stock_expiry_monitor_settings",
				return_value=stock_expiry_monitor.StockExpiryMonitorSettings(enable_stock_expiry_monitor=True),
			),
			patch.object(stock_expiry_monitor, "get_stock_expiry_rows", return_value=rows),
			patch.object(stock_expiry_monitor, "get_internal_notification_recipients", return_value=["user@example.com"]),
			patch.object(stock_expiry_monitor, "_create_internal_stock_expiry_notification", side_effect=[True, False]) as create,
		):
			first = stock_expiry_monitor.generate_stock_expiry_notifications({})
			second = stock_expiry_monitor.generate_stock_expiry_notifications({})

		self.assertEqual(first["created"], 1)
		self.assertEqual(second["reused"], 1)
		self.assertEqual(create.call_args_list[0].args[0], rows[0])

	def test_coreedge_absent_does_not_crash_when_external_channels_enabled(self):
		settings = stock_expiry_monitor.StockExpiryMonitorSettings(
			enable_stock_expiry_monitor=True,
			enable_internal_expiry_notifications=False,
			enable_email_expiry_notifications=True,
			enable_whatsapp_expiry_notifications=True,
			enable_sms_expiry_notifications=True,
		)
		with (
			patch.object(stock_expiry_monitor, "get_stock_expiry_monitor_settings", return_value=settings),
			patch.object(stock_expiry_monitor, "get_stock_expiry_rows", return_value=[]),
			patch.object(stock_expiry_monitor, "_log_external_channel_skipped") as log_skip,
		):
			result = stock_expiry_monitor.generate_stock_expiry_notifications({})

		self.assertEqual(result["external_skipped"], ["Email", "WhatsApp", "SMS"])
		self.assertEqual(log_skip.call_count, 3)
