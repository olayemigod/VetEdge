from __future__ import annotations

from frappe.utils import getdate, nowdate


def calculate_age_label(date_of_birth, reference_date=None) -> str:
	if not date_of_birth:
		return ""

	birth_date = getdate(date_of_birth)
	today = getdate(reference_date or nowdate())
	if birth_date > today:
		return ""

	years = today.year - birth_date.year
	months = today.month - birth_date.month
	days = today.day - birth_date.day

	if days < 0:
		months -= 1
		previous_month = today.month - 1 or 12
		previous_month_year = today.year if today.month > 1 else today.year - 1
		days += days_in_month(previous_month_year, previous_month)

	if months < 0:
		years -= 1
		months += 12

	parts = []
	if years:
		parts.append(format_unit(years, "year"))
	if months:
		parts.append(format_unit(months, "month"))
	if not parts:
		parts.append(format_unit(days, "day"))

	return " ".join(parts)


def days_in_month(year: int, month: int) -> int:
	if month == 12:
		next_month = getdate(f"{year + 1}-01-01")
	else:
		next_month = getdate(f"{year}-{month + 1:02d}-01")

	current_month = getdate(f"{year}-{month:02d}-01")
	return (next_month - current_month).days


def format_unit(value: int, unit: str) -> str:
	suffix = "" if value == 1 else "s"
	return f"{value} {unit}{suffix}"
