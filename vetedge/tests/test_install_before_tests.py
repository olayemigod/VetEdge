from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import vetedge.install as install


class TestInstallBeforeTests(TestCase):
	def test_standard_price_lists_are_normalized_only_when_testing(self):
		updates = []

		def exists(doctype, name=None):
			return (doctype, name) in {
				("DocType", "Price List"),
				("Price List", "Standard Buying"),
				("Price List", "Standard Selling"),
			}

		frappe_stub = SimpleNamespace(
			in_test=True,
			db=SimpleNamespace(
				exists=Mock(side_effect=exists),
				set_value=Mock(side_effect=lambda *args, **kwargs: updates.append((args, kwargs))),
			),
		)

		with patch.object(install, "frappe", frappe_stub):
			install.ensure_erpnext_test_price_lists_are_idempotent()

		self.assertEqual(
			updates,
			[
				(
					(
						"Price List",
						"Standard Buying",
						{"enabled": 1, "buying": 1, "selling": 0, "currency": "INR"},
					),
					{"update_modified": False},
				),
				(
					(
						"Price List",
						"Standard Selling",
						{"enabled": 1, "buying": 0, "selling": 1, "currency": "INR"},
					),
					{"update_modified": False},
				),
			],
		)

	def test_standard_price_lists_are_not_touched_outside_test_runner(self):
		frappe_stub = SimpleNamespace(
			in_test=False,
			db=SimpleNamespace(exists=Mock(return_value=True), set_value=Mock()),
		)

		with patch.object(install, "frappe", frappe_stub):
			install.ensure_erpnext_test_price_lists_are_idempotent()

		frappe_stub.db.set_value.assert_not_called()
