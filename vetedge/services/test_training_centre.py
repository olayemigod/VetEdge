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
		self.assertEqual(modules[0]["module_id"], "doctor-overview")
		self.assertTrue(all(module["status"] == "Published" for module in modules))

	def test_invalid_module_id_is_rejected(self):
		with patch("vetedge.services.training_centre.frappe.throw", side_effect=frappe.DoesNotExistError):
			self.assertRaises(frappe.DoesNotExistError, training_centre.get_module_by_id, "not-a-module")

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

	def test_role_filter_allows_doctor_operations_for_doctor(self):
		with patch("vetedge.services.training_centre.get_user_training_roles", return_value={"VetEdge Doctor"}):
			modules = training_centre.get_visible_training_modules(user="doctor@example.com")

		self.assertTrue(modules)
		self.assertTrue(all(module["role_group"] == "Doctor Operations" for module in modules))

	def test_role_filter_blocks_unrelated_role(self):
		with patch("vetedge.services.training_centre.get_user_training_roles", return_value={"VetEdge Groomer"}):
			modules = training_centre.get_visible_training_modules(user="groomer@example.com")

		self.assertEqual(modules, [])

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
		self.assertEqual(training_centre.get_video_status(""), "Video coming soon")
		self.assertEqual(training_centre.get_video_status("https://example.com/video"), "Video link needs review")
