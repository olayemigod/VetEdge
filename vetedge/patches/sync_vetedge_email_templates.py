from __future__ import annotations

from vetedge.setup.email_templates import sync_vetedge_email_templates


def execute() -> None:
	sync_vetedge_email_templates()
