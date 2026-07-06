# -*- coding: utf-8 -*-
# Copyright (c) 2026, ProcessEdge Solutions and contributors
# For license information, please see license.txt

import os
import json
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

	def test_lazy_loads_edgeui_bundle(self):
		"""Verify stock_expiry_monitor.js lazy-loads edgeui.bundle.js via frappe.require."""
		vetedge_path = frappe.get_app_path("vetedge")
		js_path = os.path.join(
			vetedge_path, "veterinary", "page", "stock_expiry_monitor", "stock_expiry_monitor.js"
		)
		self.assertTrue(os.path.exists(js_path))
		
		with open(js_path, "r") as f:
			content = f.read()
			
		self.assertIn("frappe.require('edgeui.bundle.js'", content)
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
