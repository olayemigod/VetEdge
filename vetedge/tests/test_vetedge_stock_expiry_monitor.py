# -*- coding: utf-8 -*-
# Copyright (c) 2026, ProcessEdge Solutions and contributors

import json
import os
from collections import Counter

import frappe
from frappe.tests.utils import FrappeTestCase


class TestVetedgeStockExpiryMonitor(FrappeTestCase):
	def get_app_path(self, *parts):
		return os.path.join(frappe.get_app_path("vetedge"), *parts)

	def read(self, *parts):
		with open(self.get_app_path(*parts), encoding="utf-8") as source:
			return source.read()

	def test_expected_page_files_exist(self):
		page_dir = self.get_app_path("veterinary", "page", "stock_expiry_monitor")
		self.assertTrue(os.path.exists(page_dir))
		for filename in ("stock_expiry_monitor.json", "stock_expiry_monitor.js", "stock_expiry_monitor.py"):
			self.assertTrue(os.path.exists(os.path.join(page_dir, filename)))

	def test_page_json_config(self):
		with open(
			self.get_app_path("veterinary", "page", "stock_expiry_monitor", "stock_expiry_monitor.json"),
			encoding="utf-8",
		) as source:
			data = json.load(source)

		self.assertEqual(data.get("doctype"), "Page")
		self.assertEqual(data.get("name"), "stock-expiry-monitor")
		self.assertEqual(data.get("module"), "Veterinary")
		self.assertEqual(data.get("standard"), "Yes")
		roles = [row.get("role") for row in data.get("roles", [])]
		for role in ("System Manager", "VetEdge Administrator", "Dispensary User", "Branch Manager"):
			self.assertIn(role, roles)

	def test_loader_requires_standalone_edgesuite_ui_before_product_bundle(self):
		content = self.read("veterinary", "page", "stock_expiry_monitor", "stock_expiry_monitor.js")

		self.assertIn("frappe.require('edgeui.bundle.js'", content)
		self.assertIn("window.EdgeSuiteUI || window.EdgeUI", content)
		self.assertIn("runtime?.createEdgeApp", content)
		self.assertIn("runtime?.components", content)
		self.assertIn("frappe.require('vetedge_stock_expiry_monitor.bundle.js'", content)
		self.assertLess(content.index("edgeui.bundle.js"), content.index("vetedge_stock_expiry_monitor.bundle.js"))
		self.assertIn("unmount()", content)
		self.assertIn("current_visit_id", content)
		self.assertIn("Stock Expiry Monitor failed to load", content)
		self.assertNotIn("coreedge", content.lower())

	def test_product_bundle_mounts_canonical_report_with_edgesuite_runtime(self):
		content = self.read("public", "js", "vetedge_stock_expiry_monitor.bundle.js")

		self.assertIn("window.EdgeSuiteUI || window.EdgeUI", content)
		self.assertIn("createCanonicalStockExpiryMonitor(runtime)", content)
		self.assertIn("runtime.createEdgeApp(component)", content)
		self.assertNotIn("VetedgeStockExpiryMonitor.components = runtime.components", content)
		self.assertNotIn("import { createApp } from 'vue'", content)
		self.assertNotIn("coreedge", content.lower())

	def test_canonical_report_uses_shared_report_components(self):
		content = self.read("public", "js", "vetedge_stock_expiry_monitor.bundle.js")
		for component in (
			"EdgeAppShell",
			"EdgePageLayout",
			"EdgePageHeader",
			"EdgeFilterBar",
			"EdgeStatCard",
			"EdgeDataTable",
			"EdgeLoadingState",
			"EdgeEmptyState",
			"EdgeErrorState",
		):
			self.assertIn(component, content)
		for label in (
			"Warehouse",
			"Item Group",
			"Expiry Window",
			"Days Threshold",
			"Item Code",
			"Apply / Refresh",
			"Expired Batches",
			"Expiring Soon",
			"Affected Total Qty",
			"Affected Warehouses",
			"Highest Risk Items",
			"Last Recalculated",
		):
			self.assertIn(label, content)
		for icon in ("close", "activity", "layers", "building", "shield"):
			self.assertIn(f"'{icon}'", content)
		self.assertIn("showSidebar: true", content)
		self.assertIn("menuItems: this.sharedMenuItems", content)
		self.assertIn("resolveVetEdgeMenuItems", content)
		self.assertIn("rowActions", content)
		self.assertIn("Open Item", content)
		self.assertIn("Open Batch", content)

	def test_frontend_uses_shared_component_contract_without_private_imports(self):
		content = self.read(
			"public", "js", "vetedge_stock_expiry_monitor", "VetedgeStockExpiryMonitor.vue"
		)

		for component in (
			"EdgeAppShell",
			"EdgePageLayout",
			"EdgePageHeader",
			"EdgeFilterBar",
			"EdgeStatCard",
			"EdgeStatusBadge",
			"EdgeLoadingState",
			"EdgeEmptyState",
			"EdgeErrorState",
			"EdgeNotificationBell",
			"EdgeNotificationDrawer",
		):
			self.assertIn(component, content)

		self.assertIn('product="vetedge"', content)
		self.assertIn('data-edge-product="vetedge"', content)
		self.assertNotIn("coreedge/coreedge/public/js/edgeui", content)
		self.assertNotIn("../../../../../coreedge", content)

	def test_shared_shell_is_content_only_with_compact_context_and_filters(self):
		content = self.read(
			"public", "js", "vetedge_stock_expiry_monitor", "VetedgeStockExpiryMonitor.vue"
		)
		self.assertNotIn(':menuItems="menuItems"', content)
		self.assertIn("vetedge-notification-icon", content)
		self.assertIn("syncShellContext", content)
		self.assertIn("'All Branches'", content)
		self.assertIn("tenantName", content)
		self.assertIn("branchName", content)
		self.assertIn("userName", content)
		self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr))", content)
		self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", content)
		self.assertIn("grid-template-columns: minmax(0, 1fr)", content)
		self.assertNotIn("frappe.realtime", content)
		self.assertNotIn("coreedge/", content.lower())

	def test_notification_drawer_uses_vetedge_notification_apis_only(self):
		content = self.read(
			"public", "js", "vetedge_stock_expiry_monitor", "VetedgeStockExpiryMonitor.vue"
		)
		for method in (
			"get_my_edgesuite_notifications",
			"mark_my_edgesuite_notification_read",
			"mark_all_my_notifications_read",
			"acknowledge_my_notification",
			"mark_my_notification_done",
			"dismiss_my_notification",
		):
			self.assertIn(method, content)

	def test_frontend_remains_read_only_for_business_records(self):
		for parts in (
			("public", "js", "vetedge_stock_expiry_monitor", "VetedgeStockExpiryMonitor.vue"),
			("public", "js", "vetedge_stock_expiry_monitor.bundle.js"),
			("veterinary", "page", "stock_expiry_monitor", "stock_expiry_monitor.js"),
		):
			content = self.read(*parts)
			for forbidden in (
				"frappe.db.set_value",
				"frappe.client.set_value",
				"frappe.client.insert",
				"frappe.client.delete",
				"delete_doc",
			):
				self.assertNotIn(forbidden, content)

	def test_filter_and_summary_labels_exist(self):
		content = self.read("public", "js", "vetedge_stock_expiry_monitor.bundle.js")
		for label in (
			"Warehouse",
			"Item Group",
			"Expiry Window",
			"Days Threshold",
			"Item Code",
			"Apply / Refresh",
			"Expired Batches",
			"Expiring Soon",
			"Affected Total Qty",
			"Affected Warehouses",
			"Highest Risk Items",
			"Last Recalculated",
		):
			self.assertIn(label, content)

	def test_aggregation_api_returns_structured_data(self):
		from vetedge.veterinary.page.stock_expiry_monitor.stock_expiry_monitor import (
			get_stock_expiry_data,
		)

		try:
			result = get_stock_expiry_data(
				{"expiry_window": "all", "days_threshold": 60, "limit": 5, "offset": 0}
			)
		except frappe.PermissionError:
			return

		for key in ("summary", "rows", "total_count", "limit", "offset"):
			self.assertIn(key, result)
		for key in (
			"expired_items",
			"expiring_soon",
			"affected_qty",
			"affected_warehouses",
			"highest_risk_items",
			"last_updated",
		):
			self.assertIn(key, result["summary"])

	def test_stock_expiry_monitor_is_discoverable_from_standard_navigation(self):
		with open(
			self.get_app_path(
				"veterinary",
				"workspace",
				"veterinary_financial_dashboard",
				"veterinary_financial_dashboard.json",
			),
			encoding="utf-8",
		) as source:
			workspace = json.load(source)
		with open(self.get_app_path("workspace_sidebar", "vetedge.json"), encoding="utf-8") as source:
			sidebar = json.load(source)

		for rows in (workspace["links"], sidebar["items"]):
			links = {row["label"]: row for row in rows if row.get("type") == "Link"}
			self.assertIn("Stock Expiry Monitor", links)
			self.assertEqual(links["Stock Expiry Monitor"]["link_type"], "Page")
			self.assertEqual(links["Stock Expiry Monitor"]["link_to"], "stock-expiry-monitor")
			counts = Counter(
				(row.get("link_type"), row.get("link_to"))
				for row in rows
				if row.get("type") == "Link"
			)
			self.assertFalse([key for key, count in counts.items() if key[1] and count > 1])
