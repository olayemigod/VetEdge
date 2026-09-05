const VETEDGE_OUTBREAK_REGISTER_STYLE_ID = "vetedge-disease-outbreak-register-style";
const OUTBREAK_DOCTYPE = "Veterinary Disease Outbreak";
const OUTBREAK_REGISTER_API = "vetedge.services.outbreak_register.get_outbreak_register";
const OUTBREAK_BRANCH_SEARCH_API = "vetedge.services.outbreak_register.search_outbreak_branches";
const OUTBREAK_PAGE_LENGTH = 25;

const OUTBREAK_COLUMNS = Object.freeze([
	{ fieldname: "name", label: __("Outbreak") },
	{ fieldname: "nadis_disease", label: __("NADIS Disease") },
	{ fieldname: "outbreak_status", label: __("Status") },
	{ fieldname: "outbreak_type", label: __("Type") },
	{ fieldname: "service_branch", label: __("Reporting Branch") },
	{ fieldname: "date_investigated", label: __("Investigated"), fieldtype: "Date" },
	{ fieldname: "number_new_outbreaks", label: __("New Outbreaks"), fieldtype: "Int" },
	{ fieldname: "total_outbreaks", label: __("Total Outbreaks"), fieldtype: "Int" },
]);

const OUTBREAK_STATUS_OPTIONS = Object.freeze([
	{ value: "", label: __("All statuses") },
	{ value: "Continuing", label: __("Continuing") },
	{ value: "Resolved", label: __("Resolved") },
]);

function ensureOutbreakRegisterStyles() {
	if (document.getElementById(VETEDGE_OUTBREAK_REGISTER_STYLE_ID)) return;
	const style = document.createElement("style");
	style.id = VETEDGE_OUTBREAK_REGISTER_STYLE_ID;
	style.textContent = `
		.vetedge-outbreak-register-root{width:100%;max-width:none;display:grid;gap:16px}
		.vetedge-outbreak-filter-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;align-items:end}
		.vetedge-outbreak-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
		.vetedge-outbreak-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
		.vetedge-outbreak-pagination{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;padding-top:10px}
		.vetedge-outbreak-note{color:var(--edge-color-ink-500,#667085);font-size:.82rem}
		@media(max-width:1100px){.vetedge-outbreak-filter-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
		@media(max-width:620px){.vetedge-outbreak-filter-grid,.vetedge-outbreak-summary{grid-template-columns:1fr}.vetedge-outbreak-actions .edge-button{width:100%}}
	`;
	document.head.appendChild(style);
}

function outbreakApiCall(method, args = {}) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method,
			args,
			callback: (response) => resolve(response.message ?? {}),
			error: reject,
		});
	});
}

function outbreakShellContext() {
	const user = frappe.session?.user || "";
	const info = frappe.boot?.user_info?.[user] || {};
	const identity = frappe.boot?.vetedge_ui_identity || frappe.boot?.edgesuite_ui_identity?.vetedge || {};
	return {
		tenantName: identity.tenant_name || frappe.boot?.sysdefaults?.company || "",
		branchName: frappe.defaults?.get_user_default?.("branch") || __("All Branches"),
		userName: info.fullname || info.full_name || user,
	};
}

function todayDate() {
	return frappe.datetime?.get_today?.() || new Date().toISOString().slice(0, 10);
}

function addDays(value, days) {
	if (frappe.datetime?.add_days) return frappe.datetime.add_days(value, days);
	const date = new Date(`${value}T00:00:00`);
	date.setDate(date.getDate() + days);
	return date.toISOString().slice(0, 10);
}

frappe.pages["vetedge-disease-outbreak-register"].on_page_load = function (wrapper) {
	wrapper.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Disease Outbreak Register"),
		single_column: true,
	});
};

frappe.pages["vetedge-disease-outbreak-register"].on_page_show = function (wrapper) {
	wrapper.visit_id = (wrapper.visit_id || 0) + 1;
	const visitId = wrapper.visit_id;
	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(wrapper.page.body).empty();
	ensureOutbreakRegisterStyles();

	const $loading = $("<div class='p-6 text-center text-muted'></div>")
		.text(__("Loading Disease Outbreak Register..."))
		.appendTo(wrapper.page.body);

	frappe.require("edgeui.bundle.js", () => {
		if (wrapper.visit_id !== visitId) return;
		const professional = window.VetEdgeProfessionalUI?.install?.();
		if (!professional?.installed) {
			$loading.remove();
			$("<div class='alert alert-danger p-6'></div>")
				.text(professional?.message || __("The Veterinary professional shell is unavailable."))
				.appendTo(wrapper.page.body);
			return;
		}

		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = [
			"EdgeAppShell",
			"EdgePageLayout",
			"EdgePageHeader",
			"EdgeFilterBar",
			"EdgeLinkField",
			"EdgeDropdown",
			"EdgeInput",
			"EdgeStatCard",
			"EdgeDataTable",
			"EdgeLoadingState",
			"EdgeErrorState",
			"EdgeEmptyState",
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || !runtime?.Vue?.h || missing.length) {
			$loading.remove();
			$("<div class='alert alert-danger p-6'></div>")
				.text(__("Disease Outbreak Register requires the current EdgeSuite UI. Missing: {0}", [missing.join(", ")]))
				.appendTo(wrapper.page.body);
			return;
		}

		const h = runtime.Vue.h;
		const {
			EdgeAppShell,
			EdgePageLayout,
			EdgePageHeader,
			EdgeFilterBar,
			EdgeLinkField,
			EdgeDropdown,
			EdgeInput,
			EdgeStatCard,
			EdgeDataTable,
			EdgeLoadingState,
			EdgeErrorState,
			EdgeEmptyState,
		} = runtime.components;
		const userProfile = outbreakShellContext();

		const component = {
			name: "VetEdgeDiseaseOutbreakRegister",
			data() {
				const toDate = todayDate();
				return {
					loading: false,
					error: "",
					rows: [],
					total: 0,
					start: 0,
					pageLength: OUTBREAK_PAGE_LENGTH,
					canCreate: false,
					canWrite: false,
					columns: OUTBREAK_COLUMNS,
					statusOptions: OUTBREAK_STATUS_OPTIONS,
					filters: {
						company: frappe.defaults?.get_user_default?.("Company") || frappe.boot?.sysdefaults?.company || "",
						branch: frappe.defaults?.get_user_default?.("branch") || "",
						status: "",
						disease: "",
						from_date: addDays(toDate, -365),
						to_date: toDate,
						txt: "",
					},
				};
			},
			computed: {
				currentPage() { return Math.floor(this.start / this.pageLength) + 1; },
				totalPages() { return Math.max(1, Math.ceil(this.total / this.pageLength)); },
				hasPrevious() { return this.start > 0; },
				hasNext() { return this.start + this.rows.length < this.total; },
				firstVisible() { return this.total ? this.start + 1 : 0; },
				lastVisible() { return Math.min(this.start + this.rows.length, this.total); },
			},
			async mounted() {
				await this.load();
			},
			methods: {
				setFilter(key, value) {
					this.filters[key] = value || "";
				},
				async searchCompanies(term) {
					try {
						const response = await outbreakApiCall("frappe.desk.search.search_link", {
							doctype: "Company",
							txt: term || "",
							page_length: 20,
							ignore_user_permissions: 0,
						});
						return Array.isArray(response) ? response : [];
					} catch (_error) {
						return [];
					}
				},
				async searchBranches(term) {
					try {
						const response = await outbreakApiCall(OUTBREAK_BRANCH_SEARCH_API, {
							txt: term || "",
							start: 0,
							page_length: 20,
						});
						return Array.isArray(response) ? response : [];
					} catch (_error) {
						return [];
					}
				},
				async searchDiseases(term) {
					try {
						const response = await outbreakApiCall("frappe.desk.search.search_link", {
							doctype: "Veterinary Diagnosis",
							txt: term || "",
							page_length: 20,
							ignore_user_permissions: 0,
						});
						return Array.isArray(response) ? response : [];
					} catch (_error) {
						return [];
					}
				},
				async load() {
					if (this.loading) return;
					this.loading = true;
					this.error = "";
					try {
						const result = await outbreakApiCall(OUTBREAK_REGISTER_API, {
							filters: JSON.stringify(this.filters),
							start: this.start,
							page_length: this.pageLength,
						});
						this.rows = result.rows || [];
						this.total = Number(result.total || 0);
						this.canCreate = Boolean(result.can_create);
						this.canWrite = Boolean(result.can_write);
						if (this.start && this.start >= this.total) {
							this.start = Math.max(0, Math.floor(Math.max(this.total - 1, 0) / this.pageLength) * this.pageLength);
							return this.load();
						}
					} catch (error) {
						this.rows = [];
						this.total = 0;
						this.error = error?.message || __("Disease Outbreak Register could not be loaded.");
					} finally {
						this.loading = false;
					}
				},
				applyFilters() {
					this.start = 0;
					this.load();
				},
				resetFilters() {
					const toDate = todayDate();
					this.filters = {
						company: frappe.defaults?.get_user_default?.("Company") || frappe.boot?.sysdefaults?.company || "",
						branch: frappe.defaults?.get_user_default?.("branch") || "",
						status: "",
						disease: "",
						from_date: addDays(toDate, -365),
						to_date: toDate,
						txt: "",
					};
					this.start = 0;
					this.load();
				},
				previousPage() {
					if (!this.hasPrevious) return;
					this.start = Math.max(0, this.start - this.pageLength);
					this.load();
				},
				nextPage() {
					if (!this.hasNext) return;
					this.start += this.pageLength;
					this.load();
				},
				openRecord(row) {
					if (!row?.name) return;
					frappe.set_route?.("Form", OUTBREAK_DOCTYPE, row.name);
				},
				newOutbreak() {
					if (!this.canCreate) return;
					const defaults = {};
					if (this.filters.branch) defaults.service_branch = this.filters.branch;
					if (this.filters.company) defaults.company = this.filters.company;
					frappe.new_doc?.(OUTBREAK_DOCTYPE, defaults);
				},
				openRegulatoryReports() {
					frappe.set_route?.("vetedge-regulatory-reporting");
				},
				renderFilterBar() {
					return h(EdgeFilterBar, { title: __("Filter disease outbreaks") }, {
						default: () => h("div", { class: "vetedge-outbreak-filter-grid" }, [
							h(EdgeLinkField, {
								modelValue: this.filters.company,
								selectedLabel: this.filters.company || "",
								label: __("Company"),
								placeholder: __("All permitted companies"),
								searcher: this.searchCompanies,
								clearable: true,
								"onUpdate:modelValue": (value) => this.setFilter("company", value),
							}),
							h(EdgeLinkField, {
								modelValue: this.filters.branch,
								selectedLabel: this.filters.branch || "",
								label: __("Reporting Branch"),
								placeholder: __("All assigned branches"),
								searcher: this.searchBranches,
								clearable: true,
								"onUpdate:modelValue": (value) => this.setFilter("branch", value),
							}),
							h(EdgeDropdown, {
								modelValue: this.filters.status,
								label: __("Status"),
								placeholder: __("All statuses"),
								options: this.statusOptions,
								"onUpdate:modelValue": (value) => this.setFilter("status", value),
							}),
							h(EdgeLinkField, {
								modelValue: this.filters.disease,
								selectedLabel: this.filters.disease || "",
								label: __("Diagnosis / Disease"),
								placeholder: __("All diseases"),
								searcher: this.searchDiseases,
								clearable: true,
								"onUpdate:modelValue": (value) => this.setFilter("disease", value),
							}),
							h(EdgeInput, {
								modelValue: this.filters.from_date,
								label: __("Investigated From"),
								type: "date",
								"onUpdate:modelValue": (value) => this.setFilter("from_date", value),
							}),
							h(EdgeInput, {
								modelValue: this.filters.to_date,
								label: __("Investigated To"),
								type: "date",
								"onUpdate:modelValue": (value) => this.setFilter("to_date", value),
							}),
							h(EdgeInput, {
								modelValue: this.filters.txt,
								label: __("Search"),
								type: "search",
								placeholder: __("Outbreak, disease or serotype"),
								"onUpdate:modelValue": (value) => this.setFilter("txt", value),
							}),
						]),
						actions: () => h("div", { class: "vetedge-outbreak-actions" }, [
							h("button", { class: "edge-button edge-button--primary", disabled: this.loading, onClick: this.applyFilters }, __("Apply")),
							h("button", { class: "edge-button", disabled: this.loading, onClick: this.resetFilters }, __("Reset")),
							h("button", { class: "edge-button", disabled: this.loading, onClick: this.load }, this.loading ? __("Refreshing...") : __("Refresh")),
							h("button", { class: "edge-button", onClick: this.openRegulatoryReports }, __("VCN / NADIS Reports")),
						]),
					});
				},
				renderContent() {
					if (this.loading) return h(EdgeLoadingState, { message: __("Loading disease outbreaks..."), skeleton: true });
					if (this.error) return h(EdgeErrorState, { title: __("Disease Outbreak Register could not load"), message: this.error, actionLabel: __("Try Again"), onRetry: this.load });
					if (!this.rows.length) return h(EdgeEmptyState, { title: __("No disease outbreaks found"), description: __("No outbreak records match the selected Company, Branch, status, disease and investigation dates."), actionLabel: this.canCreate ? __("New Outbreak") : "", onAction: this.newOutbreak });
					return h("div", { class: "vetedge-outbreak-register-root" }, [
						h(EdgeDataTable, { columns: this.columns, rows: this.rows, rowKey: "name", onRowClick: this.openRecord }),
						h("div", { class: "vetedge-outbreak-pagination" }, [
							h("span", { class: "vetedge-outbreak-note" }, __("Showing {0}–{1} of {2}", [this.firstVisible, this.lastVisible, this.total])),
							h("div", { class: "vetedge-outbreak-actions" }, [
								h("button", { class: "edge-button edge-button--compact", disabled: !this.hasPrevious || this.loading, onClick: this.previousPage }, __("Previous")),
								h("span", { class: "vetedge-outbreak-note" }, __("Page {0} of {1}", [this.currentPage, this.totalPages])),
								h("button", { class: "edge-button edge-button--compact", disabled: !this.hasNext || this.loading, onClick: this.nextPage }, __("Next")),
							]),
						]),
					]);
				},
			},
			render() {
				return h(EdgeAppShell, {
					product: "vetedge",
					title: __("Veterinary"),
					tenantName: userProfile.tenantName,
					branchName: userProfile.branchName,
					userName: userProfile.userName,
					activeRoute: "/desk/vetedge-disease-outbreak-register",
				}, {
					default: () => h(EdgePageLayout, {}, {
						header: () => h(EdgePageHeader, {
							eyebrow: __("Regulatory Reporting"),
							title: __("Disease Outbreak Register"),
							subtitle: __("Review and maintain branch-scoped disease outbreak events used by VCN / NADIS regulatory reporting."),
							actionLabel: this.canCreate ? __("New Outbreak") : "",
							onAction: this.newOutbreak,
						}),
						filters: () => this.renderFilterBar(),
						default: () => h("main", { class: "vetedge-outbreak-register-root" }, [
							h("section", { class: "vetedge-outbreak-summary" }, [
								h(EdgeStatCard, { label: __("Matching Outbreaks"), value: this.total, icon: "activity" }),
								h(EdgeStatCard, { label: __("Current Page"), value: `${this.currentPage} / ${this.totalPages}`, icon: "report" }),
								h(EdgeStatCard, { label: __("Register Access"), value: this.canWrite ? __("Read / Write") : __("Read Only"), icon: "shield" }),
							]),
							h("div", { class: "vetedge-outbreak-note" }, __("Rows are permission-aware and Branch-scoped. The register does not bypass Veterinary Disease Outbreak validation or NADIS export controls.")),
							this.renderContent(),
						]),
					}),
				});
			},
		};

		$loading.remove();
		const mount = document.createElement("div");
		mount.className = "vetedge-outbreak-register-root";
		$(wrapper.page.body).append(mount);
		wrapper.vue_app = runtime.createEdgeApp(component);
		wrapper.vue_app.mount(mount);
	});
};
