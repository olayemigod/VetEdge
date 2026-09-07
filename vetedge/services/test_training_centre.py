from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

try:
	import frappe
except ModuleNotFoundError:
	class _ValidationError(Exception):
		pass

	class _DoesNotExistError(Exception):
		pass

	class _PermissionError(Exception):
		pass

	frappe = SimpleNamespace(
		ValidationError=_ValidationError,
		DoesNotExistError=_DoesNotExistError,
		PermissionError=_PermissionError,
		throw=lambda message, exc=None: (_ for _ in ()).throw((exc or _ValidationError)(message)),
		get_roles=lambda user=None: [],
		whitelist=lambda *args, **kwargs: (lambda fn: fn),
	)
	sys.modules["frappe"] = frappe

from vetedge.services import training_centre


class TestTrainingCentre(TestCase):
	def test_manifest_loads_published_modules(self):
		modules = training_centre.load_training_manifest()

		self.assertGreaterEqual(len(modules), 10)
		self.assertEqual(modules[0]["role_group"], "Shared Operations")
		self.assertTrue(all(module["status"] == "Published" for module in modules))
		self.assertTrue(all(module["short_description"] for module in modules))
		self.assertTrue(all(module["video_title"] for module in modules))
		self.assertTrue(all(module["video_status"] == "Not Recorded" for module in modules if not module["youtube_url"]))

	def test_public_payload_uses_training_friendly_metadata(self):
		module = training_centre.load_training_manifest()[0]
		payload = training_centre.public_module_payload(module)

		self.assertIn("short_description", payload)
		self.assertIn("video_title", payload)
		self.assertIn("video_status", payload)
		self.assertIn("video_display_status", payload)
		self.assertNotIn("markdown_path", payload)

	def test_invalid_module_id_is_rejected(self):
		with patch("vetedge.services.training_centre.frappe.throw", side_effect=frappe.DoesNotExistError):
			self.assertRaises(frappe.DoesNotExistError, training_centre.get_module_by_id, "not-a-module")

	def test_markdown_link_target_maps_to_module_id(self):
		self.assertEqual(
			training_centre.get_training_module_link_target("consultation_workflow.md"),
			"training-module:consultation",
		)
		self.assertEqual(
			training_centre.get_training_module_link_target("./lab_order_workflow.md#practice"),
			"training-module:lab-order#practice",
		)
		self.assertEqual(
			training_centre.get_training_module_link_target("docs/training/veterinary_doctor_operations/hospitalisation_workflow.md"),
			"training-module:hospitalisation",
		)

	def test_markdown_link_target_rejects_unapproved_paths(self):
		self.assertEqual(training_centre.get_training_module_link_target("../README.md"), "")
		self.assertEqual(training_centre.get_training_module_link_target("other_folder/consultation_workflow.md"), "")
		self.assertEqual(training_centre.get_training_module_link_target("https://example.com/consultation_workflow.md"), "")
		self.assertEqual(training_centre.get_training_module_link_target("not_in_manifest.md"), "")
		self.assertEqual(training_centre.get_training_module_link_target("training_modules.json"), "")

	def test_markdown_links_are_rewritten_without_image_rewrites(self):
		markdown = (
			"See [Consultation](consultation_workflow.md) and "
			"![Screenshot](training_assets/screenshots/example.png)."
		)

		rewritten = training_centre.rewrite_training_markdown_links(markdown)

		self.assertIn("[Consultation](training-module:consultation)", rewritten)
		self.assertIn("![Screenshot](training_assets/screenshots/example.png)", rewritten)

	def test_markdown_path_must_stay_inside_training_folder(self):
		module = {
			"markdown_path": "docs/training/veterinary_doctor_operations/../../README.md",
		}

		with patch("vetedge.services.training_centre.frappe.throw", side_effect=frappe.ValidationError):
			self.assertRaises(frappe.ValidationError, training_centre.resolve_markdown_path, module)

	def test_only_markdown_files_are_allowed(self):
		module = {
			"markdown_path": "docs/training/veterinary_doctor_operations/training_modules.json",
		}

		with patch("vetedge.services.training_centre.frappe.throw", side_effect=frappe.ValidationError):
			self.assertRaises(frappe.ValidationError, training_centre.resolve_markdown_path, module)

	def test_role_filter_allows_shared_and_doctor_operations_for_doctor(self):
		with patch("vetedge.services.training_centre.get_user_training_roles", return_value={"VetEdge Doctor"}):
			modules = training_centre.get_visible_training_modules(user="doctor@example.com")

		self.assertTrue(modules)
		self.assertEqual({module["role_group"] for module in modules}, {"Shared Operations", "Doctor Operations"})

	def test_role_filter_allows_each_starter_operational_role(self):
		cases = {
			"Veterinary Nurse": "Nursing Operations",
			"VetEdge Front Desk": "Front Desk Operations",
			"Accounts/Cashier": "Accounts & Billing",
			"Dispensary User": "Dispensary & Stock",
			"Lab Technician": "Laboratory Operations",
			"VetEdge Groomer": "Grooming Operations",
			"Branch Manager": "Branch Management",
		}
		for role, expected_group in cases.items():
			with self.subTest(role=role), patch(
				"vetedge.services.training_centre.get_user_training_roles", return_value={role}
			):
				modules = training_centre.get_visible_training_modules(user="role@example.com")
				groups = {module["role_group"] for module in modules}
				self.assertIn("Shared Operations", groups)
				self.assertIn(expected_group, groups)

	def test_role_filter_blocks_non_vetedge_supplemental_role(self):
		with patch("vetedge.services.training_centre.get_user_training_roles", return_value={"VetEdge Groomer"}):
			groomer_modules = training_centre.get_visible_training_modules(user="groomer@example.com")
		with patch("vetedge.services.training_centre.get_user_training_roles", return_value={"Accounts User"}):
			modules = training_centre.get_visible_training_modules(user="accounts-user@example.com")

		self.assertTrue(groomer_modules)
		self.assertEqual(modules, [])

	def test_administrator_can_view_every_published_training_group(self):
		with patch("vetedge.services.training_centre.get_user_training_roles", return_value={"VetEdge Administrator"}):
			modules = training_centre.get_visible_training_modules(user="admin@example.com")

		self.assertEqual(len(modules), len(training_centre.load_training_manifest()))

	def test_youtube_url_validation(self):
		self.assertEqual(
			training_centre.get_safe_youtube_embed_url("https://youtu.be/dQw4w9WgXcQ"),
			"https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
		)
		self.assertEqual(
			training_centre.get_safe_youtube_embed_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
			"https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
		)
		self.assertEqual(training_centre.get_safe_youtube_embed_url("https://example.com/video"), "")

	def test_empty_youtube_url_reports_placeholder(self):
		self.assertEqual(training_centre.get_video_display_status("", "Not Recorded"), "Video coming soon")
		self.assertEqual(training_centre.get_video_display_status("https://example.com/video", "Needs Review"), "Video link needs review")
		self.assertEqual(training_centre.get_video_display_status("https://youtu.be/dQw4w9WgXcQ", "Published"), "Video available")

	def test_invalid_video_status_is_rejected(self):
		row = {
			"module_id": "bad-video-status",
			"title": "Bad Video Status",
			"role_group": "Doctor Operations",
			"short_description": "Invalid row used only by this test.",
			"markdown_path": "docs/training/veterinary_doctor_operations/glossary.md",
			"youtube_url": "",
			"video_title": "Bad Video Status",
			"video_status": "Draft",
			"status": "Published",
			"order": 99,
		}

		with patch("vetedge.services.training_centre.frappe.throw", side_effect=frappe.ValidationError):
			self.assertRaises(frappe.ValidationError, training_centre.normalize_manifest_row, row)

	def test_manifest_ids_paths_and_role_groups_are_release_safe(self):
		modules = training_centre.load_training_manifest()
		module_ids = [module["module_id"] for module in modules]

		self.assertEqual(len(module_ids), len(set(module_ids)))
		self.assertTrue(all(module["role_group"] in training_centre.ROLE_GROUP_ROLES for module in modules))
		self.assertTrue(all(training_centre.resolve_markdown_path(module).exists() for module in modules))

	def test_invalid_role_group_is_rejected(self):
		row = {
			"module_id": "bad-role-group",
			"title": "Bad Role Group",
			"role_group": "Uncontrolled Access",
			"short_description": "Invalid row used only by this test.",
			"markdown_path": "docs/training/veterinary_doctor_operations/glossary.md",
			"youtube_url": "",
			"video_title": "Bad Role Group",
			"video_status": "Not Recorded",
			"status": "Published",
			"order": 99,
		}

		with patch("vetedge.services.training_centre.frappe.throw", side_effect=frappe.ValidationError):
			self.assertRaises(frappe.ValidationError, training_centre.normalize_manifest_row, row)
