from __future__ import annotations

from vetedge.services.company_context_compat import repair_resolvable_company_context


def execute() -> None:
	repair_resolvable_company_context()
