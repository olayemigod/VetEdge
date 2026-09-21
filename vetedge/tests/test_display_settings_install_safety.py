from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from vetedge.setup import display_settings


class TestDisplaySettingsInstallSafety(TestCase):
	def test_date_format_update_uses_single_value_write_without_document_save(self):
		clear_cache = Mock()
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=Mock(return_value=True),
				get_single_value=Mock(return_value="yyyy-mm-dd"),
				set_single_value=Mock(),
			),
			clear_cache=clear_cache,
		)

		with patch.object(display_settings, "frappe", frappe_stub):
			changed = display_settings.ensure_vetedge_date_format()

		self.assertTrue(changed)
		frappe_stub.db.set_single_value.assert_called_once_with(
			"System Settings",
			"date_format",
			display_settings.VETEDGE_DATE_FORMAT,
			update_modified=False,
		)
		clear_cache.assert_called_once_with()

	def test_date_format_update_is_idempotent(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=Mock(return_value=True),
				get_single_value=Mock(return_value=display_settings.VETEDGE_DATE_FORMAT),
				set_single_value=Mock(),
			),
			clear_cache=Mock(),
		)

		with patch.object(display_settings, "frappe", frappe_stub):
			changed = display_settings.ensure_vetedge_date_format()

		self.assertFalse(changed)
		frappe_stub.db.set_single_value.assert_not_called()
		frappe_stub.clear_cache.assert_not_called()

	def test_date_format_update_skips_when_system_settings_doctype_is_unavailable(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=Mock(return_value=False),
				get_single_value=Mock(),
				set_single_value=Mock(),
			),
			clear_cache=Mock(),
		)

		with patch.object(display_settings, "frappe", frappe_stub):
			changed = display_settings.ensure_vetedge_date_format()

		self.assertFalse(changed)
		frappe_stub.db.get_single_value.assert_not_called()
		frappe_stub.db.set_single_value.assert_not_called()
