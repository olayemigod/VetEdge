const VETEDGE_BRANCH_ACCESS_API = Object.freeze({
	page: "vetedge.services.branch_access_workspace.get_branch_access_page",
	document: "vetedge.services.branch_access_workspace.get_branch_access_document",
	save: "vetedge.services.branch_access_workspace.save_branch_access_document",
	remove: "vetedge.services.branch_access_workspace.delete_branch_access_document",
	link: "vetedge.services.branch_access_workspace.search_branch_access_link",
});

const VETEDGE_BRANCH_ACCESS_RESOURCES = Object.freeze({
	"user-assignments": {
		title: __("Branch User Access"),
		singular: __("User Branch Assignment"),
		eyebrow: __("Configuration"),
	},
	"practitioner-assignments": {
		title: __("Practitioner Coverage"),
		singular: __("Practitioner Branch Assignment"),
		eyebrow: __("Configuration"),
	},
});

const VETEDGE_BRANCH_ACCESS_DISABLED = [
	{ value: "", label: __("All Assignments") },
	{ value: "0", label: __("Active") },
	{ value: "1", label: __("Disabled") },
];

function branchAccessProfile() {
	const boot = frappe.boot || {};
	const user = frappe.session?.user || "";
	const info = boot.user_info?.[user] || {};
	return {
		tenantName: boot.sysdefaults?.company || "",
		branchName: frappe.defaults?.get_user_default?.("branch") || __("All Branches"),
		userName: info.fullname || info.full_name || user,
	};
}

function branchAccessRouteParams() {
	const params = new URLSearchParams(window.location.search || "");
	const resource = params.get("resource") || "user-assignments";
	return {
		resource: VETEDGE_BRANCH_ACCESS_RESOURCES[resource] ? resource : "user-assignments",
		name: params.get("name") || "",
		isNew: params.get("new") === "1",
		branch: params.get("branch") || "",
	};
}

frappe.pages["vetedge-branch-access"].on_page_load = function (wrapper) {
	wrapper.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Branch Access"), single_column: true });
};

frappe.pages["vetedge-branch-access"].on_page_show = function (wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;
	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();

	const $loading = $("<div class='p-6 text-center text-muted'></div>").text(__("Loading Branch Access...")).appendTo(page.body);
	const fail = (message) => {
		$loading.remove();
		$("<div class='alert alert-danger p-6 text-center'></div>").text(message || __("Branch Access failed to load.")).appendTo(page.body);
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
			fail(__("Branch Access requires the current EdgeSuite UI. Missing: {0}", [missing.join(", ")]));
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
		const profile = branchAccessProfile();
		const initial = branchAccessRouteParams();

		const component = {
			name: "VetEdgeBranchAccess",
			data() {
				return {
					resource: initial.resource,
					loading: true,
					error: "",
					search: "",
					filters: { branch: initial.branch || "", disabled: "" },
					pageStart: 0,
					pageLength: 25,
					list: { rows: [], total: 0, columns: [], permissions: {}, branch_scope_empty: false },
					editor: { open: false, loading: false, saving: false, error: "", document: null, model: {} },
					confirmDeleteOpen: false,
					deleteBusy: false,
				};
			},
			computed: {
				resourceConfig() { return VETEDGE_BRANCH_ACCESS_RESOURCES[this.resource] || VETEDGE_BRANCH_ACCESS_RESOURCES["user-assignments"]; },
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
				message(error, fallback) { return error?.message || error?._server_messages || error?.exc_type || fallback; },
				pageFilters() { return Object.fromEntries(Object.entries(this.filters).filter(([, value]) => value !== undefined && value !== null && String(value) !== "")); },
				updateRoute(extra = {}) {
					const url = new URL(window.location.href);
					url.pathname = "/desk/vetedge-branch-access";
					url.search = "";
					url.searchParams.set("resource", this.resource);
					if (this.filters.branch) url.searchParams.set("branch", this.filters.branch);
					for (const [key, value] of Object.entries(extra)) if (value !== undefined && value !== null && String(value) !== "") url.searchParams.set(key, value);
					window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}`);
				},
				async refresh() {
					this.loading = true;
					this.error = "";
					try {
						this.list = await this.call(VETEDGE_BRANCH_ACCESS_API.page, {
							resource: this.resource,
							search: this.search || "",
							filters: JSON.stringify(this.pageFilters()),
							start: this.pageStart,
							page_length: this.pageLength,
						});
						this.pageStart = Number(this.list.start || 0);
						this.updateRoute();
					} catch (error) {
						this.error = this.message(error, __("Branch Access could not be loaded."));
					} finally {
						this.loading = false;
					}
				},
				async switchResource(resource) {
					if (!VETEDGE_BRANCH_ACCESS_RESOURCES[resource] || resource === this.resource) return;
					this.resource = resource;
					this.search = "";
					this.filters = { branch: "", disabled: "" };
					this.pageStart = 0;
					this.editor.open = false;
					await this.refresh();
				},
				async applyFilters() { this.pageStart = 0; await this.refresh(); },
				async resetFilters() { this.search = ""; this.filters = { branch: "", disabled: "" }; this.pageStart = 0; await this.refresh(); },
				async previousPage() { this.pageStart = Math.max(0, this.pageStart - this.pageLength); await this.refresh(); },
				async nextPage() { this.pageStart += this.pageLength; await this.refresh(); },
				async searchLink(field, query) {
					return (await this.call(VETEDGE_BRANCH_ACCESS_API.link, {
						resource: this.resource,
						fieldname: field?.fieldname || "",
						query: query || "",
						page_length: 20,
					})) || [];
				},
				async searchBranches(query) {
					return (await this.call(VETEDGE_BRANCH_ACCESS_API.link, { resource: this.resource, fieldname: "branch", query: query || "", page_length: 20 })) || [];
				},
				async openDocument(name = null, updateRoute = true) {
					this.editor = { open: true, loading: true, saving: false, error: "", document: null, model: {} };
					try {
						const doc = await this.call(VETEDGE_BRANCH_ACCESS_API.document, { resource: this.resource, name });
						this.editor.document = doc;
						this.editor.model = JSON.parse(JSON.stringify(doc?.values || {}));
						if (updateRoute) this.updateRoute(doc?.is_new ? { new: 1 } : { name: doc?.name || "" });
					} catch (error) {
						this.editor.error = this.message(error, __("Branch access assignment could not be opened."));
					} finally {
						this.editor.loading = false;
					}
				},
				openNew() { if (this.canCreate) this.openDocument(null); },
				openRow(row) { if (row?.name) this.openDocument(row.name); },
				closeEditor() { if (!this.editor.saving && !this.deleteBusy) { this.editor.open = false; this.confirmDeleteOpen = false; this.updateRoute(); } },
				async saveDocument() {
					if (!this.canEdit || this.editor.saving) return;
					this.editor.saving = true;
					this.editor.error = "";
					try {
						const doc = await this.call(VETEDGE_BRANCH_ACCESS_API.save, {
							resource: this.resource,
							name: this.editor.document?.is_new ? null : this.editor.document?.name,
							modified: this.editor.document?.modified || null,
							values: JSON.stringify(this.editor.model || {}),
						});
						this.editor.document = doc;
						this.editor.model = JSON.parse(JSON.stringify(doc?.values || {}));
						this.updateRoute({ name: doc?.name || "" });
						frappe.show_alert({ message: __("Branch access assignment saved"), indicator: "green" });
						await this.refresh();
					} catch (error) {
						this.editor.error = this.message(error, __("Branch access assignment could not be saved."));
					} finally {
						this.editor.saving = false;
					}
				},
				async deleteDocument() {
					if (!this.canDelete || this.deleteBusy) return;
					this.deleteBusy = true;
					try {
						await this.call(VETEDGE_BRANCH_ACCESS_API.remove, { resource: this.resource, name: this.editor.document?.name });
						this.editor.open = false;
						this.confirmDeleteOpen = false;
						this.updateRoute();
						frappe.show_alert({ message: __("Branch access assignment deleted"), indicator: "green" });
						await this.refresh();
					} catch (error) {
						this.editor.error = this.message(error, __("Branch access assignment could not be deleted."));
						this.confirmDeleteOpen = false;
					} finally {
						this.deleteBusy = false;
					}
				},
				renderFilters() {
					return h("div", { style: "display:grid;grid-template-columns:repeat(4,minmax(11rem,1fr));gap:12px;align-items:end;width:100%" }, [
						h(EdgeInput, { modelValue: this.search, type: "search", label: __("Search"), placeholder: __("User, practitioner or Branch"), "onUpdate:modelValue": (value) => { this.search = value || ""; }, onKeyup: (event) => { if (event.key === "Enter") this.applyFilters(); } }),
						h(EdgeLinkField, { modelValue: this.filters.branch, selectedLabel: this.filters.branch || "", label: __("Branch"), placeholder: __("All permitted Branches"), searcher: this.searchBranches, allowClear: true, "onUpdate:modelValue": (value) => { this.filters.branch = value || ""; } }),
						h(EdgeDropdown, { modelValue: this.filters.disabled, label: __("Status"), options: VETEDGE_BRANCH_ACCESS_DISABLED, "onUpdate:modelValue": (value) => { this.filters.disabled = value ?? ""; } }),
						h(EdgeDropdown, {
						modelValue: this.resource,
						label: __("Access Type"),
						options: Object.entries(VETEDGE_BRANCH_ACCESS_RESOURCES).map(([value, config]) => ({ value, label: config.title })),
						"onUpdate:modelValue": this.switchResource,
					}),
					]);
				},
				renderTable() {
					if (this.list.branch_scope_empty) return h(EdgeEmptyState, { title: __("No Branch access scope"), description: __("Your account has no Veterinary Branch assignment, so Branch access administration is hidden." ) });
					if (!this.list.rows?.length) return h(EdgeEmptyState, { title: __("No assignments found"), description: __("Change the filters or add a Branch access assignment."), actionLabel: this.canCreate ? __("Add Assignment") : "", onAction: this.openNew });
					return h("div", [
						h(EdgeDataTable, {
							columns: this.list.columns || [], rows: this.list.rows || [], rowKey: "name",
							actions: [{ key: "open", label: __("Open"), primary: true }],
							onRowClick: this.openRow,
							onAction: (payload) => { if (payload?.action?.key === "open") this.openRow(payload.row); },
						}),
						h("div", { style: "display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;margin-top:12px" }, [
							h("span", [__("Total records: "), h("strong", String(this.list.total || 0)), __(" · Page "), h("strong", `${this.currentPage} / ${this.totalPages}`)]),
							h("div", { style: "display:flex;gap:8px" }, [
								h("button", { class: "edge-button edge-button--compact", type: "button", disabled: !this.hasPrevious, onClick: this.previousPage }, __("Previous")),
								h("button", { class: "edge-button edge-button--compact", type: "button", disabled: !this.hasNext, onClick: this.nextPage }, __("Next")),
							]),
						]),
					]);
				},
				renderEditor() {
					const doc = this.editor.document;
					return h(EdgeModal, {
						open: this.editor.open,
						title: doc?.title || this.resourceConfig.singular,
						subtitle: this.list.subtitle || this.resourceConfig.title,
						size: "lg",
						busy: this.editor.loading || this.editor.saving,
						onClose: this.closeEditor,
					}, {
						default: () => this.editor.loading ? h(EdgeLoadingState, { message: __("Loading assignment...") }) : [
							this.editor.error ? h("div", { class: "alert alert-danger", role: "alert" }, this.editor.error) : null,
							doc?.schema ? h(EdgeDocumentForm, {
								schema: doc.schema,
								modelValue: this.editor.model,
								errors: {},
								readonly: !this.canEdit,
								linkSearcher: this.searchLink,
								"onUpdate:modelValue": (value) => { this.editor.model = value || {}; },
							}) : null,
						].filter(Boolean),
						footer: () => h("div", { style: "display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap" }, [
							this.canDelete ? h("button", { class: "edge-button edge-button--danger", type: "button", onClick: () => { this.confirmDeleteOpen = true; } }, __("Delete")) : null,
							h("button", { class: "edge-button", type: "button", disabled: this.editor.saving, onClick: this.closeEditor }, __("Close")),
							this.canEdit ? h("button", { class: "edge-button edge-button--primary", type: "button", disabled: this.editor.saving || this.editor.loading, onClick: this.saveDocument }, this.editor.saving ? __("Saving...") : __("Save")) : null,
						].filter(Boolean)),
					});
				},
				renderDeleteConfirmation() {
					return h(EdgeModal, { open: this.confirmDeleteOpen, title: __("Delete Branch access assignment"), busy: this.deleteBusy, onClose: () => { if (!this.deleteBusy) this.confirmDeleteOpen = false; } }, {
						default: () => h("p", __("Delete this Branch access assignment? This removes the access relationship but does not delete the User, Practitioner or Branch.")),
						footer: () => h("div", { style: "display:flex;gap:8px;justify-content:flex-end" }, [
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
					activeRoute: "/desk/vetedge-branch-access",
				}, {
					default: () => h(EdgePageLayout, {}, {
						header: () => h(EdgePageHeader, {
							eyebrow: this.resourceConfig.eyebrow,
							title: this.list.title || this.resourceConfig.title,
							subtitle: this.list.subtitle || __("Manage Veterinary Branch access without leaving the EdgeSuite workspace."),
							actionLabel: this.canCreate ? __("Add Assignment") : "",
							onAction: this.openNew,
						}),
						filters: () => h(EdgeFilterBar, { title: __("Branch Access Filters") }, {
							default: () => this.renderFilters(),
							actions: () => h("div", { style: "display:flex;gap:8px;flex-wrap:wrap" }, [
								h("button", { class: "edge-button edge-button--primary", type: "button", disabled: this.loading, onClick: this.applyFilters }, this.loading ? __("Loading...") : __("Apply")),
								h("button", { class: "edge-button", type: "button", disabled: this.loading, onClick: this.resetFilters }, __("Reset")),
							]),
						}),
						default: () => [
							this.error ? h(EdgeErrorState, { title: __("Branch Access could not load"), message: this.error, actionLabel: __("Try again"), onRetry: this.refresh })
								: this.loading ? h(EdgeLoadingState, { message: __("Loading Branch Access..."), skeleton: true }) : this.renderTable(),
							this.renderEditor(),
							this.renderDeleteConfirmation(),
						],
					}),
				});
			},
		};

		try {
			$loading.remove();
			const root = $("<div class='vetedge-branch-access-root' data-edge-product='vetedge'></div>").appendTo(page.body);
			wrapper.vue_app = runtime.createEdgeApp(component);
			wrapper.vue_app.mount(root[0]);
		} catch (error) {
			console.error("Error mounting VetEdge Branch Access:", error);
			fail(__("Error mounting Branch Access: {0}", [error.message || String(error)]));
		}
	});
};
