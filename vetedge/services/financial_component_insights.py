from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cstr, flt, getdate, nowdate
from vetedge.services.financial_insights import _build_trend, get_financial_insights
from vetedge.services.financial_reporting_dataset import build_financial_dataset

CONSULTATION_SERVICE_INCOME = "Consultation Service Income"
TREATMENT_INCOME = "Treatment Income"


def _component_totals(dataset: list[dict], value_field: str = "amount") -> dict[str, float]:
	totals: dict[str, float] = defaultdict(float)
	for row in dataset:
		if int(row.get("docstatus") or 0) != 1:
			continue
		components = row.get("revenue_components") or []
		if not components:
			category = cstr(row.get("service_source") or "General Income").strip() or "General Income"
			if not category.endswith("Income"):
				category = f"{category} Income"
			fallback_field = "outstanding_amount" if value_field == "outstanding_amount" else "grand_total"
			totals[category] += flt(row.get(fallback_field))
			continue
		for component in components:
			category = cstr(component.get("category") or "Other Income").strip() or "Other Income"
			totals[category] += flt(component.get(value_field))
	return dict(totals)


def _previous_period_filters(filters: frappe._dict) -> frappe._dict:
	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or add_days(to_date, -30))
	duration = (to_date - from_date).days + 1
	previous_to = from_date - timedelta(days=1)
	previous_from = previous_to - timedelta(days=duration - 1)
	previous = frappe._dict(filters.copy())
	previous.from_date = cstr(previous_from)
	previous.to_date = cstr(previous_to)
	return previous


def _income_card(
	card_id: str,
	title: str,
	category: str,
	current: dict[str, float],
	previous: dict[str, float],
	branch: str | None,
) -> dict:
	value = flt(current.get(category))
	previous_value = flt(previous.get(category))
	filters = {"income_category": category}
	if branch:
		filters["branch"] = branch
	return {
		"id": card_id,
		"value_type": "currency",
		"title": _(title),
		"label": _(title),
		"value": value,
		"secondary_value": _("Separated from other clinical income"),
		"trend": _build_trend(value, previous_value),
		"action": {"type": "report", "target": "Revenue Summary", "filters": filters},
		"tooltip": _("Submitted invoice revenue allocated from Veterinary invoice items and service links."),
		"severity": "info",
		"category": "income_source",
	}


def _composition_cards(totals: dict[str, float]) -> list[dict]:
	total = sum(totals.values())
	cards = []
	for category, value in totals.items():
		share = (value / total * 100.0) if total else 0.0
		cards.append(
			{
				"id": f"income_{frappe.scrub(category)}",
				"title": category,
				"label": category,
				"value": value,
				"value_type": "currency",
				"share_percent": round(share, 1),
				"secondary_value": _("{0}% of Revenue").format(round(share, 1)),
				"trend": None,
				"tooltip": _("Submitted revenue allocated to {0}.").format(category),
				"severity": "info",
				"category": "composition",
			}
		)
	return sorted(cards, key=lambda row: row.get("value") or 0, reverse=True)


def get_component_financial_insights(filters=None) -> dict:
	"""Extend the existing financial insight payload with line-level income truth."""
	filters = frappe._dict(filters or {})
	payload = get_financial_insights(filters)
	current_dataset = build_financial_dataset(filters)
	previous_dataset = build_financial_dataset(_previous_period_filters(filters))
	current_totals = _component_totals(current_dataset)
	previous_totals = _component_totals(previous_dataset)
	outstanding_totals = _component_totals(current_dataset, "outstanding_amount")

	payload["dataset"] = current_dataset
	payload["revenue_composition"] = _composition_cards(current_totals)
	payload["kpis"] = [
		*payload.get("kpis", []),
		_income_card(
			"consultation_service_income",
			"Consultation Service Income",
			CONSULTATION_SERVICE_INCOME,
			current_totals,
			previous_totals,
			filters.get("branch"),
		),
		_income_card(
			"treatment_income",
			"Treatment Income",
			TREATMENT_INCOME,
			current_totals,
			previous_totals,
			filters.get("branch"),
		),
	]

	outstanding = payload.get("outstanding_breakdowns") or {}
	outstanding["by_service"] = [
		{"name": category, "value": value}
		for category, value in sorted(outstanding_totals.items(), key=lambda row: row[1], reverse=True)
	]
	payload["outstanding_breakdowns"] = outstanding

	if current_totals:
		dominant_category, dominant_value = max(current_totals.items(), key=lambda row: row[1])
		total_revenue = sum(current_totals.values())
		share = (dominant_value / total_revenue * 100.0) if total_revenue else 0.0
		for indicator in payload.get("health_indicators", []):
			if indicator.get("id") == "revenue_concentration":
				indicator["secondary_value"] = _("Income source: {0} ({1}%)").format(
					dominant_category,
					round(share, 1),
				)
				break

	return payload
