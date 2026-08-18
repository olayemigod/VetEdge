from __future__ import annotations

from typing import Any

from frappe.utils import cint

from vetedge.services import appointment_edgeui

CANDIDATE_POOL_MAX = 100


def _shared_ranker():
	try:
		from edgesuite_ui.search_ranking import rank_search_records
	except (ImportError, ModuleNotFoundError):
		return None
	return rank_search_records


def _search_values(option: dict[str, Any]) -> dict[str, Any]:
	raw = option.get("raw") if isinstance(option.get("raw"), dict) else {}
	identifiers = [option.get("value")]
	search_text = [option.get("label"), option.get("description")]
	for fieldname in ("microchip_id", "mobile_no", "email_id"):
		if raw.get(fieldname):
			identifiers.append(raw.get(fieldname))
	for fieldname in (
		"patient_name",
		"primary_owner",
		"species",
		"breed",
		"customer_name",
		"species_name",
		"breed_name",
	):
		if raw.get(fieldname):
			search_text.append(raw.get(fieldname))
	return {
		**option,
		"identifiers": identifiers,
		"search_text": search_text,
	}


def _rank(options: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
	ranker = _shared_ranker()
	if not ranker:
		return options[:limit]
	prepared = [_search_values(option) for option in options]
	ranked = ranker(
		prepared,
		query,
		exact_fields=("identifiers",),
		search_fields=("label", "description", "search_text"),
		limit=limit,
	)
	return [
		{key: value for key, value in option.items() if key not in {"identifiers", "search_text"}}
		for option in ranked
	]


def search_appointment_link(
	field: str,
	txt: str = "",
	context: str | dict | None = None,
	start: int = 0,
	page_length: int = 20,
) -> list[dict]:
	"""Use the shared EdgeSuite fuzzy ranker without changing appointment permissions or filters."""
	query = str(txt or "").strip()
	start_value = max(cint(start), 0)
	limit = min(max(cint(page_length) or 20, 1), appointment_edgeui.PAGE_LENGTH_MAX)
	if not query or start_value or not _shared_ranker():
		return appointment_edgeui.search_appointment_link(
			field=field,
			txt=query,
			context=context,
			start=start_value,
			page_length=limit,
		)

	candidate_limit = min(CANDIDATE_POOL_MAX, max(limit * 5, limit))
	candidates = appointment_edgeui.search_appointment_link(
		field=field,
		txt="",
		context=context,
		start=0,
		page_length=candidate_limit,
	)
	return _rank(candidates, query, limit)
