# -*- coding: utf-8 -*-
# Copyright (c) 2026, ProcessEdge Solutions and contributors
# For license information, please see license.txt

import os
import json
from collections import Counter
import frappe
from frappe.tests.utils import FrappeTestCase

class TestVetedgeStockExpiryMonitor(FrappeTestCase):
	def test_expected_page_files_exist(self):
		"""Verify all page files are in place."""
		vetedge_path = frappe.get_app_path("vetedge")
		page_dir = os.path.join(vetedge_path, "veterinary", "page", "stock_expiry_monitor")
		self.assertTrue(os.path.exists(page_dir), "Page directory does not exist")
		
		expected_files = [
			"stock_expiry_monitor.json",
			"stock_expiry_monitor.js",
			"stock_expiry_monitor.py"
		]
		for filename in expected_files:
			file_path = os.path.join(page_dir, filename)
			self.assertTrue(os.path.exists(file_path), f"Page file {filename} does not exist")

	def test_page_json_config(self):
		"""Verify standard page definition parameters."""
		vetedge_path = frappe.get_app_path("vetedge")
		json_path = os.path.join(
			vetedge_path, "veterinary", "page", "stock_expiry_monitor", "stock_expiry_monitor.json"
		)
		self.assertTrue(os.path.exists(json_path))
		
		with open(json_path, "r") as f:
			data = json.load(f)
			
		self.assertEqual(data.get("doctype"), "Page")
		self.assertEqual(data.get("name"), "stock-expiry-monitor")
		self.assertEqual(data.get("module"), "Veterinary")
		self.assertEqual(data.get("standard"), "Yes")
		
		roles = [r.get("role") for r in data.get("roles", [])]
		self.assertIn("System Manager", roles)
		self.assertIn("VetEdge Administrator", roles)
		self.assertIn("Dispensary User", roles)
		self.assertIn("Branch Manager", roles)

	def test_loader_loads_edgeui_before_product_bundle(self):
		"""Verify stock_expiry_monitor.js loads public EdgeUI before the VetEdge bundle."""
		vetedge_path = frappe.get_app_path("vetedge")
		js_path = os.path.join(
			vetedge_path, "veterinary", "page", "stock_expiry_monitor", "stock_expiry_monitor.js"
		)
		self.assertTrue(os.path.exists(js_path))
		
		with open(js_path, "r") as f:
			content = f.read()
			
		edgeui_idx = content.find("frappe.require('edgeui.bundle.js'")
		product_idx = content.find("frappe.require('vetedge_stock_expiry_monitor.bundle.js'")
		self.assertNotEqual(edgeui_idx, -1)
		self.assertNotEqual(product_idx, -1)
		self.assertLess(edgeui_idx, product_idx)
		self.assertIn("frappe.require('vetedge_stock_expiry_monitor.bundle.js'", content)
		self.assertIn("window.EdgeUI", content)
		self.assertIn("Required EdgeSuite shell components could not be resolved", content)
		self.assertIn("unmount()", content)
		self.assertIn("current_visit_id", content)

	def test_edgeui_not_copied(self):
		"""Assert that shared EdgeUI Vue components are not cloned or copied into VetEdge."""
		vetedge_path = frappe.get_app_path("vetedge")
		for root, dirs, files in os.walk(vetedge_path):
			for file in files:
				if file.startswith("Edge") and file.endswith(".vue"):
					self.fail(f"Found cloned EdgeUI component {file} inside VetEdge at {root}")

	def test_aggregation_api_returns_structured_data(self):
		"""Verify get_stock_expiry_data API logic returns expected structures."""
		from vetedge.veterinary.page.stock_expiry_monitor.stock_expiry_monitor import get_stock_expiry_data
		
		try:
			res = get_stock_expiry_data({
				"expiry_window": "all",
				"days_threshold": 60,
				"limit": 5,
				"offset": 0
			})
			self.assertIn("summary", res)
			self.assertIn("rows", res)
			self.assertIn("total_count", res)
			self.assertIn("limit", res)
			self.assertIn("offset", res)
			
			summary = res["summary"]
			self.assertIn("expired_items", summary)
			self.assertIn("expiring_soon", summary)
			self.assertIn("affected_qty", summary)
			self.assertIn("affected_warehouses", summary)
			self.assertIn("highest_risk_items", summary)
			self.assertIn("last_updated", summary)
		except frappe.PermissionError:
			pass

	def test_frontend_uses_layout_components_and_identity(self):
		"""Verify VetEdge Stock Expiry Monitor uses the real EdgeSuite shell pattern."""
		vetedge_path = frappe.get_app_path("vetedge")
		vue_path = os.path.join(
			vetedge_path, "public", "js", "vetedge_stock_expiry_monitor", "VetedgeStockExpiryMonitor.vue"
		)
		self.assertTrue(os.path.exists(vue_path))
		with open(vue_path, "r") as f:
			content = f.read()

		for component in ("EdgeAppShell", "EdgePageLayout", "EdgeFilterBar", "EdgeStatCard", "EdgeStatusBadge"):
			self.assertIn(component, content)
		for component in ("EdgeNotificationBell", "EdgeNotificationDrawer"):
			self.assertIn(component, content)
		self.assertIn('product="vetedge"', content)
		self.assertIn('data-edge-product="vetedge"', content)
		self.assertIn("EdgeSuite UI failed to load", content)
		self.assertIn("missingComponents", content)
		self.assertIn("requiredEdgeUIComponents", content)
		self.assertIn("localEdgeUIComponents", content)
		self.assertIn("resolveEdgeUIComponents", content)
		self.assertIn("window.EdgeUI", content)
		self.assertIn("import { h } from 'vue'", content)
		self.assertNotIn("coreedge/coreedge/public/js/edgeui", content)
		self.assertNotIn("../../../../../coreedge", content)
		self.assertNotIn("return 'div'", content)
		self.assertNotIn("getComponent", content)

	def test_edgesuite_notification_drawer_is_piloted_without_global_override(self):
		"""Verify the Stock Expiry Monitor opts into the shared drawer through VetEdge APIs only."""
		vetedge_path = frappe.get_app_path("vetedge")
		vue_path = os.path.join(
			vetedge_path, "public", "js", "vetedge_stock_expiry_monitor", "VetedgeStockExpiryMonitor.vue"
		)
		hooks_path = os.path.join(vetedge_path, "hooks.py")
		with open(vue_path, "r") as f:
			content = f.read()
		with open(hooks_path, "r") as f:
			hooks = f.read()

		self.assertIn("<EdgeNotificationBell", content)
		self.assertIn("<EdgeNotificationDrawer", content)
		self.assertIn("vetedge.services.notification_api.get_my_edgesuite_notifications", content)
		self.assertIn("vetedge.services.notification_api.mark_my_edgesuite_notification_read", content)
		self.assertIn("vetedge.services.notification_api.mark_all_my_notifications_read", content)
		self.assertIn("acknowledge_my_notification", content)
		self.assertIn("mark_my_notification_done", content)
		self.assertIn("dismiss_my_notification", content)
		self.assertNotIn("/assets/vetedge/js/veterinary_notification_center.js", hooks)
		self.assertNotIn("app_include_js.append", hooks)

	def test_notification_drawer_frontend_does_not_mutate_business_records(self):
		"""Verify drawer wiring only calls notification APIs, not business document mutation APIs."""
		vetedge_path = frappe.get_app_path("vetedge")
		vue_path = os.path.join(
			vetedge_path, "public", "js", "vetedge_stock_expiry_monitor", "VetedgeStockExpiryMonitor.vue"
		)
		with open(vue_path, "r") as f:
			content = f.read()

		for forbidden in (
			"frappe.db.set_value",
			"frappe.client.set_value",
			"frappe.client.insert",
			"frappe.client.delete",
			"Sales Invoice",
			"Payment Entry",
			"Stock Entry",
			"submit(",
			"delete_doc",
		):
			self.assertNotIn(forbidden, content)

	def test_filter_and_summary_labels_exist(self):
		"""Verify visible filters and summary cards remain in the normal render flow."""
		vetedge_path = frappe.get_app_path("vetedge")
		vue_path = os.path.join(
			vetedge_path, "public", "js", "vetedge_stock_expiry_monitor", "VetedgeStockExpiryMonitor.vue"
		)
		with open(vue_path, "r") as f:
			content = f.read()

		self.assertIn("edge-filter-grid", content)
		self.assertIn("edge-stat-grid", content)
		self.assertIn("edge-table-card", content)
		for label in ("Warehouse", "Item Group", "Expiry Window", "Days Threshold", "Item Code", "Apply / Refresh"):
			self.assertIn(label, content)
		for label in ("Expired Batches", "Expiring Soon", "Affected Total Qty", "Affected Warehouses", "Highest Risk Items", "Last Recalculated"):
			self.assertIn(label, content)

	def test_loader_uses_product_bundle_mount_function(self):
		"""Verify page loader avoids raw CSS requires and mounts with the VetEdge bundle runtime."""
		vetedge_path = frappe.get_app_path("vetedge")
		js_path = os.path.join(
			vetedge_path, "veterinary", "page", "stock_expiry_monitor", "stock_expiry_monitor.js"
		)
		with open(js_path, "r") as f:
			content = f.read()

		self.assertIn("frappe.require('edgeui.bundle.js'", content)
		self.assertIn("vetedge_stock_expiry_monitor.bundle.js", content)
		self.assertIn("mountVetedgeStockExpiryMonitor", content)
		self.assertIn("EdgeSuite UI failed to load", content)
		self.assertIn('data-edge-product="vetedge"', content)
		self.assertNotIn("edgeui.bundle.css", content)
		self.assertNotIn("vetedge_stock_expiry_monitor.bundle.css", content)
		self.assertNotIn("createEdgeApp", content)

	def test_no_stock_mutation_logic_introduced_in_frontend(self):
		"""Verify the monitor frontend remains read-only for stock records."""
		vetedge_path = frappe.get_app_path("vetedge")
		for rel in (
			("public", "js", "vetedge_stock_expiry_monitor", "VetedgeStockExpiryMonitor.vue"),
			("veterinary", "page", "stock_expiry_monitor", "stock_expiry_monitor.js"),
		):
			path = os.path.join(vetedge_path, *rel)
			with open(path, "r") as f:
				content = f.read()
			for forbidden in ("frappe.db.set_value", "frappe.client.set_value", "frappe.client.insert", "frappe.client.delete", "save(", "submit(", "delete_doc"):
				self.assertNotIn(forbidden, content)

	def test_stock_expiry_monitor_is_discoverable_from_standard_navigation(self):
		"""Verify Phase 2F navigation exposes the monitor with the standard label and route."""
		vetedge_path = frappe.get_app_path("vetedge")
		workspace_path = os.path.join(
			vetedge_path,
			"veterinary",
			"workspace",
			"veterinary_financial_dashboard",
			"veterinary_financial_dashboard.json",
		)
		sidebar_path = os.path.join(vetedge_path, "workspace_sidebar", "vetedge.json")
		with open(workspace_path, "r") as f:
			workspace = json.load(f)
		with open(sidebar_path, "r") as f:
			sidebar = json.load(f)

		expected_workspace_groups = ["Dashboard", "Operations", "Records", "Reports", "Settings"]
		expected_sidebar_groups = [
			"Dashboard",
			"Front Desk",
			"Clinical",
			"Hospital & Services",
			"Inventory / Pharmacy",
			"Reports",
			"Veterinary Masters",
			"Configuration",
			"Platform",
			"Help & Training",
		]
		workspace_groups = [row["label"] for row in workspace["links"] if row.get("type") == "Card Break"]
		sidebar_groups = [row["label"] for row in sidebar["items"] if row.get("type") == "Section Break"]
		self.assertEqual(workspace_groups, expected_workspace_groups)
		self.assertEqual(sidebar_groups, expected_sidebar_groups)

		for rows in (workspace["links"], sidebar["items"]):
			links = {
				row["label"]: row
				for row in rows
				if row.get("type") == "Link"
			}
			self.assertIn("Stock Expiry Monitor", links)
			self.assertEqual(links["Stock Expiry Monitor"]["link_type"], "Page")
			self.assertEqual(links["Stock Expiry Monitor"]["link_to"], "stock-expiry-monitor")
			counts = Counter(
				(row.get("link_type"), row.get("link_to"))
				for row in rows
				if row.get("type") == "Link"
			)
			self.assertFalse([key for key, count in counts.items() if key[1] and count > 1])

		sidebar_labels = [row.get("label") for row in sidebar["items"]]
		self.assertGreater(sidebar_labels.index("Stock Expiry Monitor"), sidebar_labels.index("Inventory / Pharmacy"))
		self.assertLess(sidebar_labels.index("Stock Expiry Monitor"), sidebar_labels.index("Reports"))
