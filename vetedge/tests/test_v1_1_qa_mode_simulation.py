# -*- coding: utf-8 -*-
"""
VetEdge Platform V1.1 QA — Mode Simulation Tests

Verifies all edge_platform_mode / coreedge_required combinations produce
the correct resolution of: is_coreedge_enabled, should_show_coreedge_controls,
should_fail_closed_when_coreedge_missing, and sidebar visibility.

Run via:
  bench --site vetedge.local run-tests --app vetedge --module vetedge.tests.test_v1_1_qa_mode_simulation
"""
from __future__ import annotations

import unittest
from unittest.mock import patch
import frappe

import vetedge.coreedge_adapter as _adapter
from vetedge.coreedge_adapter import (
    get_edge_platform_mode,
    is_coreedge_enabled,
    should_show_coreedge_controls,
    should_fail_closed_when_coreedge_missing,
    get_vetedge_product_app,
    get_visible_vetedge_sidebar_items,
)

SAMPLE_SIDEBAR = [
    {"label": "Veterinary Patient", "link_to": "Veterinary Patient"},
    {"label": "Platform Settings",  "link_to": "CoreEdge Settings"},
    {"label": "Product Activation", "link_to": "CoreEdge Product Activation"},
    {"label": "Veterinary Appointment", "link_to": "Veterinary Appointment"},
]
COREEDGE_LABELS = {"Platform Settings", "Product Activation"}
VET_LABELS = {"Veterinary Patient", "Veterinary Appointment"}


class TestV11QAModeSimulation(unittest.TestCase):
    """QA readiness check — VetEdge Platform V1.1 mode simulation."""

    def setUp(self):
        self._orig_conf = dict(frappe.conf)
        for k in ("edge_platform_mode", "coreedge_required", "edge_platform_product"):
            if k in frappe.conf:
                del frappe.conf[k]

    def tearDown(self):
        frappe.conf.clear()
        frappe.conf.update(self._orig_conf)

    # ── helpers ───────────────────────────────────────────────────────────

    def _resolve(self, ce_installed: bool):
        with patch.object(_adapter, "is_coreedge_available", return_value=ce_installed):
            mode   = get_edge_platform_mode()
            enabled = is_coreedge_enabled()
            show   = should_show_coreedge_controls()
            fail_c = should_fail_closed_when_coreedge_missing()
            visible = {i["label"] for i in get_visible_vetedge_sidebar_items(SAMPLE_SIDEBAR)}
        return mode, enabled, show, fail_c, visible

    # ── 1. STANDALONE — no site_config keys ──────────────────────────────

    def test_01_standalone_no_config_ce_installed(self):
        """standalone (no keys set) with CE installed → controls hidden, VetEdge links visible."""
        mode, enabled, show, fail_c, vis = self._resolve(ce_installed=True)
        self.assertEqual(mode, "standalone")
        self.assertFalse(enabled)
        self.assertFalse(show)
        self.assertFalse(fail_c)
        self.assertFalse(COREEDGE_LABELS & vis, "CoreEdge links should be hidden")
        self.assertTrue(VET_LABELS.issubset(vis), "VetEdge links should be visible")

    def test_02_standalone_no_config_ce_missing(self):
        """standalone (no keys set) with CE missing → controls hidden, no fail-close."""
        mode, enabled, show, fail_c, vis = self._resolve(ce_installed=False)
        self.assertEqual(mode, "standalone")
        self.assertFalse(enabled)
        self.assertFalse(show)
        self.assertFalse(fail_c)
        self.assertFalse(COREEDGE_LABELS & vis)

    def test_03_standalone_explicit_ce_installed(self):
        """edge_platform_mode = standalone (explicit) → same as no key."""
        frappe.conf.edge_platform_mode = "standalone"
        mode, enabled, show, fail_c, vis = self._resolve(ce_installed=True)
        self.assertEqual(mode, "standalone")
        self.assertFalse(enabled)
        self.assertFalse(show)
        self.assertFalse(COREEDGE_LABELS & vis)

    # ── 2. SHARED_HOSTED ─────────────────────────────────────────────────

    def test_04_shared_hosted_ce_installed(self):
        """edge_platform_mode = shared_hosted + CE installed → controls shown, fail-closed."""
        frappe.conf.edge_platform_mode = "shared_hosted"
        mode, enabled, show, fail_c, vis = self._resolve(ce_installed=True)
        self.assertEqual(mode, "shared_hosted")
        self.assertTrue(enabled)
        self.assertTrue(show)
        self.assertTrue(fail_c)
        self.assertTrue(COREEDGE_LABELS.issubset(vis), "CoreEdge links must be visible")
        self.assertTrue(VET_LABELS.issubset(vis), "VetEdge links must remain visible")

    def test_05_shared_hosted_ce_missing(self):
        """edge_platform_mode = shared_hosted + CE missing → enabled+fail-closed, controls hidden (CE unavailable)."""
        frappe.conf.edge_platform_mode = "shared_hosted"
        mode, enabled, show, fail_c, vis = self._resolve(ce_installed=False)
        self.assertTrue(enabled)
        self.assertFalse(show, "Controls must be hidden when CE is not installed even if required")
        self.assertTrue(fail_c)
        self.assertFalse(COREEDGE_LABELS & vis)

    # ── 3. WHITE_LABEL ───────────────────────────────────────────────────

    def test_06_white_label_ce_installed(self):
        """edge_platform_mode = white_label + CE installed → same behavior as shared_hosted."""
        frappe.conf.edge_platform_mode = "white_label"
        mode, enabled, show, fail_c, vis = self._resolve(ce_installed=True)
        self.assertEqual(mode, "white_label")
        self.assertTrue(enabled)
        self.assertTrue(show)
        self.assertTrue(fail_c)
        self.assertTrue(COREEDGE_LABELS.issubset(vis))

    def test_07_white_label_ce_missing(self):
        """edge_platform_mode = white_label + CE missing → enabled+fail-closed, controls hidden."""
        frappe.conf.edge_platform_mode = "white_label"
        mode, enabled, show, fail_c, vis = self._resolve(ce_installed=False)
        self.assertTrue(enabled)
        self.assertFalse(show)
        self.assertTrue(fail_c)

    # ── 4. coreedge_required overrides ───────────────────────────────────

    def test_08_coreedge_required_overrides_standalone_when_ce_missing(self):
        """coreedge_required=1 + standalone mode + CE missing → enabled and fail-closed."""
        frappe.conf.edge_platform_mode = "standalone"
        frappe.conf.coreedge_required = 1
        mode, enabled, show, fail_c, vis = self._resolve(ce_installed=False)
        self.assertTrue(enabled, "coreedge_required must override standalone")
        self.assertTrue(fail_c)

    def test_09_coreedge_required_no_mode_ce_installed(self):
        """coreedge_required=1, no mode, CE installed → enabled, controls shown."""
        frappe.conf.coreedge_required = 1
        mode, enabled, show, fail_c, vis = self._resolve(ce_installed=True)
        self.assertTrue(enabled)
        self.assertTrue(show)

    # ── 5. Unsupported / unknown mode → fail-safe ─────────────────────────

    def test_10_unsupported_mode_fails_safe_to_required(self):
        """Unknown mode value → fail-safe: treated as enabled and fail-closed."""
        frappe.conf.edge_platform_mode = "enterprise_cloud"
        mode, enabled, show, fail_c, vis = self._resolve(ce_installed=False)
        self.assertEqual(mode, "enterprise_cloud")
        self.assertTrue(enabled, "Unsupported mode must fail-safe to required")
        self.assertTrue(fail_c)

    # ── 6. Product app defaults ───────────────────────────────────────────

    def test_11_product_app_defaults_to_vetedge(self):
        """edge_platform_product unset/blank → 'VetEdge'."""
        self.assertEqual(get_vetedge_product_app(), "VetEdge")
        frappe.conf.edge_platform_product = ""
        self.assertEqual(get_vetedge_product_app(), "VetEdge")

    def test_12_product_app_respects_site_config(self):
        """edge_platform_product = 'ClinicEdge' → 'ClinicEdge'."""
        frappe.conf.edge_platform_product = "ClinicEdge"
        self.assertEqual(get_vetedge_product_app(), "ClinicEdge")

    # ── 7. Schema guard — no banned fields in Veterinary Settings ─────────

    def test_13_veterinary_settings_has_no_banned_coreedge_fields(self):
        """Veterinary Settings DocType must not contain removed platform fields."""
        meta = frappe.get_meta("Veterinary Settings")
        fieldnames = {f.fieldname for f in meta.fields}
        banned = [
            "deployment_mode",
            "enable_coreedge_platform",
            "fail_closed_when_coreedge_missing",
            "coreedge_product_app",
            "coreedge_platform_section",
        ]
        for field in banned:
            self.assertNotIn(field, fieldnames, f"Field '{field}' must have been removed from Veterinary Settings")

    def test_14_veterinary_settings_still_has_clinical_fields(self):
        """Core clinical fields must still be present in Veterinary Settings."""
        meta = frappe.get_meta("Veterinary Settings")
        fieldnames = {f.fieldname for f in meta.fields}
        required = [
            "enable_vetedge",
            "enable_consultations",
            "enable_boarding",
            "enable_vaccination",
            "enable_vitals",
            "enable_grooming",
        ]
        for field in required:
            self.assertIn(field, fieldnames, f"Clinical field '{field}' must still be present")

    # ── 8. No stale tabSingles rows ────────────────────────────────────────

    def test_15_no_stale_coreedge_rows_in_singles(self):
        """Migration patch must have cleaned stale coreedge fields from tabSingles."""
        stale_fields = (
            "deployment_mode",
            "enable_coreedge_platform",
            "fail_closed_when_coreedge_missing",
            "coreedge_product_app",
            "coreedge_platform_section",
        )
        rows = frappe.db.sql(
            "SELECT field FROM tabSingles WHERE doctype='Veterinary Settings' AND field IN %s",
            (stale_fields,),
            as_dict=True,
        )
        self.assertEqual(rows, [], f"Stale coreedge fields found in tabSingles: {[r['field'] for r in rows]}")
