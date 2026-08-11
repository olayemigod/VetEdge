from __future__ import annotations

from unittest import TestCase

import frappe

from vetedge.install.dashboard import (
	SIDEBAR_TARGET_DOCTYPES,
	_should_keep_sidebar_item,
	ensure_vetedge_workspace_sidebar,
)


class TestVetEdgeSidebarTargetIntegrity(TestCase):
	def test_missing_standard_targets_are_not_publishable(self):
		missing = "VetEdge QA Target That Does Not Exist"
		for link_type in SIDEBAR_TARGET_DOCTYPES:
			with self.subTest(link_type=link_type):
				self.assertFalse(
					_should_keep_sidebar_item(
						{
							"type": "Link",
							"label": missing,
							"link_type": link_type,
							"link_to": missing,
						}
					)
				)

	def test_runtime_sidebar_contains_only_existing_standard_targets(self):
		ensure_vetedge_workspace_sidebar()
		sidebar = frappe.get_doc("Workspace Sidebar", "VetEdge")
		checked = 0

		for item in sidebar.items:
			if item.type != "Link" or not item.link_to:
				continue
			target_doctype = SIDEBAR_TARGET_DOCTYPES.get(item.link_type)
			if not target_doctype:
				continue
			checked += 1
			self.assertTrue(
				frappe.db.exists(target_doctype, item.link_to),
				f"Broken sidebar target published: {item.label} -> {item.link_type} {item.link_to}",
			)

		self.assertGreater(checked, 0)
