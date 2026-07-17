from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import billing_core, master_pricing


class TestMasterPricing(TestCase):
	def test_sync_lab_test_price_creates_item_price(self):
		inserted = []
		frappe_stub = make_pricing_frappe_stub(
			existing_item_price=None,
			default_price_list="VetEdge Selling",
			price_list_currency="NGN",
			stock_uom="Nos",
			inserted=inserted,
		)
		doc = frappe._dict(linked_item="LAB-CBC", price_list="Clinic Selling", default_rate=2500)

		with patch("vetedge.services.master_pricing.frappe", frappe_stub):
			name = master_pricing.sync_master_item_price(doc, "linked_item", "default_rate")

		self.assertEqual(name, "ITEM-PRICE-NEW")
		self.assertEqual(inserted[0].item_code, "LAB-CBC")
		self.assertEqual(inserted[0].price_list, "Clinic Selling")
		self.assertEqual(inserted[0].price_list_rate, 2500)
		self.assertEqual(inserted[0].uom, "Nos")
		self.assertEqual(inserted[0].currency, "NGN")

	def test_sync_vaccine_price_updates_existing_item_price(self):
		set_value = Mock()
		frappe_stub = make_pricing_frappe_stub(
			existing_item_price="ITEM-PRICE-001",
			default_price_list="VetEdge Selling",
			price_list_currency="USD",
			stock_uom="Nos",
			set_value=set_value,
		)
		doc = frappe._dict(default_item="VAC-RABIES", price_list="Clinic Selling", default_price=3000)

		with patch("vetedge.services.master_pricing.frappe", frappe_stub):
			name = master_pricing.sync_master_item_price(doc, "default_item", "default_price")

		self.assertEqual(name, "ITEM-PRICE-001")
		set_value.assert_called_once_with(
			"Item Price",
			"ITEM-PRICE-001",
			{"price_list_rate": 3000, "selling": 1, "uom": "Nos", "currency": "USD"},
			update_modified=True,
		)

	def test_sync_treatment_price_uses_default_selling_price_list_when_missing(self):
		inserted = []
		frappe_stub = make_pricing_frappe_stub(
			existing_item_price=None,
			default_price_list="Default Selling",
			price_list_currency="GBP",
			stock_uom="Unit",
			inserted=inserted,
		)
		doc = frappe._dict(item="MED-001", default_price=1200)

		with patch("vetedge.services.master_pricing.frappe", frappe_stub):
			master_pricing.sync_master_item_price(doc, "item", "default_price")

		self.assertEqual(inserted[0].price_list, "Default Selling")
		self.assertEqual(inserted[0].item_code, "MED-001")

	def test_existing_item_price_update_does_not_insert_duplicate(self):
		get_doc = Mock()
		frappe_stub = make_pricing_frappe_stub(
			existing_item_price="ITEM-PRICE-001",
			default_price_list="Default Selling",
			price_list_currency="USD",
			stock_uom="Nos",
			get_doc=get_doc,
		)
		doc = frappe._dict(item="MED-001", price_list="Clinic Selling", default_price=1500)

		with patch("vetedge.services.master_pricing.frappe", frappe_stub):
			master_pricing.sync_master_item_price(doc, "item", "default_price")

		get_doc.assert_not_called()

	def test_billing_core_branch_price_list_stays_higher_priority_than_master(self):
		frappe_stub = make_billing_rate_frappe_stub(
			branch_price_list="Branch Selling",
			rates={"Branch Selling": 4000, "Master Selling": 2500, "Default Selling": 1000},
		)

		with patch("vetedge.services.billing_core.frappe", frappe_stub):
			rate = billing_core._get_item_selling_rate(
				"LAB-CBC",
				branch="Main Branch",
				master_price_list="Master Selling",
				uom="Nos",
			)

		self.assertEqual(rate, 4000)

	def test_billing_core_uses_master_price_list_after_branch_miss(self):
		frappe_stub = make_billing_rate_frappe_stub(
			branch_price_list="Branch Selling",
			rates={"Master Selling": 2500, "Default Selling": 1000},
		)

		with patch("vetedge.services.billing_core.frappe", frappe_stub):
			rate = billing_core._get_item_selling_rate(
				"LAB-CBC",
				branch="Main Branch",
				master_price_list="Master Selling",
				uom="Nos",
			)

		self.assertEqual(rate, 2500)


def make_pricing_frappe_stub(
	existing_item_price=None,
	default_price_list=None,
	price_list_currency=None,
	stock_uom=None,
	inserted=None,
	set_value=None,
	get_doc=None,
):
	inserted = inserted if inserted is not None else []
	set_value = set_value or Mock()

	def exists(doctype, name=None):
		if doctype == "DocType":
			return name in {"Item Price", "Veterinary Settings", "Selling Settings"}
		if doctype == "Price List":
			return bool(name)
		return True

	def get_single_value(doctype, fieldname):
		if doctype == "Veterinary Settings" and fieldname == "default_selling_price_list":
			return default_price_list
		if doctype == "Selling Settings" and fieldname == "selling_price_list":
			return "ERPNext Selling"
		return None

	def get_value(doctype, filters, fieldname=None, as_dict=False):
		if doctype == "Item Price":
			return existing_item_price
		if doctype == "Price List":
			return price_list_currency
		if doctype == "Item":
			return stock_uom
		return None

	class ItemPrice(SimpleNamespace):
		def insert(self):
			self.name = "ITEM-PRICE-NEW"
			inserted.append(self)

	return SimpleNamespace(
		db=SimpleNamespace(exists=exists, get_single_value=get_single_value, get_value=get_value, set_value=set_value),
		get_meta=lambda doctype: SimpleNamespace(
			get_field=lambda fieldname: fieldname in {"default_selling_price_list", "selling_price_list", "uom", "currency", "selling"}
		),
		get_doc=get_doc or (lambda values: ItemPrice(**values)),
		throw=Mock(side_effect=frappe.ValidationError),
		ValidationError=frappe.ValidationError,
	)


def make_billing_rate_frappe_stub(branch_price_list=None, rates=None):
	rates = rates or {}

	def exists(doctype, name=None):
		if doctype == "DocType":
			return name in {"Branch", "Item Price", "Veterinary Settings", "Selling Settings"}
		if doctype == "Price List":
			return name == "Standard Selling"
		return True

	def get_value(doctype, name, fieldname=None, as_dict=False):
		if doctype == "Branch":
			return branch_price_list
		if doctype == "Item":
			return 99
		return None

	def get_all(doctype, filters=None, fields=None, order_by=None):
		rate = rates.get((filters or {}).get("price_list"))
		if not rate:
			return []
		return [frappe._dict(name=f"PRICE-{filters['price_list']}", price_list_rate=rate, uom="Nos")]

	def get_single_value(doctype, fieldname):
		if doctype == "Veterinary Settings":
			return "Default Selling"
		if doctype == "Selling Settings":
			return "ERPNext Selling"
		return None

	return SimpleNamespace(
		db=SimpleNamespace(exists=exists, get_value=get_value, get_all=get_all, get_single_value=get_single_value),
		get_all=get_all,
		get_meta=lambda doctype: SimpleNamespace(
			get_field=lambda fieldname: fieldname
			in {"vetedge_price_list", "selling_price_list", "default_selling_price_list", "uom", "selling", "valid_from", "valid_upto"}
		),
	)
