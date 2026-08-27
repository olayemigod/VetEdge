const VETEDGE_ADMIN_API = Object.freeze({
	page: "vetedge.services.administration_workspace.get_administration_page",
	document: "vetedge.services.administration_workspace.get_administration_document",
	save: "vetedge.services.administration_workspace.save_administration_document",
	remove: "vetedge.services.administration_workspace.delete_administration_document",
	link: "vetedge.services.administration_workspace.search_administration_link",
});

const VETEDGE_ADMIN_RESOURCES = Object.freeze([
	{ key: "notification-preferences", label: __("Notification Preferences") },
	{ key: "notification-logs", label: __("Notification Delivery Log") },
	{ key: "notification-items", label: __("Notification Items") },
	{ key: "role-bundles", label: __("Role Bundles") },
	{ key: "license-profile", label: __("Legacy License Profile") },
]);
const VETEDGE_ADMIN_STYLE_ID = "vetedge-administration-style";

function ensureVetEdgeAdministrationStyles() {
	if (document.getElementById(VETEDGE_ADMIN_STYLE_ID)) return;
	const style = document.createElement("style");
	style.id = VETEDGE_ADMIN_STYLE_ID;
	style.textContent = `
		.vetedge-administration-root,.vetedge-administration-root .edge-app-shell,.vetedge-administration-root .edge-shell-body,.vetedge-administration-root .edge-shell-main,.vetedge-administration-root .edge-page-layout{width:100%;max-width:none;min-width:0}
		.vetedge-administration-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 16px}
		.vetedge-administration-tabs .edge-button.is-active{background:var(--edge-color-brand-600);border-color:var(--edge-color-brand-600);color:#fff}
		.vetedge-administration-filter-grid{display:grid;grid-template-columns:repeat(4,minmax(11rem,1fr));gap:12px;align-items:end;width:100%}
		.vetedge-administration-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
		.vetedge-administration-summary{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px;color:var(--edge-color-ink-500)}
		.vetedge-administration-summary strong{color:var(--edge-color-ink-950)}
		.vetedge-administration-note{padding:12px 14px;border:1px solid var(--edge-color-border);border-radius:10px;background:var(--edge-color-surface-soft);color:var(--edge-color-ink-700);margin-bottom:14px}
		.vetedge-administration-error{padding:10px 12px;border:1px solid var(--edge-color-danger-200,#fecaca);border-radius:8px;background:var(--edge-color-danger-50,#fef2f2);color:var(--edge-color-danger-700,#b91c1c);margin-bottom:12px}
		.vetedge-administration-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
		.vetedge-administration-detail{padding:12px;border:1px solid var(--edge-color-border);border-radius:10px;background:var(--edge-color-surface)}
		.vetedge-administration-detail small{display:block;color:var(--edge-color-ink-500);margin-bottom:4px}
		.vetedge-administration-detail strong,.vetedge-administration-detail pre{color:var(--edge-color-ink-950);white-space:pre-wrap;overflow-wrap:anywhere;margin:0}
		.vetedge-administration-role-editor{margin-top:14px;padding-top:14px;border-top:1px solid var(--edge-color-border)}
		.vetedge-administration-role-list{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
		.vetedge-administration-role-chip{display:inline-flex;align-items:center;gap:7px;padding:6px 9px;border:1px solid var(--edge-color-border);border-radius:999px;background:var(--edge-color-surface-soft)}
		.vetedge-administration-role-chip button{border:0;background:transparent;cursor:pointer;color:inherit;font:inherit;padding:0}
		@media(max-width:1000px){.vetedge-administration-filter-grid{grid-template-columns:repeat(2,minmax(10rem,1fr))}}
		@media(max-width:650px){.vetedge-administration-filter-grid,.vetedge-administration-detail-grid{grid-template-columns:1fr}.vetedge-administration-actions,.vetedge-administration-actions .edge-button{width:100%}}
	`;
	document.head.appendChild(style);
}

function vetEdgeAdministrationProfile() {
	const boot = frappe.boot || {};
	const user = frappe.session?.user || "";
	const info = boot.user_info?.[user] || {};
	return {
		tenantName: boot.sysdefaults?.company || "",
		branchName: frappe.defaults?.get_user_default?.("branch") || __("All Branches"),
		userName: info.fullname || info.full_name || user,
	};
}

function vetEdgeAdministrationParams() {
	const params = new URLSearchParams(window.location.search || "");
	const resource = params.get("resource") || "notification-preferences";
	return {
		resource: VETEDGE_ADMIN_RESOURCES.some((item) => item.key === resource) ? resource : "notification-preferences",
		name: params.get("name") || "",
		isNew: params.get("new") === "1",
	};
}

frappe.pages["vetedge-administration"].on_page_load = function (wrapper) {
	wrapper.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Veterinary Administration"), single_column: true });
};

frappe.pages["vetedge-administration"].on_page_show = function (wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;
	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	ensureVetEdgeAdministrationStyles();

	const $loading = $("<div class='p-6 text-center text-muted'></div>").text(__("Loading Veterinary Administration...")).appendTo(page.body);
	const fail = (message) => {
		$loading.remove();
		$("<div class='alert alert-danger p-6 text-center'></div>").text(message || __("Veterinary Administration failed to load.")).appendTo(page.body);
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
			fail(__("Veterinary Administration requires the current EdgeSuite UI. Missing: {0}", [missing.join(", ")]));
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
		const initial = vetEdgeAdministrationParams();
		const profile = vetEdgeAdministrationProfile();

		const component = {
			name: "VetEdgeAdministration",
			data() {
				return {
					resource: initial.resource,
					loading: true,
					error: "",
					search: "",
					filters: {},
					pageStart: 0,
					pageLength: 25,
					list: { rows: [], total: 0, start: 0, page_length: 25, columns: [], filters: [], permissions: {}, mode: "readonly", title: "", subtitle: "" },
					editor: { open: false, loading: false, saving: false, error: "", document: null, model: {}, roles: [], roleSearch: "", dirty: false },
					confirmDeleteOpen: false,
					deleteBusy: false,
				};
			},
			computed: {
				canCreate() { return Boolean(this.list.permissions?.create && ["editable", "role_bundle"].includes(this.list.mode)); },
				canEdit() {
					const doc = this.editor.document;
					return Boolean(doc && ["editable", "role_bundle"].includes(doc.mode) && (doc.is_new ? this.list.permissions?.create : doc.permissions?.write));
				},
				canDelete() { return Boolean(this.editor.document && !this.editor.document.is_new && ["editable", "role_bundle"].includes(this.editor.document.mode) && this.editor.document.permissions?.delete); },
				currentPage() { return Math.floor(Number(this.list.start || 0) / Math.max(1, Number(this.list.page_length || this.pageLength))) + 1; },
				totalPages() { return Math.max(1, Math.ceil(Number(this.list.total || 0) / Math.max(1, Number(this.list.page_length || this.pageLength)))); },
				hasPrevious() { return Number(this.list.start || 0) > 0; },
				hasNext() { return Number(this.list.start || 0) + (this.list.rows?.length || 0) < Number(this.list.total || 0); },
				resourceLabel() { return VETEDGE_ADMIN_RESOURCES.find((item) => item.key === this.resource)?.label || __("Veterinary Administration"); },
			},
			async mounted() {
				await this.refresh();
				if (initial.name) await this.openDocument(initial.name, false);
				else if (initial.isNew && this.canCreate) await this.openDocument(null, false);
				else if (this.list.mode === "single_readonly" && this.list.rows?.[0]?.name) await this.openDocument(this.list.rows[0].name, false);
			},
			methods: {
				async call(method, args = {}) {
					const response = await frappe.call(method, args);
					return response?.message;
				},
				message(error, fallback) {
					return error?.message || error?._server_messages || error?.exc_type || fallback || __("The requested administration operation could not be completed.");
				},
				pageFilters() { return Object.fromEntries(Object.entries(this.filters || {}).filter(([, value]) => value !== undefined && value !== null && String(value) !== "")); },
				async refresh() {
					this.loading = true;
					this.error = "";
					try {
						this.list = await this.call(VETEDGE_ADMIN_API.page, {
							resource: this.resource,
							search: this.search || "",
							filters: JSON.stringify(this.pageFilters()),
							start: this.pageStart,
							page_length: this.pageLength,
						});
						this.pageStart = Number(this.list.start || 0);
					} catch (error) {
						this.error = this.message(error, __("Veterinary Administration could not be loaded."));
					} finally {
						this.loading = false;
					}
				},
				async switchResource(resource) {
					if (!resource || resource === this.resource || this.loading) return;
					this.editor.open = false;
					this.resource = resource;
					this.search = "";
					this.filters = {};
					this.pageStart = 0;
					this.updateRoute();
					await this.refresh();
					if (this.list.mode === "single_readonly" && this.list.rows?.[0]?.name) await this.openDocument(this.list.rows[0].name, false);
				},
				updateRoute(doc = null) {
					const url = new URL(window.location.href);
					url.pathname = "/desk/vetedge-administration";
					url.search = "";
					url.searchParams.set("resource", this.resource);
					if (doc?.is_new) url.searchParams.set("new", "1");
					else if (doc?.name && doc.mode !== "single_readonly") url.searchParams.set("name", doc.name);
					window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}`);
				},
				async applyFilters() { this.pageStart = 0; await this.refresh(); },
				async resetFilters() { this.search = ""; this.filters = {}; this.pageStart = 0; await this.refresh(); },
				async previousPage() { this.pageStart = Math.max(0, this.pageStart - this.pageLength); await this.refresh(); },
				async nextPage() { this.pageStart += this.pageLength; await this.refresh(); },
				setFilter(fieldname, value) { this.filters = { ...this.filters, [fieldname]: value ?? "" }; },
				selectOptions(field, allLabel = __("All")) {
					const values = String(field?.options || "").split("\n").map((value) => value.trim()).filter(Boolean);
					return [{ value: "", label: allLabel }, ...values.map((value) => ({ value, label: value }))];
				},
				async genericLinkSearch(field, term) {
					if (!field?.options) return [];
					const response = await frappe.call("frappe.desk.search.search_link", { doctype: field.options, txt: term || "", page_length: 20, ignore_user_permissions: 0 });
					return response?.message || [];
				},
				async roleSearch(term) {
					return (await this.call(VETEDGE_ADMIN_API.link, { resource: "role-bundles", fieldname: "role", query: term || "", page_length: 20 })) || [];
				},
				async openDocument(name = null, updateRoute = true) {
					this.editor = { open: true, loading: true, saving: false, error: "", document: null, model: {}, roles: [], roleSearch: "", dirty: false };
					try {
						const doc = await this.call(VETEDGE_ADMIN_API.document, { resource: this.resource, name });
						this.editor.document = doc;
						this.editor.model = JSON.parse(JSON.stringify(doc?.values || {}));
						this.editor.roles = Array.isArray(doc?.roles) ? [...doc.roles] : [];
						if (updateRoute) this.updateRoute(doc);
					} catch (error) {
						this.editor.error = this.message(error, __("Administration record could not be opened."));
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
					this.updateRoute();
				},
				onModelUpdate(value) { this.editor.model = value || {}; this.editor.dirty = true; },
				addRole(value) {
					const role = String(value || "").trim();
					if (!role || this.editor.roles.includes(role)) return;
					this.editor.roles = [...this.editor.roles, role];
					this.editor.roleSearch = "";
					this.editor.dirty = true;
				},
				removeRole(role) {
					if (!this.canEdit) return;
					this.editor.roles = this.editor.roles.filter((item) => item !== role);
					this.editor.dirty = true;
				},
				async saveDocument() {
					if (!this.canEdit || this.editor.saving) return;
					this.editor.saving = true;
					this.editor.error = "";
					try {
						const doc = await this.call(VETEDGE_ADMIN_API.save, {
							resource: this.resource,
							name: this.editor.document?.is_new ? null : this.editor.document?.name,
							modified: this.editor.document?.modified || null,
							values: JSON.stringify(this.editor.model || {}),
							roles: this.editor.document?.mode === "role_bundle" ? JSON.stringify(this.editor.roles || []) : null,
						});
						this.editor.document = doc;
						this.editor.model = JSON.parse(JSON.stringify(doc?.values || {}));
						this.editor.roles = Array.isArray(doc?.roles) ? [...doc.roles] : [];
						this.editor.dirty = false;
						this.updateRoute(doc);
						frappe.show_alert({ message: __("Administration record saved"), indicator: "green" });
						await this.refresh();
						this.editor.saving = false;
						this.closeEditor();
					} catch (error) {
						this.editor.error = this.message(error, __("Administration record could not be saved."));
					} finally {
						this.editor.saving = false;
					}
				},
				async deleteDocument() {
					if (!this.canDelete || this.deleteBusy) return;
					this.deleteBusy = true;
					this.editor.error = "";
					try {
						await this.call(VETEDGE_ADMIN_API.remove, { resource: this.resource, name: this.editor.document.name });
						frappe.show_alert({ message: __("Administration record deleted"), indicator: "green" });
						this.confirmDeleteOpen = false;
						this.editor.open = false;
						this.updateRoute();
						this.pageStart = 0;
						await this.refresh();
					} catch (error) {
						this.editor.error = this.message(error, __("Administration record could not be deleted."));
						this.confirmDeleteOpen = false;
					} finally {
						this.deleteBusy = false;
					}
				},
				renderFilter(field) {
					const value = this.filters[field.fieldname] ?? "";
					if (field.fieldtype === "Check") {
						return h(EdgeDropdown, { modelValue: String(value), label: field.label, options: [{ value: "", label: __("All") }, { value: "1", label: __("Yes") }, { value: "0", label: __("No") }], "onUpdate:modelValue": (next) => this.setFilter(field.fieldname, next ?? "") });
					}
					if (field.fieldtype === "Select") {
						return h(EdgeDropdown, { modelValue: value, label: field.label, options: this.selectOptions(field), "onUpdate:modelValue": (next) => this.setFilter(field.fieldname, next || "") });
					}
					if (field.fieldtype === "Link") {
						return h(EdgeLinkField, { modelValue: value, selectedLabel: value || "", label: field.label, placeholder: __("All"), allowClear: true, searcher: (term) => this.genericLinkSearch(field, term), "onUpdate:modelValue": (next) => this.setFilter(field.fieldname, next || "") });
					}
					return h(EdgeInput, { modelValue: value, label: field.label, "onUpdate:modelValue": (next) => this.setFilter(field.fieldname, next || "") });
				},
				renderFilters() {
					return h("div", { class: "vetedge-administration-filter-grid" }, [
						h(EdgeInput, { modelValue: this.search, type: "search", label: __("Search"), placeholder: __("Search this administration resource"), "onUpdate:modelValue": (value) => { this.search = value || ""; }, onKeyup: (event) => { if (event.key === "Enter") this.applyFilters(); } }),
						...(this.list.filters || []).map((field) => this.renderFilter(field)),
					]);
				},
				renderTable() {
					if (!this.list.rows?.length) {
						return h(EdgeEmptyState, { title: __("No records found"), description: this.list.subtitle || __("Change the filters or create a record if permitted."), actionLabel: this.canCreate ? __("Add {0}", [this.list.singular || __("Record")]) : "", onAction: this.openNew });
					}
					return h("div", [
						h("div", { class: "vetedge-administration-summary" }, [
							h("span", [__("Total records: "), h("strong", String(this.list.total || 0))]),
							h("span", [__("Page "), h("strong", `${this.currentPage} / ${this.totalPages}`)]),
						]),
						h(EdgeDataTable, {
							columns: this.list.columns || [], rows: this.list.rows || [], rowKey: "name",
							actions: [{ key: "open", label: __("Open"), primary: true }],
							onRowClick: this.openRow, onAction: this.handleRowAction,
						}, {
							footer: () => this.list.mode === "single_readonly" ? null : h("div", { class: "vetedge-administration-actions" }, [
								h("button", { class: "edge-button edge-button--compact", type: "button", disabled: !this.hasPrevious, onClick: this.previousPage }, __("Previous")),
								h("button", { class: "edge-button edge-button--compact", type: "button", disabled: !this.hasNext, onClick: this.nextPage }, __("Next")),
							]),
						}),
					]);
				},
				renderDetails(doc) {
					const details = doc?.details || [];
					return h("div", { class: "vetedge-administration-detail-grid" }, details.map((field) => {
						const value = field.fieldtype === "Check" ? (Number(field.value) ? __("Yes") : __("No")) : (field.value ?? "");
						const long = ["Long Text", "Small Text", "Text", "Code"].includes(field.fieldtype);
						return h("div", { class: "vetedge-administration-detail" }, [h("small", field.label), long ? h("pre", String(value || "—")) : h("strong", String(value || "—"))]);
					}));
				},
				renderRoleEditor() {
					if (this.editor.document?.mode !== "role_bundle") return null;
					return h("div", { class: "vetedge-administration-role-editor" }, [
						h(EdgeLinkField, { modelValue: this.editor.roleSearch, selectedLabel: this.editor.roleSearch || "", label: __("Add Role"), placeholder: __("Search permitted Frappe Roles"), disabled: !this.canEdit, searcher: this.roleSearch, allowClear: true, "onUpdate:modelValue": (value) => this.addRole(value) }),
						h("div", { class: "vetedge-administration-role-list" }, (this.editor.roles || []).map((role) => h("span", { class: "vetedge-administration-role-chip" }, [h("span", role), this.canEdit ? h("button", { type: "button", title: __("Remove role"), onClick: () => this.removeRole(role) }, "×") : null].filter(Boolean)))),
					]);
				},
				renderEditor() {
					if (!this.editor.open) return null;
					const doc = this.editor.document;
					return h(EdgeModal, {
						key: "vetedge-administration-editor-modal",
						open: true,
						title: doc?.title || this.list.singular || __("Administration Record"),
						subtitle: this.list.subtitle || "",
						size: "lg",
						busy: this.editor.loading || this.editor.saving,
						onClose: this.closeEditor,
					}, {
						default: () => this.editor.loading ? h(EdgeLoadingState, { message: __("Loading administration record...") }) : [
							this.editor.error ? h("div", { class: "vetedge-administration-error", role: "alert" }, this.editor.error) : null,
							doc?.mode === "single_readonly" ? h("div", { class: "vetedge-administration-note" }, __("Compatibility information only. Subscription, activation and runtime access remain controlled by the Platform where enabled.")) : null,
							doc?.schema ? h(EdgeDocumentForm, { schema: doc.schema, modelValue: this.editor.model, errors: {}, readonly: !this.canEdit, linkSearcher: (field, term) => this.genericLinkSearch(field, term), "onUpdate:modelValue": this.onModelUpdate }) : this.renderDetails(doc),
							this.renderRoleEditor(),
						].filter(Boolean),
						footer: () => h("div", { class: "vetedge-administration-actions" }, [
							this.canDelete ? h("button", { class: "edge-button edge-button--danger", type: "button", disabled: this.editor.saving, onClick: () => { this.confirmDeleteOpen = true; } }, __("Delete")) : null,
							h("button", { class: "edge-button", type: "button", disabled: this.editor.saving, onClick: this.closeEditor }, __("Close")),
							this.canEdit ? h("button", { class: "edge-button edge-button--primary", type: "button", disabled: this.editor.saving || this.editor.loading, onClick: this.saveDocument }, this.editor.saving ? __("Saving...") : __("Save")) : null,
						].filter(Boolean)),
					});
				},
				renderDeleteConfirmation() {
					if (!this.confirmDeleteOpen) return null;
					return h(EdgeModal, { key: "vetedge-administration-delete-modal", open: true, title: __("Delete administration record"), subtitle: this.editor.document?.title || this.editor.document?.name || "", busy: this.deleteBusy, onClose: () => { if (!this.deleteBusy) this.confirmDeleteOpen = false; } }, {
						default: () => h("p", __("Delete this record? Frappe link integrity and permissions will still be enforced.")),
						footer: () => h("div", { class: "vetedge-administration-actions" }, [
							h("button", { class: "edge-button", type: "button", disabled: this.deleteBusy, onClick: () => { this.confirmDeleteOpen = false; } }, __("Cancel")),
							h("button", { class: "edge-button edge-button--danger", type: "button", disabled: this.deleteBusy, onClick: this.deleteDocument }, this.deleteBusy ? __("Deleting...") : __("Delete")),
						]),
					});
				},
			},
			render() {
				return h(EdgeAppShell, { product: "vetedge", title: "Veterinary", tenantName: profile.tenantName, branchName: profile.branchName, userName: profile.userName, activeRoute: "/desk/vetedge-administration" }, {
					default: () => h(EdgePageLayout, {}, {
						header: () => h(EdgePageHeader, { eyebrow: __("Configuration"), title: this.list.title || this.resourceLabel, subtitle: this.list.subtitle || __("Permission-aware Veterinary administration."), actionLabel: this.canCreate ? __("Add {0}", [this.list.singular || __("Record")]) : "", onAction: this.openNew }),
						default: () => [
							h("nav", { class: "vetedge-administration-tabs", "aria-label": __("Veterinary administration resources") }, VETEDGE_ADMIN_RESOURCES.map((item) => h("button", { class: ["edge-button", { "is-active": item.key === this.resource }], type: "button", onClick: () => this.switchResource(item.key) }, item.label))),
							this.list.mode === "single_readonly" ? h("div", { class: "vetedge-administration-note" }, __("Legacy License Profile is read-only. It must not become a second source of truth for Platform subscription or activation.")) : null,
							this.list.mode === "single_readonly" ? null : h(EdgeFilterBar, { title: __("Filters") }, { default: () => this.renderFilters(), actions: () => h("div", { class: "vetedge-administration-actions" }, [h("button", { class: "edge-button edge-button--primary", type: "button", disabled: this.loading, onClick: this.applyFilters }, this.loading ? __("Loading...") : __("Apply")), h("button", { class: "edge-button", type: "button", disabled: this.loading, onClick: this.resetFilters }, __("Reset"))]) }),
							this.error ? h(EdgeErrorState, { title: __("Veterinary Administration could not load"), message: this.error, actionLabel: __("Try again"), onRetry: this.refresh }) : this.loading ? h(EdgeLoadingState, { message: __("Loading Veterinary Administration..."), skeleton: true }) : this.renderTable(),
							this.renderEditor(),
							this.renderDeleteConfirmation(),
						].filter(Boolean),
					}),
				});
			},
		};

		try {
			$loading.remove();
			const root = $("<div class='vetedge-administration-root' data-edge-product='vetedge'></div>").appendTo(page.body);
			wrapper.vue_app = runtime.createEdgeApp(component);
			wrapper.vue_app.mount(root[0]);
		} catch (error) {
			console.error("Error mounting Veterinary Administration:", error);
			fail(__("Error mounting Veterinary Administration: {0}", [error.message || String(error)]));
		}
	});
};