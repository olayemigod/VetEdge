# -*- coding: utf-8 -*-
from __future__ import annotations

import frappe
from frappe import _


def require_vetedge_platform_access(
	action: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> None:
	"""Enforce the selected operator-controlled platform authority.

	Remote authority never falls back to a locally installed CoreEdge app. This prevents
	a product site from bypassing a central suspension or using stale local platform data.
	Legacy authority remains available only as the V3.0B migration path.
	"""
	from vetedge.platform_client import (
		RemotePlatformAccessDenied,
		RemotePlatformAuthenticationError,
		RemotePlatformConfigurationError,
		RemotePlatformError,
		RemotePlatformProtocolError,
		RemotePlatformUnavailableError,
		is_remote_platform_requested,
		require_remote_platform_access,
	)

	if is_remote_platform_requested():
		try:
			require_remote_platform_access(
				action=action,
				reference_doctype=reference_doctype,
				reference_name=reference_name,
			)
			return
		except RemotePlatformAccessDenied as exc:
			frappe.throw(
				str(exc),
				exc=frappe.PermissionError,
				title=_("Platform Access Required"),
			)
		except RemotePlatformConfigurationError as exc:
			_log_remote_error(exc)
			frappe.throw(
				_("Platform access has not been configured for this site. Contact your system administrator."),
				exc=frappe.PermissionError,
				title=_("Platform Connection Required"),
			)
		except RemotePlatformAuthenticationError as exc:
			_log_remote_error(exc)
			frappe.throw(
				_("The platform could not authenticate this product site. Contact your system administrator."),
				exc=frappe.PermissionError,
				title=_("Platform Connection Required"),
			)
		except (RemotePlatformUnavailableError, RemotePlatformProtocolError) as exc:
			_log_remote_error(exc)
			frappe.throw(
				_("Platform access could not be verified. Try again or contact your system administrator."),
				exc=frappe.PermissionError,
				title=_("Platform Connection Required"),
			)
		except RemotePlatformError as exc:
			_log_remote_error(exc)
			frappe.throw(
				_("Platform access could not be verified."),
				exc=frappe.PermissionError,
				title=_("Platform Connection Required"),
			)

	# V3.0B migration path: preserve the existing local adapter until the operator
	# provisions the site's central service client and selects remote authority.
	from vetedge.coreedge_adapter import require_vetedge_access

	try:
		require_vetedge_access(
			action=action,
			reference_doctype=reference_doctype,
			reference_name=reference_name,
		)
	except TypeError:
		# Backward compatibility for older CoreEdge adapter signatures.
		require_vetedge_access()


def _log_remote_error(exc: Exception) -> None:
	try:
		frappe.logger("vetedge.platform").warning(
			"Remote platform gate failed: %s: %s",
			exc.__class__.__name__,
			str(exc),
		)
	except Exception:
		pass
