(function () {
	frappe.EdgeSuite = frappe.EdgeSuite || {};
	
	const DateRanges = {
		earliestDate: "2020-01-01",
		
		init() {
			frappe.call({
				method: "vetedge.services.report_visibility.get_earliest_transaction_date",
				callback: (r) => {
					if (r.message) {
						this.earliestDate = r.message;
					}
				}
			});
		},
		
		getDefaultPreset() {
			return "this_month";
		},
		
		getRange(preset) {
			let start, end;
			const today = moment();
			switch (preset) {
				case "today":
					start = today.clone().startOf("day");
					end = today.clone().endOf("day");
					break;
				case "yesterday":
					start = today.clone().subtract(1, "days").startOf("day");
					end = today.clone().subtract(1, "days").endOf("day");
					break;
				case "this_week":
					start = today.clone().startOf("week");
					end = today.clone().endOf("week");
					break;
				case "last_week":
					start = today.clone().subtract(1, "weeks").startOf("week");
					end = today.clone().subtract(1, "weeks").endOf("week");
					break;
				case "this_month":
					start = today.clone().startOf("month");
					end = today.clone().endOf("month");
					break;
				case "last_month":
					start = today.clone().subtract(1, "months").startOf("month");
					end = today.clone().subtract(1, "months").endOf("month");
					break;
				case "this_quarter":
					start = today.clone().startOf("quarter");
					end = today.clone().endOf("quarter");
					break;
				case "last_quarter":
					start = today.clone().subtract(1, "quarters").startOf("quarter");
					end = today.clone().subtract(1, "quarters").endOf("quarter");
					break;
				case "this_year":
					start = today.clone().startOf("year");
					end = today.clone().endOf("year");
					break;
				case "last_year":
					start = today.clone().subtract(1, "years").startOf("year");
					end = today.clone().subtract(1, "years").endOf("year");
					break;
				case "full_history":
					return {
						start: this.earliestDate,
						end: today.clone().endOf("day").format("YYYY-MM-DD")
					};
				default:
					return null;
			}
			return {
				start: start.format("YYYY-MM-DD"),
				end: end.format("YYYY-MM-DD")
			};
		},
		
		getPreviousRange(preset, currentRange = null) {
			let range = currentRange;
			if (!range && preset && preset !== "custom") {
				range = this.getRange(preset);
			}
			if (!range || !range.start || !range.end) {
				return null;
			}
			const start = moment(range.start);
			const end = moment(range.end);
			const durationDays = end.diff(start, "days") + 1;
			const prevEnd = start.clone().subtract(1, "days");
			const prevStart = prevEnd.clone().subtract(durationDays - 1, "days");
			return {
				start: prevStart.format("YYYY-MM-DD"),
				end: prevEnd.format("YYYY-MM-DD")
			};
		},
		
		getOptions() {
			return [
				{ value: "this_month", label: __("This Month") },
				{ value: "today", label: __("Today") },
				{ value: "yesterday", label: __("Yesterday") },
				{ value: "this_week", label: __("This Week") },
				{ value: "last_week", label: __("Last Week") },
				{ value: "last_month", label: __("Last Month") },
				{ value: "this_quarter", label: __("This Quarter") },
				{ value: "last_quarter", label: __("Last Quarter") },
				{ value: "this_year", label: __("This Year") },
				{ value: "last_year", label: __("Last Year") },
				{ value: "full_history", label: __("Full History") },
				{ value: "custom", label: __("-- Custom Range --") }
			];
		}
	};
	
	frappe.EdgeSuite.DateRanges = DateRanges;
	
	// Auto-initialize on load
	$(document).ready(() => {
		DateRanges.init();
	});
})();
