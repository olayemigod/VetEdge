(function () {
	function setFilterReadOnly(filter, readOnly) {
		if (!filter) {
			return;
		}
		filter.df.read_only = readOnly ? 1 : 0;
		filter.refresh();
	}

	function applyContextToReport(queryReport, context) {
		if (!queryReport || !context) {
			return;
		}

		if (context.default_branch && queryReport.get_filter("branch")) {
			queryReport.set_filter_value("branch", context.default_branch);
		}

		if (context.practitioner && queryReport.get_filter("practitioner")) {
			queryReport.set_filter_value("practitioner", context.practitioner);
		}

		if (context.practitioner_locked && queryReport.get_filter("practitioner")) {
			setFilterReadOnly(queryReport.get_filter("practitioner"), true);
		}
	}

	window.vetedgeReportVisibility = {
		apply(queryReport, reportName) {
			frappe.call({
				method: "vetedge.services.report_visibility.get_visibility_context",
				args: {
					scope_name: reportName,
					scope_type: "report",
				},
				callback: function (r) {
					applyContextToReport(queryReport, r.message || {});
				},
			});
		},

		applyDashboard(branchField, dashboardKey) {
			if (!branchField) {
				return;
			}
			frappe.call({
				method: "vetedge.services.report_visibility.get_visibility_context",
				args: {
					scope_name: dashboardKey,
					scope_type: "dashboard",
				},
				callback: function (r) {
					const context = r.message || {};
					if (context.default_branch && !branchField.get_value()) {
						branchField.set_value(context.default_branch);
					}
				},
			});
		},
	};
})();
