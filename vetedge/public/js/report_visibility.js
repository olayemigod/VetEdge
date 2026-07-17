// report_visibility.js
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

	class EdgeReportEnhancer {
		constructor(report, reportName) {
			this.report = report;
			this.reportName = reportName;
			this.init();
		}

		init() {
			this.setupDatePresets();
			this.hookSummaryRender();
		}

		setupDatePresets() {
			const report = this.report;
			const fromDate = report.get_filter("from_date");
			const toDate = report.get_filter("to_date");
			if (!fromDate || !toDate) return;

			const filterArea = report.page.page_form;
			if (!filterArea || filterArea.find(".edgesuite-date-presets-select").length) return;

			const optionsHtml = frappe.EdgeSuite.DateRanges.getOptions().map(opt => {
				return `<option value="${opt.value}">${opt.label}</option>`;
			}).join("");

			const presetsHtml = `
				<div class="edgesuite-date-presets-wrapper mr-2 d-inline-block" style="vertical-align: top; margin-top: 4px;">
					<label class="small text-muted" style="display: block; margin-bottom: 4px;">Date Preset</label>
					<select class="form-control input-sm edgesuite-date-presets-select" style="max-width: 140px; font-size: 0.85rem; height: 30px; border-radius: 4px;">
						${optionsHtml}
					</select>
				</div>
			`;
			$(presetsHtml).prependTo(filterArea);

			// Default preset
			const selectEl = filterArea.find(".edgesuite-date-presets-select");
			selectEl.val(frappe.EdgeSuite.DateRanges.getDefaultPreset());

			const enhancer = this;
			filterArea.on("change", ".edgesuite-date-presets-select", function () {
				enhancer.applyDatePreset($(this).val());
			});

			// Hook manual date input edits to change preset to "custom"
			const fromInput = fromDate.$input;
			const toInput = toDate.$input;
			if (fromInput && toInput) {
				const handleManualEdit = () => {
					if (selectEl.val() !== "custom") {
						selectEl.val("custom");
					}
				};
				fromInput.on("change", handleManualEdit);
				toInput.on("change", handleManualEdit);
			}
		}

		applyDatePreset(preset) {
			if (!preset || preset === "custom") return;
			const range = frappe.EdgeSuite.DateRanges.getRange(preset);
			if (range) {
				this.report.set_filter_value("from_date", range.start);
				this.report.set_filter_value("to_date", range.end);
				this.report.refresh();
			}
		}


		hookSummaryRender() {
			const enhancer = this;
			const report = this.report;

			report.show_and_render_summary = function (summary) {
				if (!summary) return;

				const metadataIndex = summary.findIndex(item => item.is_edgesuite_metadata);
				if (metadataIndex !== -1) {
					const metadata = summary.splice(metadataIndex, 1)[0];
					enhancer.renderExecutiveHeader(metadata, summary);
					enhancer.checkEmptyState(metadata);
				} else {
					if (frappe.views.QueryReport.prototype.show_and_render_summary) {
						frappe.views.QueryReport.prototype.show_and_render_summary.call(report, summary);
					}
				}
			};
		}

		renderExecutiveHeader(metadata, cards) {
			const report = this.report;
			report.page.main_section.find(".edgesuite-executive-header").remove();

			const escapeHtml = frappe.utils.escape_html;
			const filterSummary = metadata.filter_summary || "None";
			const lastRefresh = metadata.last_refresh || "Just Now";

			const hasHealth = metadata.capabilities.supports_health_score && metadata.health_score;
			const hasRecs = metadata.capabilities.supports_recommendations && metadata.recommendations.length > 0;

			const headerHtml = `
				<div class="edgesuite-executive-header p-3 mb-4 bg-white border rounded shadow-sm" style="border-radius: 8px; border: 1px solid var(--edge-border, #dfe5ef);">
					<!-- Action Bar -->
					<div class="d-flex justify-content-between align-items-center mb-3 pb-2 border-bottom flex-wrap" style="gap: 12px;">
						<div class="small text-muted">
							<span class="font-weight-bold"><i class="fa fa-filter"></i> Filters:</span> <span style="background-color: var(--edge-bg, #f7f9fc); padding: 2px 6px; border-radius: 4px;">${escapeHtml(filterSummary)}</span>
							<span class="mx-2">|</span>
							<span class="font-weight-bold"><i class="fa fa-clock-o"></i> Refreshed:</span> <span>${escapeHtml(lastRefresh)}</span>
						</div>
						<div class="d-flex btn-group" style="gap: 6px;">
							${metadata.capabilities.supports_export ? `<button class="btn btn-default btn-xs edge-btn-export" style="border-radius: 4px;"><i class="fa fa-download"></i> Export</button>` : ""}
							<button class="btn btn-default btn-xs edge-btn-share" style="border-radius: 4px;"><i class="fa fa-share-alt"></i> Share</button>
							<button class="btn btn-default btn-xs edge-btn-print" style="border-radius: 4px;"><i class="fa fa-print"></i> Print</button>
						</div>
					</div>

					<!-- Health & Recommendations -->
					${(hasHealth || hasRecs) ? `
					<div class="row mb-3 align-items-stretch" style="border-bottom: 1px solid var(--edge-border, #dfe5ef); padding-bottom: 16px;">
						${hasHealth ? `
						<div class="col-md-3 border-right text-center d-flex flex-column justify-content-center p-3" style="min-height: 120px;">
							<div class="text-muted small font-weight-bold mb-2" style="letter-spacing: 0.5px; text-transform: uppercase;">Health Score</div>
							<div class="h2 font-weight-bold mb-1 text-${metadata.health_score.severity}">${Math.round(metadata.health_score.score)}/100</div>
							<span class="badge badge-light p-2 font-weight-bold text-${metadata.health_score.severity}" style="font-size: 0.85rem; border-radius: 4px;">${escapeHtml(metadata.health_score.rating)}</span>
						</div>
						` : ""}
						${hasRecs ? `
						<div class="col-md-${hasHealth ? '9' : '12'} p-3">
							<div class="text-muted small font-weight-bold mb-2"><i class="fa fa-lightbulb-o"></i> Actionable Recommendations</div>
							<div class="d-flex flex-column" style="gap: 8px;">
								${metadata.recommendations.map(rec => `
									<div class="alert alert-${rec.severity === 'danger' ? 'danger' : 'warning'} p-2 mb-0 small" style="border-radius: 6px; border: 1px solid rgba(0,0,0,0.02);">
										<span class="font-weight-bold">${escapeHtml(rec.title)}:</span> ${escapeHtml(rec.description)}
									</div>
								`).join("")}
							</div>
						</div>
						` : ""}
					</div>
					` : ""}

					<!-- KPI Cards Grid -->
					<div class="row pt-2">
						${cards.map(card => {
							let cardVal = card.value;
							if (card.datatype === "Currency" && typeof cardVal === "number") {
								if (frappe.format_value) {
									cardVal = frappe.format_value(cardVal, {fieldtype: "Currency"});
								} else {
									cardVal = "₦" + cardVal.toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,');
								}
							} else if (card.datatype === "Percent" && typeof cardVal === "number") {
								cardVal = `${Math.round(cardVal)}%`;
							} else if (card.suffix && cardVal != null) {
								cardVal = `${cardVal}${card.suffix}`;
							}
							const hasTrend = card.trend && card.trend.direction !== "flat";
							const trendClass = card.trend ? (card.trend.direction === "up" ? "text-success" : "text-danger") : "";
							const trendSymbol = card.trend ? (card.trend.direction === "up" ? "▲" : "▼") : "";
							const trendBadge = hasTrend ? `<span class="${trendClass} ml-2 font-weight-bold" style="font-size: 0.8rem;">${trendSymbol} ${Math.round(card.trend.percentage)}%</span>` : (card.trend ? '<span class="text-muted ml-2 small">Stable</span>' : '');
							const isClickable = card.action && metadata.capabilities.supports_drilldown;

							return `
								<div class="col-md-3 mb-3">
									<div class="border rounded p-3 bg-white h-100 ${isClickable ? 'edgesuite-drilldown-card' : ''}"
										style="border-radius: 6px; ${isClickable ? 'cursor: pointer; border-color: var(--edge-border, #dfe5ef); transition: border 0.2s ease;' : ''}"
										${isClickable ? `data-action="${escapeHtml(JSON.stringify(card.action))}"` : ""}>
										<div class="text-muted small d-flex justify-content-between align-items-center mb-2">
											<span>${escapeHtml(card.label)}</span>
											${trendBadge}
										</div>
										<div class="h3 font-weight-bold mb-0" style="color: var(--edge-text, #1e293b);">${escapeHtml(cardVal)}</div>
									</div>
								</div>
							`;
						}).join("")}
					</div>
				</div>
			`;

			$(headerHtml).prependTo(report.page.main_section);

			// Attach event listeners
			const main = report.page.main_section;
			main.find(".edge-btn-export").on("click", () => report.export_report());
			main.find(".edge-btn-print").on("click", () => report.print_report());
			main.find(".edge-btn-share").on("click", () => {
				const dummy = document.createElement('input');
				document.body.appendChild(dummy);
				dummy.value = window.location.href;
				dummy.select();
				document.execCommand('copy');
				document.body.removeChild(dummy);
				frappe.show_alert({ message: __("Link copied to clipboard!"), indicator: "green" });
			});

			main.find(".edgesuite-drilldown-card").hover(
				function () { $(this).css("border-color", "var(--edge-primary, #1677ff)"); },
				function () { $(this).css("border-color", "var(--edge-border, #dfe5ef)"); }
			).on("click", function () {
				const actionStr = $(this).attr("data-action");
				if (actionStr) {
					const action = JSON.parse(actionStr);
					if (action.type === "report" && action.target) {
						frappe.route_options = Object.assign({}, report.get_values(), action.filters || {});
						frappe.set_route("query-report", action.target);
					}
				}
			});
		}

		checkEmptyState(metadata) {
			const report = this.report;
			const datatableContainer = report.$report.find(".datatable-container");
			const hasRows = report.data && report.data.length > 0;
			if (!hasRows && metadata && metadata.empty_state) {
				const emptyStateHtml = `
					<div class="edgesuite-empty-state text-center p-5 bg-white border rounded mt-4" style="border-radius: 8px; border: 1px solid var(--edge-border, #dfe5ef);">
						<div class="mb-3" style="font-size: 2.5rem; color: var(--edge-text-muted, #98a2b3);">📋</div>
						<h4 class="font-weight-bold" style="font-size: 1.1rem; color: var(--edge-text);">${frappe.utils.escape_html(metadata.empty_state.message)}</h4>
						<div class="text-muted mt-3 small" style="max-width: 480px; margin: 0 auto; line-height: 1.6;">
							${metadata.empty_state.suggestions.map(s => `<div class="mb-1">• ${frappe.utils.escape_html(s)}</div>`).join("")}
						</div>
					</div>
				`;
				datatableContainer.html(emptyStateHtml);
			}
		}
	}

	window.vetedgeReportVisibility = {
		apply(queryReport, reportName) {
			new EdgeReportEnhancer(queryReport, reportName);

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
