const VETEDGE_REGULATORY_STYLE_ID = "vetedge-regulatory-reporting-style";
const NADIS_VACCINATION_VALIDATE = "vetedge.services.nadis_vaccination_export.validate_nadis_vaccination_export";
const NADIS_VACCINATION_DOWNLOAD = "vetedge.services.nadis_vaccination_export.download_nadis_vaccination_workbook";
const NADIS_OUTBREAK_VALIDATE = "vetedge.services.nadis_outbreak_export.validate_nadis_outbreak_export";
const NADIS_OUTBREAK_DOWNLOAD = "vetedge.services.nadis_outbreak_export.download_nadis_outbreak_workbook";
const REPORT_FILTER_SEARCH = "vetedge.services.report_filter_search.search_report_filter_options";
const REPORT_RUN_GENERATE = "vetedge.services.regulatory_report_runs.generate_regulatory_report_run";
const REPORT_RUN_HISTORY = "vetedge.services.regulatory_report_runs.get_regulatory_report_runs";
const REPORT_RUN_SEND = "vetedge.services.regulatory_report_runs.send_regulatory_report_run";
const REPORT_RUN_STATUS = "vetedge.services.regulatory_report_runs.update_regulatory_submission_status";
const VACCINATION_REPORT = "NADIS Monthly Vaccination Report";
const OUTBREAK_REPORT = "NADIS Disease Outbreak Report";

function ensureRegulatoryStyles() {
	if (document.getElementById(VETEDGE_REGULATORY_STYLE_ID)) return;
	const style = document.createElement("style");
	style.id = VETEDGE_REGULATORY_STYLE_ID;
	style.textContent = `
		.vetedge-regulatory-root{width:100%;max-width:none;display:grid;gap:18px}
		.vetedge-regulatory-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
		.vetedge-regulatory-filter-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
		.vetedge-regulatory-card{border:1px solid var(--edge-color-border,#d9dce1);border-radius:20px;background:var(--edge-color-surface,#fff);padding:18px;display:grid;gap:16px;min-width:0}
		.vetedge-regulatory-card h3{margin:0;color:var(--edge-color-ink-950,#1f2937);font-size:1.05rem}.vetedge-regulatory-card p{margin:0;color:var(--edge-color-ink-500,#667085)}
		.vetedge-regulatory-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
		.vetedge-regulatory-status{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.vetedge-regulatory-pill{display:inline-flex;padding:4px 9px;border-radius:999px;font-size:.75rem;font-weight:700;background:var(--edge-color-surface-muted,#f2f4f7)}.vetedge-regulatory-pill.ready{color:var(--edge-color-success-700,#067647)}.vetedge-regulatory-pill.blocked{color:var(--edge-color-danger-700,#b42318)}
		.vetedge-regulatory-issues{display:grid;gap:6px;max-height:230px;overflow:auto}.vetedge-regulatory-issue{padding:8px 10px;border-radius:8px;background:var(--edge-color-surface-soft,#f8fafc);font-size:.82rem;color:var(--edge-color-ink-700,#475467)}
		.vetedge-regulatory-meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.vetedge-regulatory-stat{padding:10px;border-radius:10px;background:var(--edge-color-surface-muted,#f2f4f7)}.vetedge-regulatory-stat strong{display:block;font-size:1.15rem;color:var(--edge-color-ink-950,#101828)}.vetedge-regulatory-stat span{font-size:.75rem;color:var(--edge-color-ink-500,#667085)}
		.vetedge-regulatory-history{display:grid;gap:10px}.vetedge-regulatory-run{display:grid;grid-template-columns:minmax(12rem,2fr) minmax(8rem,1fr) minmax(8rem,1fr) auto;gap:12px;align-items:center;padding:12px;border:1px solid var(--edge-color-border,#e4e7ec);border-radius:12px}.vetedge-regulatory-run-main{display:grid;gap:3px;min-width:0}.vetedge-regulatory-run-main strong{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.vetedge-regulatory-run small{color:var(--edge-color-ink-500,#667085)}
		.vetedge-regulatory-send-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr)) auto;gap:10px;align-items:end}
		.vetedge-regulatory-note{color:var(--edge-color-ink-500,#667085);font-size:.82rem}
		@media(max-width:1100px){.vetedge-regulatory-filter-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.vetedge-regulatory-run{grid-template-columns:1fr 1fr}.vetedge-regulatory-send-grid{grid-template-columns:1fr 1fr}}
		@media(max-width:1000px){.vetedge-regulatory-grid{grid-template-columns:1fr}}
		@media(max-width:576px){.vetedge-regulatory-filter-grid,.vetedge-regulatory-meta,.vetedge-regulatory-run,.vetedge-regulatory-send-grid{grid-template-columns:1fr}.vetedge-regulatory-actions .edge-button{width:100%}}
	`;
	document.head.appendChild(style);
}

function apiCall(method, args = {}) {
	return new Promise((resolve, reject) => frappe.call({ method, args, callback: (response) => resolve(response.message || {}), error: reject }));
}

function downloadEndpoint(method, filters) {
	const params = new URLSearchParams({ filters: JSON.stringify(filters || {}) });
	window.location.assign(`/api/method/${method}?${params.toString()}`);
}

function shellContext() {
	const user = frappe.session?.user || "";
	const info = frappe.boot?.user_info?.[user] || {};
	const identity = frappe.boot?.vetedge_ui_identity || frappe.boot?.edgesuite_ui_identity?.vetedge || {};
	return {
		tenantName: identity.tenant_name || frappe.boot?.sysdefaults?.company || "",
		branchName: frappe.defaults?.get_user_default?.("branch") || __("All Branches"),
		userName: info.fullname || info.full_name || user,
	};
}

function isRegulatoryAdmin() {
	return Boolean(frappe.user?.has_role?.("System Manager") || frappe.user?.has_role?.("VetEdge Administrator"));
}

frappe.pages["vetedge-regulatory-reporting"].on_page_load = function (wrapper) {
	wrapper.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Regulatory Reporting"), single_column: true });
};

frappe.pages["vetedge-regulatory-reporting"].on_page_show = function (wrapper) {
	wrapper.visit_id = (wrapper.visit_id || 0) + 1;
	const visitId = wrapper.visit_id;
	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(wrapper.page.body).empty();
	ensureRegulatoryStyles();
	const $loading = $("<div class='p-6 text-center text-muted'></div>").text(__("Loading Regulatory Reporting...")).appendTo(wrapper.page.body);

	frappe.require("edgeui.bundle.js", () => {
		if (wrapper.visit_id !== visitId) return;
		const professional = window.VetEdgeProfessionalUI?.install?.();
		if (!professional?.installed) {
			$loading.remove();
			$("<div class='alert alert-danger p-6'></div>").text(professional?.message || __("The Veterinary professional shell is unavailable.")).appendTo(wrapper.page.body);
			return;
		}

		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ["EdgeAppShell", "EdgePageLayout", "EdgePageHeader", "EdgeFilterBar", "EdgeLinkField", "EdgeInput"];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || !runtime?.Vue?.h || missing.length) {
			$loading.remove();
			$("<div class='alert alert-danger p-6'></div>").text(__("Regulatory Reporting requires the current EdgeSuite UI. Missing: {0}", [missing.join(", ")])).appendTo(wrapper.page.body);
			return;
		}

		const h = runtime.Vue.h;
		const { EdgeAppShell, EdgePageLayout, EdgePageHeader, EdgeFilterBar, EdgeLinkField, EdgeInput } = runtime.components;
		const userProfile = shellContext();

		const component = {
			name: "VetEdgeRegulatoryReporting",
			data() {
				return {
					filters: {
						company: frappe.defaults?.get_user_default?.("Company") || frappe.boot?.sysdefaults?.company || "",
						branch: frappe.defaults?.get_user_default?.("branch") || "",
						from_date: "",
						to_date: "",
					},
					canManageOutbreak: isRegulatoryAdmin(),
					canManageRuns: isRegulatoryAdmin(),
					vaccination: { loading: false, generating: false, result: null, error: "" },
					outbreak: { loading: false, generating: false, result: null, error: "" },
					history: { loading: false, rows: [], total: 0, error: "" },
					emailRecipients: "",
					submissionReference: "",
					submissionNotes: "",
					sendingRun: "",
					updatingRun: "",
				};
			},
			async mounted() {
				if (this.canManageRuns) await this.loadHistory();
			},
			methods: {
				async searchCompanies(term) {
					try {
						const response = await apiCall("frappe.desk.search.search_link", { doctype: "Company", txt: term || "", page_length: 20, ignore_user_permissions: 0 });
						return Array.isArray(response) ? response : [];
					} catch (_error) {
						return [];
					}
				},
				async searchBranches(term) {
					try {
						const response = await apiCall(REPORT_FILTER_SEARCH, { report_name: "Vaccination Report", field: "branch", txt: term || "", start: 0, page_length: 20, filters: JSON.stringify(this.filters) });
						return Array.isArray(response) ? response : [];
					} catch (_error) {
						return [];
					}
				},
				setFilter(key, value) {
					this.filters[key] = value || "";
					this.vaccination.result = null;
					this.outbreak.result = null;
				},
				resetScope() {
					this.filters = {
						company: frappe.defaults?.get_user_default?.("Company") || frappe.boot?.sysdefaults?.company || "",
						branch: frappe.defaults?.get_user_default?.("branch") || "",
						from_date: "",
						to_date: "",
					};
					this.vaccination.result = null;
					this.outbreak.result = null;
				},
				async validateVaccination() {
					this.vaccination.loading = true;
					this.vaccination.error = "";
					try {
						this.vaccination.result = await apiCall(NADIS_VACCINATION_VALIDATE, { filters: this.filters });
					} catch (error) {
						this.vaccination.error = error?.message || __("Vaccination report validation failed.");
					} finally {
						this.vaccination.loading = false;
					}
				},
				async validateOutbreak() {
					if (!this.canManageOutbreak) return;
					this.outbreak.loading = true;
					this.outbreak.error = "";
					try {
						this.outbreak.result = await apiCall(NADIS_OUTBREAK_VALIDATE, { filters: this.filters });
					} catch (error) {
						this.outbreak.error = error?.message || __("Disease Outbreak report validation failed.");
					} finally {
						this.outbreak.loading = false;
					}
				},
				downloadVaccination() {
					if (this.vaccination.result?.submission_ready) downloadEndpoint(NADIS_VACCINATION_DOWNLOAD, this.filters);
				},
				downloadOutbreak() {
					if (this.canManageOutbreak && this.outbreak.result?.submission_ready) downloadEndpoint(NADIS_OUTBREAK_DOWNLOAD, this.filters);
				},
				async generateRun(kind) {
					if (!this.canManageRuns) return;
					const state = kind === "vaccination" ? this.vaccination : this.outbreak;
					const reportType = kind === "vaccination" ? VACCINATION_REPORT : OUTBREAK_REPORT;
					if (!state.result?.submission_ready) return;
					state.generating = true;
					try {
						const result = await apiCall(REPORT_RUN_GENERATE, { report_type: reportType, filters: this.filters });
						frappe.show_alert?.({ message: __("Regulatory report {0} saved to history.", [result.name]), indicator: "green" });
						await this.loadHistory();
					} catch (error) {
						frappe.msgprint({ title: __("Report Generation Failed"), message: error?.message || __("The regulatory report could not be saved."), indicator: "red" });
					} finally {
						state.generating = false;
					}
				},
				async loadHistory() {
					if (!this.canManageRuns) return;
					this.history.loading = true;
					this.history.error = "";
					try {
						const result = await apiCall(REPORT_RUN_HISTORY, { company: this.filters.company || "", branch: this.filters.branch || "", start: 0, page_length: 10 });
						this.history.rows = result.rows || [];
						this.history.total = Number(result.total || 0);
					} catch (error) {
						this.history.error = error?.message || __("Regulatory report history could not be loaded.");
						this.history.rows = [];
					} finally {
						this.history.loading = false;
					}
				},
				async sendRun(run) {
					if (!this.canManageRuns || !run?.name || !String(this.emailRecipients || "").trim()) {
						frappe.msgprint({ title: __("Recipient Required"), message: __("Enter at least one recipient email address before sending."), indicator: "orange" });
						return;
					}
					this.sendingRun = run.name;
					try {
						const result = await apiCall(REPORT_RUN_SEND, { name: run.name, recipients: this.emailRecipients });
						frappe.show_alert?.({ message: __("Regulatory report sent to {0}.", [result.sent_to]), indicator: "green" });
						await this.loadHistory();
					} catch (error) {
						frappe.msgprint({ title: __("Send Failed"), message: error?.message || __("The regulatory report could not be sent."), indicator: "red" });
					} finally {
						this.sendingRun = "";
					}
				},
				async updateRunStatus(run, status) {
					if (!this.canManageRuns || !run?.name) return;
					this.updatingRun = run.name;
					try {
						await apiCall(REPORT_RUN_STATUS, { name: run.name, status, submission_reference: this.submissionReference || "", notes: this.submissionNotes || "" });
						frappe.show_alert?.({ message: __("Regulatory report marked {0}.", [status]), indicator: "green" });
						await this.loadHistory();
					} catch (error) {
						frappe.msgprint({ title: __("Status Update Failed"), message: error?.message || __("The regulatory report status could not be updated."), indicator: "red" });
					} finally {
						this.updatingRun = "";
					}
				},
				newOutbreak() {
					if (this.canManageOutbreak) frappe.new_doc?.("Veterinary Disease Outbreak");
				},
				openOutbreaks() {
					if (this.canManageOutbreak) frappe.set_route?.("vetedge-disease-outbreak-register");
				},
				renderStats(result, kind) {
					if (!result) return null;
					const stats = kind === "vaccination"
						? [[result.distinct_animal_count || 0, __("Animals Vaccinated")], [result.grouped_row_count || 0, __("Workbook Rows")], [result.error_count || 0, __("Blocking Issues")]]
						: [[result.outbreak_count || 0, __("Outbreaks")], [result.animal_group_count || 0, __("Animal Groups")], [result.error_count || 0, __("Blocking Issues")]];
					return h("div", { class: "vetedge-regulatory-meta" }, stats.map(([value, label]) => h("div", { class: "vetedge-regulatory-stat" }, [h("strong", String(value)), h("span", label)])));
				},
				renderIssues(result, error, kind) {
					if (kind === "outbreak" && !this.canManageOutbreak) return h("div", { class: "vetedge-regulatory-issue" }, __("Disease Outbreak regulatory entry and export are currently restricted to Veterinary administrators until native outbreak Branch-read permission hooks complete QA."));
					if (error) return h("div", { class: "alert alert-danger" }, error);
					if (!result) return h("p", __("Validate the selected reporting period before downloading or saving a regulatory workbook."));
					const issues = [
						...(result.errors || []).map((item) => ({ ...item, kind: "error" })),
						...(result.warnings || []).map((item) => ({ ...item, kind: "warning" })),
					];
					if (!issues.length) return h("div", { class: "vetedge-regulatory-issue" }, __("No blocking validation issues found."));
					return h("div", { class: "vetedge-regulatory-issues" }, issues.slice(0, 20).map((item) => h("div", { class: "vetedge-regulatory-issue" }, `${item.kind === "error" ? "Blocked" : "Warning"}${item.record ? ` · ${item.record}` : ""}: ${item.message || ""}`)));
				},
				renderCard(kind, title, description, state, validateAction, downloadAction) {
					const result = state.result;
					const restricted = kind === "outbreak" && !this.canManageOutbreak;
					const ready = Boolean(!restricted && result?.submission_ready);
					return h("section", { class: "vetedge-regulatory-card" }, [
						h("div", [h("h3", title), h("p", description)]),
						h("div", { class: "vetedge-regulatory-status" }, [
							h("span", { class: `vetedge-regulatory-pill ${ready ? "ready" : "blocked"}` }, restricted ? __("Administrator Managed") : ready ? __("Ready for Export") : result ? __("Needs Attention") : __("Not Validated")),
							result?.template_mapping_verified ? h("span", { class: "vetedge-regulatory-pill ready" }, __("Official Template Mapped")) : null,
						]),
						this.renderStats(result, kind),
						this.renderIssues(result, state.error, kind),
						h("div", { class: "vetedge-regulatory-actions" }, [
							h("button", { class: "edge-button", disabled: restricted || state.loading, onClick: validateAction }, state.loading ? __("Validating...") : __("Validate")),
							h("button", { class: "edge-button edge-button--primary", disabled: restricted || !ready || state.loading, onClick: downloadAction }, __("Download Excel")),
							this.canManageRuns && !restricted ? h("button", { class: "edge-button", disabled: !ready || state.generating, onClick: () => this.generateRun(kind) }, state.generating ? __("Saving...") : __("Generate & Save")) : null,
							kind === "outbreak" && this.canManageOutbreak ? h("button", { class: "edge-button", onClick: this.openOutbreaks }, __("Outbreak Register")) : null,
							kind === "outbreak" && this.canManageOutbreak ? h("button", { class: "edge-button", onClick: this.newOutbreak }, __("New Outbreak")) : null,
						]),
					]);
				},
				renderRunActions(run) {
					const busy = this.sendingRun === run.name || this.updatingRun === run.name;
					const status = run.status || "Generated";
					const actions = [
						run.export_file ? h("button", { class: "edge-button", disabled: busy, onClick: () => window.open(run.export_file, "_blank", "noopener") }, __("Open File")) : null,
					];
					if (status === "Generated") {
						actions.push(h("button", { class: "edge-button edge-button--primary", disabled: busy, onClick: () => this.sendRun(run) }, this.sendingRun === run.name ? __("Sending...") : __("Send")));
						actions.push(h("button", { class: "edge-button", disabled: busy, onClick: () => this.updateRunStatus(run, "Superseded") }, __("Supersede")));
					}
					if (status === "Sent") {
						actions.push(h("button", { class: "edge-button", disabled: busy, onClick: () => this.updateRunStatus(run, "Accepted") }, __("Accept")));
						actions.push(h("button", { class: "edge-button", disabled: busy, onClick: () => this.updateRunStatus(run, "Rejected") }, __("Reject")));
						actions.push(h("button", { class: "edge-button", disabled: busy, onClick: () => this.updateRunStatus(run, "Superseded") }, __("Supersede")));
					}
					if (status === "Rejected") {
						actions.push(h("button", { class: "edge-button", disabled: busy, onClick: () => this.updateRunStatus(run, "Superseded") }, __("Supersede")));
					}
					return h("div", { class: "vetedge-regulatory-actions" }, actions);
				},
				renderHistory() {
					if (!this.canManageRuns) return null;
					const rows = this.history.rows || [];
					return h("section", { class: "vetedge-regulatory-card" }, [
						h("div", [h("h3", __("Submission History")), h("p", __("Saved workbooks are private, immutable report evidence. Email sends use the saved attachment and do not regenerate clinical data."))]),
						h("div", { class: "vetedge-regulatory-send-grid" }, [
							h(EdgeInput, { modelValue: this.emailRecipients, label: __("Recipient Email(s)"), placeholder: __("vcn@example.gov.ng, officer@example.gov.ng"), "onUpdate:modelValue": (value) => { this.emailRecipients = value || ""; } }),
							h(EdgeInput, { modelValue: this.submissionReference, label: __("Submission Reference"), placeholder: __("Optional acknowledgement/reference"), "onUpdate:modelValue": (value) => { this.submissionReference = value || ""; } }),
							h(EdgeInput, { modelValue: this.submissionNotes, label: __("Submission Notes"), placeholder: __("Optional acceptance/rejection notes"), "onUpdate:modelValue": (value) => { this.submissionNotes = value || ""; } }),
							h("button", { class: "edge-button", disabled: this.history.loading, onClick: this.loadHistory }, this.history.loading ? __("Refreshing...") : __("Refresh History")),
						]),
						this.history.error ? h("div", { class: "alert alert-danger" }, this.history.error) : null,
						!rows.length && !this.history.loading ? h("div", { class: "vetedge-regulatory-issue" }, __("No saved regulatory report runs match the current Company/Branch scope.")) : null,
						rows.length ? h("div", { class: "vetedge-regulatory-history" }, rows.map((run) => h("div", { class: "vetedge-regulatory-run", key: run.name }, [
							h("div", { class: "vetedge-regulatory-run-main" }, [h("strong", run.report_type || run.name), h("small", `${run.name} · ${frappe.datetime?.str_to_user?.(run.generated_on) || run.generated_on || ""}`), run.sent_to ? h("small", __("Sent to {0}", [run.sent_to])) : null]),
							h("div", [h("span", { class: `vetedge-regulatory-pill ${run.status === "Accepted" ? "ready" : run.status === "Rejected" ? "blocked" : ""}` }, run.status || __("Generated")), h("small", { style: "display:block;margin-top:4px" }, run.service_branch || run.company || "")]),
							h("div", [h("small", __("Template SHA-256")), h("div", { title: run.template_sha256 || "", style: "font-family:monospace;font-size:.72rem;overflow:hidden;text-overflow:ellipsis" }, run.template_sha256 || "—"), run.submission_reference ? h("small", __("Reference: {0}", [run.submission_reference])) : null]),
							this.renderRunActions(run),
						]))) : null,
					]);
				},
				renderFilterBar() {
					return h(EdgeFilterBar, { title: __("Reporting Scope") }, {
						default: () => h("div", { class: "vetedge-regulatory-filter-grid" }, [
							h(EdgeLinkField, { modelValue: this.filters.company, selectedLabel: this.filters.company || "", label: __("Company"), placeholder: __("All permitted companies"), searcher: this.searchCompanies, clearable: true, "onUpdate:modelValue": (value) => this.setFilter("company", value) }),
							h(EdgeLinkField, { modelValue: this.filters.branch, selectedLabel: this.filters.branch || "", label: __("Branch"), placeholder: __("All permitted branches"), searcher: this.searchBranches, clearable: true, "onUpdate:modelValue": (value) => this.setFilter("branch", value) }),
							h(EdgeInput, { modelValue: this.filters.from_date, label: __("From Date"), type: "date", "onUpdate:modelValue": (value) => this.setFilter("from_date", value) }),
							h(EdgeInput, { modelValue: this.filters.to_date, label: __("To Date"), type: "date", "onUpdate:modelValue": (value) => this.setFilter("to_date", value) }),
						]),
						actions: () => h("div", { class: "vetedge-regulatory-actions" }, [
							h("button", { class: "edge-button", onClick: this.resetScope }, __("Reset")),
						]),
					});
				},
			},
			render() {
				return h(EdgeAppShell, {
					product: "vetedge",
					title: __("Veterinary"),
					tenantName: userProfile.tenantName,
					branchName: userProfile.branchName,
					userName: userProfile.userName,
					activeRoute: "/desk/vetedge-regulatory-reporting",
				}, {
					default: () => h(EdgePageLayout, {}, {
						header: () => h(EdgePageHeader, {
							eyebrow: __("Regulatory Reporting"),
							title: __("VCN / NADIS Reporting"),
							subtitle: __("Prepare, retain, send and track vaccination and disease-outbreak submissions from Veterinary operational records."),
							actionLabel: this.canManageOutbreak ? __("Outbreak Register") : "",
							onAction: this.openOutbreaks,
						}),
						filters: () => this.renderFilterBar(),
						default: () => h("main", { class: "vetedge-regulatory-root" }, [
							h("div", { class: "vetedge-regulatory-grid" }, [
								this.renderCard("vaccination", __("NADIS Monthly Vaccination Report"), __("Counts distinct vaccinated animals and aggregates administered records into the mapped NADIS vaccination workbook."), this.vaccination, this.validateVaccination, this.downloadVaccination),
								this.renderCard("outbreak", __("NADIS Disease Outbreak Report"), __("Exports outbreak records and their animal groups, diagnosis bases, control measures and locations across the five mapped workbook sheets."), this.outbreak, this.validateOutbreak, this.downloadOutbreak),
							]),
							h("div", { class: "vetedge-regulatory-note" }, __("Regulatory exports remain permission-aware and never mutate clinical, accounting or stock records during validation or download.")),
							this.renderHistory(),
						]),
					}),
				});
			},
		};

		$loading.remove();
		const mount = document.createElement("div");
		mount.className = "vetedge-regulatory-root";
		$(wrapper.page.body).append(mount);
		wrapper.vue_app = runtime.createEdgeApp(component);
		wrapper.vue_app.mount(mount);
	});
};