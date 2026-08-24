const VETEDGE_REGULATORY_STYLE_ID = "vetedge-regulatory-reporting-style";
const NADIS_VACCINATION_VALIDATE = "vetedge.services.nadis_vaccination_export.validate_nadis_vaccination_export";
const NADIS_VACCINATION_DOWNLOAD = "vetedge.services.nadis_vaccination_export.download_nadis_vaccination_workbook";
const NADIS_OUTBREAK_VALIDATE = "vetedge.services.nadis_outbreak_export.validate_nadis_outbreak_export";
const NADIS_OUTBREAK_DOWNLOAD = "vetedge.services.nadis_outbreak_export.download_nadis_outbreak_workbook";
const REPORT_FILTER_SEARCH = "vetedge.services.report_filter_search.search_report_filter_options";

function ensureRegulatoryStyles() {
	if (document.getElementById(VETEDGE_REGULATORY_STYLE_ID)) return;
	const style = document.createElement("style");
	style.id = VETEDGE_REGULATORY_STYLE_ID;
	style.textContent = `
		.vetedge-regulatory-root{width:100%;max-width:none}
		.vetedge-regulatory-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
		.vetedge-regulatory-card{border:1px solid var(--edge-color-border,#d9dce1);border-radius:14px;background:var(--edge-color-surface,#fff);padding:18px;display:grid;gap:16px;min-width:0}
		.vetedge-regulatory-card h3{margin:0;color:var(--edge-color-ink-950,#1f2937);font-size:1.05rem}
		.vetedge-regulatory-card p{margin:0;color:var(--edge-color-ink-500,#667085)}
		.vetedge-regulatory-filters{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
		.vetedge-regulatory-actions{display:flex;gap:8px;flex-wrap:wrap}
		.vetedge-regulatory-button{appearance:none;border:1px solid var(--edge-color-border,#d0d5dd);background:var(--edge-color-surface,#fff);color:var(--edge-color-ink-900,#344054);border-radius:9px;padding:8px 12px;font-weight:600;cursor:pointer}
		.vetedge-regulatory-button.primary{background:var(--edge-color-brand-600,#2563eb);border-color:var(--edge-color-brand-600,#2563eb);color:#fff}
		.vetedge-regulatory-button:disabled{opacity:.55;cursor:not-allowed}
		.vetedge-regulatory-status{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
		.vetedge-regulatory-pill{display:inline-flex;padding:4px 9px;border-radius:999px;font-size:.75rem;font-weight:700;background:var(--edge-color-surface-muted,#f2f4f7)}
		.vetedge-regulatory-pill.ready{color:var(--edge-color-success-700,#067647)}
		.vetedge-regulatory-pill.blocked{color:var(--edge-color-danger-700,#b42318)}
		.vetedge-regulatory-issues{display:grid;gap:6px;max-height:230px;overflow:auto}
		.vetedge-regulatory-issue{padding:8px 10px;border-radius:8px;background:var(--edge-color-surface-soft,#f8fafc);font-size:.82rem;color:var(--edge-color-ink-700,#475467)}
		.vetedge-regulatory-meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
		.vetedge-regulatory-stat{padding:10px;border-radius:10px;background:var(--edge-color-surface-muted,#f2f4f7)}
		.vetedge-regulatory-stat strong{display:block;font-size:1.15rem;color:var(--edge-color-ink-950,#101828)}
		.vetedge-regulatory-stat span{font-size:.75rem;color:var(--edge-color-ink-500,#667085)}
		@media(max-width:1000px){.vetedge-regulatory-grid{grid-template-columns:1fr}.vetedge-regulatory-filters{grid-template-columns:1fr 1fr}}
		@media(max-width:576px){.vetedge-regulatory-filters,.vetedge-regulatory-meta{grid-template-columns:1fr}.vetedge-regulatory-actions .vetedge-regulatory-button{width:100%}}
	`;
	document.head.appendChild(style);
}

function apiCall(method, args = {}) {
	return new Promise((resolve, reject) => {
		frappe.call({ method, args, callback: (response) => resolve(response.message || {}), error: reject });
	});
}

function downloadEndpoint(method, filters) {
	const params = new URLSearchParams({ filters: JSON.stringify(filters || {}) });
	window.location.assign(`/api/method/${method}?${params.toString()}`);
}

function profile() {
	const user = frappe.session?.user || "";
	const info = frappe.boot?.user_info?.[user] || {};
	return {
		tenantName: frappe.boot?.sysdefaults?.company || "",
		branchName: frappe.defaults?.get_user_default?.("branch") || "All Branches",
		userName: info.fullname || info.full_name || user,
	};
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
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ["EdgeAppShell", "EdgePageLayout", "EdgePageHeader", "EdgeLinkField", "EdgeInput"];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || !runtime?.Vue?.h || missing.length) {
			$loading.remove();
			$("<div class='alert alert-danger p-6'></div>").text(__("Regulatory Reporting requires the current EdgeSuite UI. Missing: {0}", [missing.join(", ")])).appendTo(wrapper.page.body);
			return;
		}

		const h = runtime.Vue.h;
		const { EdgeAppShell, EdgePageLayout, EdgePageHeader, EdgeLinkField, EdgeInput } = runtime.components;
		const userProfile = profile();
		const component = {
			name: "VetEdgeRegulatoryReporting",
			data() {
				return {
					filters: { branch: frappe.defaults?.get_user_default?.("branch") || "", from_date: "", to_date: "" },
					vaccination: { loading: false, result: null, error: "" },
					outbreak: { loading: false, result: null, error: "" },
				};
			},
			methods: {
				async searchBranches(term) {
					try {
						const response = await apiCall(REPORT_FILTER_SEARCH, {
							report_name: "Vaccination Report",
							field: "branch",
							txt: term || "",
							start: 0,
							page_length: 20,
							filters: JSON.stringify(this.filters),
						});
						return Array.isArray(response) ? response : [];
					} catch (_error) {
						return [];
					}
				},
				setFilter(key, value) { this.filters[key] = value || ""; this.vaccination.result = null; this.outbreak.result = null; },
				async validateVaccination() {
					this.vaccination.loading = true; this.vaccination.error = "";
					try { this.vaccination.result = await apiCall(NADIS_VACCINATION_VALIDATE, { filters: this.filters }); }
					catch (error) { this.vaccination.error = error?.message || __("Vaccination report validation failed."); }
					finally { this.vaccination.loading = false; }
				},
				async validateOutbreak() {
					this.outbreak.loading = true; this.outbreak.error = "";
					try { this.outbreak.result = await apiCall(NADIS_OUTBREAK_VALIDATE, { filters: this.filters }); }
					catch (error) { this.outbreak.error = error?.message || __("Disease Outbreak report validation failed."); }
					finally { this.outbreak.loading = false; }
				},
				downloadVaccination() { if (this.vaccination.result?.submission_ready) downloadEndpoint(NADIS_VACCINATION_DOWNLOAD, this.filters); },
				downloadOutbreak() { if (this.outbreak.result?.submission_ready) downloadEndpoint(NADIS_OUTBREAK_DOWNLOAD, this.filters); },
				newOutbreak() { frappe.new_doc?.("Veterinary Disease Outbreak"); },
				openOutbreaks() { frappe.set_route?.("List", "Veterinary Disease Outbreak"); },
				renderStats(result, kind) {
					if (!result) return null;
					const stats = kind === "vaccination"
						? [[result.source_count || 0, __("Vaccinations")], [result.grouped_row_count || 0, __("Workbook Rows")], [result.error_count || 0, __("Blocking Issues")]]
						: [[result.outbreak_count || 0, __("Outbreaks")], [result.animal_group_count || 0, __("Animal Groups")], [result.error_count || 0, __("Blocking Issues")]];
					return h("div", { class: "vetedge-regulatory-meta" }, stats.map(([value, label]) => h("div", { class: "vetedge-regulatory-stat" }, [h("strong", String(value)), h("span", label)])));
				},
				renderIssues(result, error) {
					if (error) return h("div", { class: "alert alert-danger" }, error);
					if (!result) return h("p", __("Validate the selected reporting period before downloading the official workbook."));
					const issues = [...(result.errors || []).map((item) => ({ ...item, kind: "error" })), ...(result.warnings || []).map((item) => ({ ...item, kind: "warning" }))];
					if (!issues.length) return h("div", { class: "vetedge-regulatory-issue" }, __("No blocking validation issues found."));
					return h("div", { class: "vetedge-regulatory-issues" }, issues.slice(0, 20).map((item) => h("div", { class: "vetedge-regulatory-issue" }, `${item.kind === "error" ? "Blocked" : "Warning"}${item.record ? ` · ${item.record}` : ""}: ${item.message || ""}`)));
				},
				renderCard(kind, title, description, state, validateAction, downloadAction) {
					const result = state.result;
					const ready = Boolean(result?.submission_ready);
					return h("section", { class: "vetedge-regulatory-card" }, [
						h("div", [h("h3", title), h("p", description)]),
						h("div", { class: "vetedge-regulatory-status" }, [
							h("span", { class: `vetedge-regulatory-pill ${ready ? "ready" : "blocked"}` }, ready ? __("Ready for Export") : result ? __("Needs Attention") : __("Not Validated")),
							result?.template_mapping_verified ? h("span", { class: "vetedge-regulatory-pill ready" }, __("Official Template Mapped")) : null,
						]),
						this.renderStats(result, kind),
						this.renderIssues(result, state.error),
						h("div", { class: "vetedge-regulatory-actions" }, [
							h("button", { class: "vetedge-regulatory-button", disabled: state.loading, onClick: validateAction }, state.loading ? __("Validating...") : __("Validate")),
							h("button", { class: "vetedge-regulatory-button primary", disabled: !ready || state.loading, onClick: downloadAction }, __("Download Official Excel")),
							kind === "outbreak" ? h("button", { class: "vetedge-regulatory-button", onClick: this.openOutbreaks }, __("Outbreak Register")) : null,
							kind === "outbreak" ? h("button", { class: "vetedge-regulatory-button", onClick: this.newOutbreak }, __("New Outbreak")) : null,
						]),
					]);
				},
			},
			render() {
				const filterPanel = h("div", { class: "vetedge-regulatory-card" }, [
					h("h3", __("Reporting Scope")),
					h("div", { class: "vetedge-regulatory-filters" }, [
						h(EdgeLinkField, { modelValue: this.filters.branch, label: __("Branch"), placeholder: __("Search Branch"), searchable: true, search: this.searchBranches, "onUpdate:modelValue": (value) => this.setFilter("branch", value) }),
						h(EdgeInput, { modelValue: this.filters.from_date, label: __("From Date"), type: "date", "onUpdate:modelValue": (value) => this.setFilter("from_date", value) }),
						h(EdgeInput, { modelValue: this.filters.to_date, label: __("To Date"), type: "date", "onUpdate:modelValue": (value) => this.setFilter("to_date", value) }),
					]),
					h("p", __("Regulatory exports use permission-aware Branch scope and the supplied NADIS workbook mappings. Validation never changes clinical, accounting or stock records.")),
				]);
				return h(EdgeAppShell, { productKey: "vetedge", profile: userProfile }, {
					default: () => h(EdgePageLayout, {}, {
						header: () => h(EdgePageHeader, { title: __("Regulatory Reporting"), description: __("Prepare VCN / NADIS vaccination and disease-outbreak submissions from Veterinary operational records.") }),
						default: () => h("main", { class: "vetedge-regulatory-root" }, [
							filterPanel,
							h("div", { style: "height:18px" }),
							h("div", { class: "vetedge-regulatory-grid" }, [
								this.renderCard("vaccination", __("NADIS Monthly Vaccination Report"), __("Aggregates administered vaccination records into the official NADIS vaccination workbook columns."), this.vaccination, this.validateVaccination, this.downloadVaccination),
								this.renderCard("outbreak", __("NADIS Disease Outbreak Report"), __("Exports outbreak records and their animal groups, diagnosis bases, control measures and locations across the five official workbook sheets."), this.outbreak, this.validateOutbreak, this.downloadOutbreak),
							]),
						]),
					}),
				});
			},
		};

		$loading.remove();
		const mount = document.createElement("div");
		mount.className = "vetedge-regulatory-root";
		wrapper.page.body.appendChild(mount);
		wrapper.vue_app = runtime.createEdgeApp(component);
		wrapper.vue_app.mount(mount);
	});
};
