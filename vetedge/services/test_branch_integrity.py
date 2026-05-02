import unittest
from types import SimpleNamespace

import frappe

from vetedge.services import branch_integrity


class _Meta:
    def __init__(self, labels=None):
        self._labels = labels or {}

    def has_field(self, fieldname):
        return True

    def get_label(self, fieldname):
        return self._labels.get(fieldname)


class _Doc:
    def __init__(self, doctype, values=None):
        self.doctype = doctype
        self._values = values or {}
        self.meta = _Meta({"service_branch": "Service Branch", "branch": "Branch"})

    def get(self, fieldname):
        return self._values.get(fieldname)

    def __getattr__(self, item):
        return self._values.get(item)


class TestBranchIntegrity(unittest.TestCase):
    def test_branch_required_doctype_enforced(self):
        doc = _Doc("Veterinary Consultation", {"service_branch": ""})
        with self.assertRaises(frappe.ValidationError):
            branch_integrity.enforce_branch_integrity(doc)

    def test_branch_required_doctype_passes_when_set(self):
        doc = _Doc("Veterinary Consultation", {"service_branch": "Main"})
        branch_integrity.enforce_branch_integrity(doc)

    def test_vetedge_invoice_detection(self):
        doc = _Doc("Sales Invoice", {"branch": "", "remarks": "Grooming billing for GROOM-0001"})
        self.assertTrue(branch_integrity._is_vetedge_invoice(doc))
        with self.assertRaises(frappe.ValidationError):
            branch_integrity.enforce_vetedge_invoice_branch(doc)

    def test_non_vetedge_invoice_is_ignored(self):
        doc = _Doc("Sales Invoice", {"branch": "", "remarks": "General invoice"})
        branch_integrity.enforce_vetedge_invoice_branch(doc)

    def test_vetedge_stock_entry_detection(self):
        doc = _Doc("Stock Entry", {"branch": "", "remarks": "Vaccination stock issue for VAC-0001"})
        self.assertTrue(branch_integrity._is_vetedge_stock_entry(doc))
        with self.assertRaises(frappe.ValidationError):
            branch_integrity.enforce_vetedge_stock_entry_branch(doc)


if __name__ == "__main__":
    unittest.main()
