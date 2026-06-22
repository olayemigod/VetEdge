# -*- coding: utf-8 -*-
from __future__ import annotations

import frappe

def require_vetedge_platform_access(
	action: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> None:
	"""
	Thin service-layer wrapper around coreedge_adapter.require_vetedge_access.
	Service modules must import from this module, not directly from coreedge_adapter.
	"""
	from vetedge.coreedge_adapter import require_vetedge_access
	try:
		require_vetedge_access(
			action=action,
			reference_doctype=reference_doctype,
			reference_name=reference_name
		)
	except TypeError:
		# If the require_vetedge_access doesn't support kwargs in some environments, fall back gracefully.
		require_vetedge_access()
