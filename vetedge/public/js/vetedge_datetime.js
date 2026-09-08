(function (root) {
	"use strict";

	const DISPLAY_DATE_FORMAT = "DD-MM-YYYY";
	const DISPLAY_DATETIME_FORMAT = "DD-MM-YYYY HH:mm";
	const ISO_PARTS = /^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;
	const DISPLAY_PARTS = /^(\d{2})-(\d{2})-(\d{4})(?:\s(\d{2}):(\d{2}))?$/;

	function pad(value) {
		return String(value).padStart(2, "0");
	}

	function asParts(value, includeTime) {
		if (value === null || value === undefined || value === "") return null;

		if (value instanceof Date && !Number.isNaN(value.getTime())) {
			return {
				year: value.getFullYear(),
				month: value.getMonth() + 1,
				day: value.getDate(),
				hour: includeTime ? value.getHours() : 0,
				minute: includeTime ? value.getMinutes() : 0,
			};
		}

		let text = typeof value?.format === "function"
			? value.format(includeTime ? "YYYY-MM-DD HH:mm:ss" : "YYYY-MM-DD")
			: String(value).trim();

		if (includeTime && root.frappe?.datetime?.convert_to_user_tz) {
			try {
				const converted = root.frappe.datetime.convert_to_user_tz(text);
				if (converted) {
					if (converted instanceof Date && !Number.isNaN(converted.getTime())) {
						return {
							year: converted.getFullYear(), month: converted.getMonth() + 1, day: converted.getDate(),
							hour: converted.getHours(), minute: converted.getMinutes(),
						};
					}
					text = typeof converted.format === "function"
						? converted.format("YYYY-MM-DD HH:mm:ss")
						: String(converted).trim();
				}
			} catch (_error) {
				// Keep the server value when the Frappe timezone helper cannot parse it.
			}
		}

		const iso = text.match(ISO_PARTS);
		if (iso) {
			return {
				year: Number(iso[1]),
				month: Number(iso[2]),
				day: Number(iso[3]),
				hour: Number(iso[4] || 0),
				minute: Number(iso[5] || 0),
			};
		}

		const display = text.match(DISPLAY_PARTS);
		if (display) {
			return {
				year: Number(display[3]),
				month: Number(display[2]),
				day: Number(display[1]),
				hour: Number(display[4] || 0),
				minute: Number(display[5] || 0),
			};
		}

		return null;
	}

	function formatDate(value, fallback) {
		const parts = asParts(value, false);
		if (!parts) return fallback !== undefined ? fallback : (value == null ? "" : String(value));
		return `${pad(parts.day)}-${pad(parts.month)}-${parts.year}`;
	}

	function formatDateTime(value, fallback) {
		const parts = asParts(value, true);
		if (!parts) return fallback !== undefined ? fallback : (value == null ? "" : String(value));
		return `${pad(parts.day)}-${pad(parts.month)}-${parts.year} ${pad(parts.hour)}:${pad(parts.minute)}`;
	}

	function formatByFieldtype(value, fieldtype, fallback) {
		const type = String(fieldtype || "").toLowerCase();
		if (type === "datetime") return formatDateTime(value, fallback);
		if (type === "date") return formatDate(value, fallback);
		return value;
	}

	function inferredFieldtype(value, column) {
		const declared = String(column?.fieldtype || column?.type || "").toLowerCase();
		if (declared) return declared;
		const text = value == null ? "" : String(value).trim();
		if (!ISO_PARTS.test(text)) return "";
		const fieldname = String(column?.fieldname || column?.key || "").toLowerCase();
		if (!/(^|_)(date|datetime|timestamp|creation|modified)$|_date$|_datetime$|_on$/.test(fieldname)) return "";
		return /[T\s]\d{2}:\d{2}/.test(text) ? "datetime" : "date";
	}

	function formatCell(value, column) {
		if (value === null || value === undefined || value === "") return "—";
		return formatByFieldtype(value, inferredFieldtype(value, column), String(value));
	}

	function formatChartLabel(value) {
		if (typeof value !== "string" || !ISO_PARTS.test(value.trim())) return value;
		return value.includes("T") || value.includes(" ") ? formatDateTime(value) : formatDate(value);
	}

	function formatChartData(data) {
		if (!data || !Array.isArray(data.labels)) return data;
		return { ...data, labels: data.labels.map(formatChartLabel) };
	}

	function reportFormatter(value, row, column, data, defaultFormatter) {
		const type = String(column?.fieldtype || "").toLowerCase();
		if (type === "date" || type === "datetime") return formatByFieldtype(value, type, "");
		return typeof defaultFormatter === "function"
			? defaultFormatter(value, row, column, data)
			: value;
	}

	root.VetEdgeDateTime = Object.freeze({
		DISPLAY_DATE_FORMAT,
		DISPLAY_DATETIME_FORMAT,
		formatDate,
		formatDateTime,
		formatByFieldtype,
		inferredFieldtype,
		formatCell,
		formatChartLabel,
		formatChartData,
		reportFormatter,
	});

	if (typeof module !== "undefined" && module.exports) module.exports = root.VetEdgeDateTime;
})(typeof window !== "undefined" ? window : globalThis);
