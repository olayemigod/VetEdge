const VETEDGE_CARE_LOCATION_API = Object.freeze({
	page: "vetedge.services.care_location_workspace.get_care_location_page",
	document: "vetedge.services.care_location_workspace.get_care_location_document",
	save: "vetedge.services.care_location_workspace.save_care_location_document",
	remove: "vetedge.services.care_location_workspace.delete_care_location_document",
	link: "vetedge.services.care_location_workspace.search_care_location_link",
});

const VETEDGE_CARE_LOCATION_TYPES = ["", "Ward", "Kennel", "Cage", "ICU", "Isolation", "Recovery", "General"].map((value) => ({ value, label: value || __("All Location Types") }));
const VETEDGE_CARE_LOCATION_STATUSES = ["", "Available", "Occupied", "Cleaning", "Maintenance", "Inactive"].map((value) => ({ value, label: value || __("All Statuses") }));
const VETEDGE_CARE_LOCATION_ENABLED = [
	{ value: "", label: __("All Records") },
	{ value: "1", label: __("Enabled") },
	{ value: "0", label: __("Disabled") },
];
const VETEDGE_CARE_LOCATION_STYLE_ID = "vetedge-care-location-style";

function ensureVetEdgeCareLocationStyles() {
	if (document.getElementById(VETEDGE_CARE_LOCATION_STYLE_ID)) return;
	const style = document.createElement("style");
	style.id = VETEDGE_CARE_LOCATION_STYLE_ID;
	style.textContent = `
		.vetedge-care-location-root,.vetedge-care-location-root .edge-app-shell,.vetedge-care-location-root .edge-shell-body,.vetedge-care-location-root .edge-shell-main,.vetedge-care-location-root .edge-page-layout{width:100%;max-width:none;min-width:0}
		.vetedge-care-location-filters{display:grid;grid-template-columns:repeat(5,minmax(10rem,1fr));gap:12px;align-items:end;width:100%}
		.vetedge-care-location-summary{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:0 0 14px;color:var(--edge-color-ink-500)}
		.vetedge-care-location-summary strong{color:var(--edge-color-ink-950)}
		.vetedge-care-location-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
		.vetedge-care-location-editor-error{margin-bottom:12px;padding:10px 12px;border:1px solid var(--edge-color-danger-200,#fecaca);border-radius:8px;color:var(--edge-color-danger-700,#b91c1c);background:var(--edge-color-danger-50,#fef2f2)}
		.vetedge-care-location-empty-scope{margin-bottom:14px;padding:12px;border:1px solid var(--edge-color-warning-200,#fde68a);border-radius:8px;background:var(--edge-color-warning-50,#fffbeb);color:var(--edge-color-ink-700)}
		@media(max-width:1100px){.vetedge-care-location-filters{grid-template-columns:repeat(3,minmax(10rem,1fr))}}
		@media(max-width:760px){.vetedge-care-location-filters{grid-template-columns:repeat(2,minmax(9rem,1fr))}}
		@media(max-width:560px){.vetedge-care-location-filters{grid-template-columns:1fr}.vetedge-care-location-actions,.vetedge-care-location-actions .edge-button{width:100%}}
	`;
	document.head.appendChild(style);
}

function careLocationProfile() {
	const boot = frappe.boot || {};
	const user = frappe.session?.user || "";
	const info = boot.user_info?.[user] || {};
	return {
		tenantName: boot.sysdefaults?.company || "",
		branchName: frappe.defaults?.get_user_default?.("branch") || "All Branches",
		userName: info.fullname || info.full_name || user,
	};
}

function careLocationRouteParams() {
	const params = new URLSearchParams(window.location.search || "");
	return {
		name: params.get("name") || "",
		isNew: params.get("new") === "1",
		branch: params.get("branch") || "",
	};
}

frappe.pages["vetedge-care-locations"].on_page_load = function (wrapper) {
	wrapper.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Care Locations"), single_column: true });
};

frappe.pages["vetedge-care-locations"].on_page_show = function (wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;
	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	ensureVetEdgeCareLocationStyles();

	const $loading = $("<div class='p-6 text-center text-muted'></div>").text(__("Loading Care Locations...")).appendTo(page.body);
	const fail = (message) => {
		$loading.remove();
		$("<div class='alert alert-danger p-6 text-center'></div>").text(message || __("Care Locations failed to load.")).appendTo(page.body);
	};

	frappe.require("edgeui.bundle.js", () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = [
			"EdgeAppShell", "EdgePageLayout", "EdgePageHeader", "EdgeFilterBar", "EdgeDataTable",
			"EdgeDocumentForm", "EdgeLinkField", "EdgeDropdown", "EdgeInput", "EdgeModal",
			"EdgeLoadingState", "EdgeEmptyState", "EdgeErrorState",
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || !runtime?.Vue?.h || missing.length) {
			fail(__("Care Locations require the current EdgeSuite UI. Missing: {0}", [missing.join(", ")]));
			return;
		}

		window.VetEdgeProfessionalUI?.install?.();
		window.VetEdgeUIBridge?.install?.();
		window.VetEdgeNavigationRecovery?.install?.();

		const h = runtime.Vue.h;
		const {
			EdgeAppShell, EdgePageLayout, EdgePageHeader, EdgeFilterBar, EdgeDataTable,
			EdgeDocumentForm, EdgeLinkField, EdgeDropdown, EdgeInput, EdgeModal,
			EdgeLoadingState, EdgeEmptyState, EdgeErrorState,
		} = runtime.components;
		const profile = careLocationProfile();
		const initial = careLocationRouteParams();

		const component = {
			name: "VetEdgeCareLocations",
			data() {
				return {
					loading: true,
					error: "",
					search: "",
					filters: { branch: initial.branch || "", location_type: "", status: "", enabled: "" },
					pageStart: 0,
					pageLength: 25,
					list: { rows: [], total: 0, start: 0, page_length: 25, columns: [], permissions: {}, branch_scope_empty: false },
					editor: { open: false, loading: false, saving: false, error: "", document: null, model: {}, dirty: false },
					confirmDeleteOpen: false,
					deleteBusy: false,
				};
			},
			computed: {
				canCreate() { return Boolean(this.list.permissions?.create); },
				canEdit() {
					const doc = this.editor.document;
					return Boolean(doc?.is_new ? this.list.permissions?.create : doc?.permissions?.write);
				},
				canDelete() { return Boolean(!this.editor.document?.is_new && this.editor.document?.permissions?.delete); },
				currentPage() { return Math.floor(Number(this.list.start || 0) / Math.max(1, Number(this.list.page_length || this.pageLength))) + 1; },
				totalPages() { return Math.max(1, Math.ceil(Number(this.list.total || 0) / Math.max(1, Number(this.list.page_length || this.pageLength)))); },
				hasPrevious() { return Number(this.list.start || 0) > 0; },
				hasNext() { return Number(this.list.start || 0) + (this.list.rows?.length || 0) < Number(this.list.total || 0); },
			},
			async mounted() {
				await this.refresh();
				if (initial.name) await this.openDocument(initial.name, false);
				else if (initial.isNew) await this.openDocument(null, false);
			},
			methods: {
				async call(method, args = {}) {
					const response = await frappe.call(method, args);
					return response?.message;
				},
				message(error, fallback) {
					return error?.message || error?._server_messages || error?.exc_type || fallback || __("The requested operation could not be completed.");
				},
				pageFilters() {
					return Object.fromEntries(Object.entries(this.filters).filter(([, value]) => value !== undefined && value !== null && String(value) !== ""));
				},
				async refresh({ silent = false } = {}) {
					if (!silent) {
						this.loading = true;
						this.error = "";
					}
					try {
						const nextList = await this.call(VETEDGE_CARE_LOCATION_API.page, {
							search: this.search || "",
							filters: JSON.stringify(this.pageFilters()),
							start: this.pageStart,
							page_length: this.pageLength,
						});
						this.list = nextList;
						this.pageStart = Number(this.list.start || 0);
						if (!silent) this.error = "";
					} catch (error) {
						const message = this.message(error, __("Care Locations could not be loaded."));
						if (silent) {
							console.warn("Care Locations background refresh failed:", error);
							frappe.show_alert({ message: __("Care Location saved, but the list could not refresh."), indicator: "orange" });
						} else {
							this.error = message;
						}
					} finally {
						if (!silent) this.loading = false;
					}
				},
				async applyFilters() { this.pageStart = 0; await this.refresh(); },
				async resetFilters() { this.search = ""; this.filters = { branch: "", location_type: "", status: "", enabled: "" }; this.pageStart = 0; await this.refresh(); },
				async previousPage() { this.pageStart = Math.max(0, this.pageStart - this.pageLength); await this.refresh(); },
				async nextPage() { this.pageStart += this.pageLength; await this.refresh(); },
				async searchBranches(query) {
					return (await this.call(VETEDGE_CARE_LOCATION_API.link, { fieldname: "branch", query: query || "", page_length: 20 })) || [];
				},
				async linkSearch(field, query) {
					return (await this.call(VETEDGE_CARE_LOCATION_API.link, { fieldname: field?.fieldname || "", query: query || "", page_length: 20 })) || [];
				},
				setFilter(fieldname, value) { this.filters = { ...this.filters, [fieldname]: value ?? "" }; },
				setEditorRoute(doc) {
					const url = new URL(window.location.href);
					url.pathname = "/desk/vetedge-care-locations";
					url.searchParams.delete("name");
					url.searchParams.delete("new");
					if (doc?.is_new) url.searchParams.set("new", "1");
					else if (doc?.name) url.searchParams.set("name", doc.name);
					window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}`);
				},
				clearEditorRoute() {
					const url = new URL(window.location.href);
					url.pathname = "/desk/vetedge-care-locations";
					url.searchParams.delete("name");
					url.searchParams.delete("new");
					window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}`);
				},
				async openDocument(name = null, updateRoute = true) {
					this.editor = { open: true, loading: true, saving: false, error: "", document: null, model: {}, dirty: false };
					try {
						const doc = await this.call(VETEDGE_CARE_LOCATION_API.document, { name });
						this.editor.document = doc;
						this.editor.model = JSON.parse(JSON.stringify(doc?.values || {}));
						if (updateRoute) this.setEditorRoute(doc);
					} catch (error) {
						this.editor.error = this.message(error, __("Care Location could not be opened."));
					} finally {
						this.editor.loading = false;
					}
				},
				openNew() { if (this.canCreate) this.openDocument(null); },
				openRow(row) { if (row?.name) this.openDocument(row.name); },
				handleRowAction(payload) { if (payload?.action?.key === "open") this.openRow(payload.row); },
				closeEditor() {
					if (this.editor.saving || this.deleteBusy) return;
					this.editor.open = false;
					this.confirmDeleteOpen = false;
					this.clearEditorRoute();
				},
				onModelUpdate(value) { this.editor.model = value || {}; this.editor.dirty = true; },
				async saveDocument() {
					if (!this.canEdit || this.editor.saving) return;
					const wasNew = Boolean(this.editor.document?.is_new);
					this.editor.saving = true;
					this.editor.error = "";
					try {
						const doc = await this.call(VETEDGE_CARE_LOCATION_API.save, {
							name: wasNew ? null : this.editor.document?.name,
							modified: this.editor.document?.modified || null,
							values: JSON.stringify(this.editor.model || {}),
						});
						this.editor.document = doc;
						this.editor.model = JSON.parse(JSON.stringify(doc?.values || {}));
						this.editor.dirty = false;
						this.editor.saving = false;
						this.editor.open = false;
						this.confirmDeleteOpen = false;
						this.clearEditorRoute();
						if (wasNew) this.pageStart = 0;
						frappe.show_alert({ message: __("Care Location saved"), indicator: "green" });
						await this.refresh({ silent: true });
					} catch (error) {
						this.editor.error = this.message(error, __("Care Location could not be saved."));
					} finally {
						this.editor.saving = false;
					}
				},
				requestDelete() { if (this.canDelete) this.confirmDeleteOpen = true; },
				async deleteDocument() {
					if (!this.canDelete || this.deleteBusy) return;
					this.deleteBusy = true;
					this.editor.error = "";
					try {
						await this.call(VETEDGE_CARE_LOCATION_API.remove, { name: this.editor.document.name });
						frappe.show_alert({ message: __("Care Location deleted"), indicator: "green" });
						this.confirmDeleteOpen = false;
						this.editor.open = false;
						this.clearEditorRoute();
						this.pageStart = 0;
						await this.refresh({ silent: true });
					} catch (error) {
						this.editor.error = this.message(error, __("Care Location could not be deleted."));
						this.confirmDeleteOpen = false;
					} finally {
						this.deleteBusy = false;
					}
				},
				renderFilters() {
					return h("div", { class: "vetedge-care-location-filters" }, [
						h(EdgeInput, { modelValue: this.search, type: "search", label: __("Search"), placeholder: __("Location, Branch, type or status"), "onUpdate:modelValue": (value) => { this.search = value || ""; }, onKeyup: (event) => { if (event.key === "Enter") this.applyFilters(); } }),
						h(EdgeLinkField, { modelValue: this.filters.branch, selectedLabel: this.filters.branch || "", label: __("Branch"), placeholder: __("All permitted Branches"), searcher: this.searchBranches, allowClear: true, "onUpdate:modelValue": (value) => this.setFilter("branch", value || "") }),
						h(EdgeDropdown, { modelValue: this.filters.location_type, label: __("Location Type"), options: VETEDGE_CARE_LOCATION_TYPES, "onUpdate:modelValue": (value) => this.setFilter("location_type", value || "") }),
						h(EdgeDropdown, { modelValue: this.filters.status, label: __("Status"), options: VETEDGE_CARE_LOCATION_STATUSES, "onUpdate:modelValue": (value) => this.setFilter("status", value || "") }),
						h(EdgeDropdown, { modelValue: this.filters.enabled, label: __("Enabled"), options: VETEDGE_CARE_LOCATION_ENABLED, "onUpdate:modelValue": (value) => this.setFilter("enabled", value ?? "") }),
					]);
				},
				renderTable() {
					if (this.list.branch_scope_empty) {
						return h("div", { class: "vetedge-care-location-empty-scope" }, __("No Veterinary Branch is assigned to your account, so Care Locations are hidden until Branch access is configured."));
					}
					if (!this.list.rows?.length) {
						return h(EdgeEmptyState, { title: __("No Care Locations found"), description: __("Change the filters or add a Care Location for an authorised Branch."), actionLabel: this.canCreate ? __("Add Care Location") : "", onAction: this.openNew });
					}
					return h("div", [
						h("div", { class: "vetedge-care-location-summary" }, [
							h("span", [__("Total records: "), h("strong", String(this.list.total || 0))]),
							h("span", [__("Page "), h("strong", `${this.currentPage} / ${this.totalPages}`)]),
						]),
						h(EdgeDataTable, {
							columns: this.list.columns || [], rows: this.list.rows || [], rowKey: "name",
							actions: [{ key: "open", label: __("Open"), primary: true }],
							onRowClick: this.openRow, onAction: this.handleRowAction,
						}, {
							footer: () => h("div", { class: "vetedge-care-location-actions" }, [
								h("button", { class: "edge-button edge-button--compact", type: "button", disabled: !this.hasPrevious, onClick: this.previousPage }, __("Previous")),
								h("button", { class: "edge-button edge-button--compact", type: "button", disabled: !this.hasNext, onClick: this.nextPage }, __("Next")),
							]),
						}),
					]);
				},
				renderEditor() {
					const doc = this.editor.document;
					return h(EdgeModal, {
						open: this.editor.open,
						title: doc?.title || (doc?.is_new ? __("Add Care Location") : __("Care Location")),
						subtitle: __("Maintain Branch-aware wards, kennels, cages, ICU, isolation and recovery locations."),
						size: "lg",
						busy: this.editor.loading || this.editor.saving,
						onClose: this.closeEditor,
					}, {
						default: () => this.editor.loading
							? h(EdgeLoadingState, { message: __("Loading Care Location...") })
							: [
								this.editor.error ? h("div", { class: "vetedge-care-location-editor-error", role: "alert" }, this.editor.error) : null,
								doc?.schema ? h(EdgeDocumentForm, {
									schema: doc.schema,
									modelValue: this.editor.model,
									errors: {},
									readonly: !this.canEdit,
									linkSearcher: this.linkSearch,
									"onUpdate:modelValue": this.onModelUpdate,
								}) : null,
							].filter(Boolean),
						footer: () => h("div", { class: "vetedge-care-location-actions" }, [
							this.canDelete ? h("button", { class: "edge-button edge-button--danger", type: "button", disabled: this.editor.saving, onClick: this.requestDelete }, __("Delete")) : null,
							h("button", { class: "edge-button", type: "button", disabled: this.editor.saving, onClick: this.closeEditor }, __("Close")),
							this.canEdit ? h("button", { class: "edge-button edge-button--primary", type: "button", disabled: this.editor.saving || this.editor.loading, onClick: this.saveDocument }, this.editor.saving ? __("Saving...") : __("Save")) : null,
						].filter(Boolean)),
					});
				},
				renderDeleteConfirmation() {
					return h(EdgeModal, {
						open: this.confirmDeleteOpen,
						title: __("Delete Care Location"),
						subtitle: this.editor.document?.title || this.editor.document?.name || "",
						busy: this.deleteBusy,
						onClose: () => { if (!this.deleteBusy) this.confirmDeleteOpen = false; },
					}, {
						default: () => h("p", __("Delete this Care Location? Linked Hospitalisation records may prevent deletion. This action cannot be undone.")),
						footer: () => h("div", { class: "vetedge-care-location-actions" }, [
							h("button", { class: "edge-button", type: "button", disabled: this.deleteBusy, onClick: () => { this.confirmDeleteOpen = false; } }, __("Cancel")),
							h("button", { class: "edge-button edge-button--danger", type: "button", disabled: this.deleteBusy, onClick: this.deleteDocument }, this.deleteBusy ? __("Deleting...") : __("Delete")),
						]),
					});
				},
			},
			render() {
				return h(EdgeAppShell, {
					product: "vetedge", title: "Veterinary", tenantName: profile.tenantName,
					branchName: this.filters.branch || profile.branchName, userName: profile.userName,
					activeRoute: "/desk/vetedge-care-locations",
				}, {
					default: () => h(EdgePageLayout, {}, {
						header: () => h(EdgePageHeader, {
							eyebrow: __("Configuration"), title: __("Care Locations"),
							subtitle: __("Manage Branch-aware wards, kennels, cages, ICU, isolation and recovery capacity."),
							actionLabel: this.canCreate ? __("Add Care Location") : "", onAction: this.openNew,
						}),
						filters: () => h(EdgeFilterBar, { title: __("Care Location Filters") }, {
							default: () => this.renderFilters(),
							actions: () => h("div", { class: "vetedge-care-location-actions" }, [
								h("button", { class: "edge-button edge-button--primary", type: "button", disabled: this.loading, onClick: this.applyFilters }, this.loading ? __("Loading...") : __("Apply")),
								h("button", { class: "edge-button", type: "button", disabled: this.loading, onClick: this.resetFilters }, __("Reset")),
							]),
						}),
						default: () => [
							this.error ? h(EdgeErrorState, { title: __("Care Locations could not load"), message: this.error, actionLabel: __("Try again"), onRetry: this.refresh })
								: this.loading ? h(EdgeLoadingState, { message: __("Loading Care Locations..."), skeleton: true }) : this.renderTable(),
							this.renderEditor(),
							this.renderDeleteConfirmation(),
						],
					}),
				});
			},
		};

		try {
			$loading.remove();
			const root = $("<div class='vetedge-care-location-root' data-edge-product='vetedge'></div>").appendTo(page.body);
			wrapper.vue_app = runtime.createEdgeApp(component);
			wrapper.vue_app.mount(root[0]);
		} catch (error) {
			console.error("Error mounting VetEdge Care Locations:", error);
			fail(__("Error mounting Care Locations: {0}", [error.message || String(error)]));
		}
	});
};