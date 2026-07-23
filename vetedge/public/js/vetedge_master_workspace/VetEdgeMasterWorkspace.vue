<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/app/vetedge-master-workspace"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Veterinary Setup"
					:title="pageTitle"
					:subtitle="pageSubtitle"
					:action-label="listMode && canCreate ? `Add ${definition.singular || 'Master'}` : ''"
					@action="openNewDocument"
				/>
			</template>

			<template #filters>
				<EdgeFilterBar v-if="listMode" title="Find master records">
					<div class="vetedge-master-filters">
						<label class="vetedge-master-filter vetedge-master-filter--resource">
							<span>Master Type</span>
							<select v-model="resource" class="form-control" @change="changeResource">
								<option v-for="option in resourceOptions" :key="option.value" :value="option.value">
									{{ option.label }}
								</option>
							</select>
						</label>
						<label class="vetedge-master-filter vetedge-master-filter--search">
							<span>Search</span>
							<input
								v-model.trim="search"
								type="search"
								class="form-control"
								placeholder="Search visible master records"
								@keyup.enter="applyFilters"
							/>
						</label>
						<template v-for="field in definition.filters || []" :key="field.fieldname">
							<label v-if="field.fieldtype === 'Select'" class="vetedge-master-filter">
								<span>{{ field.label }}</span>
								<select v-model="filters[field.fieldname]" class="form-control">
									<option value="">All</option>
									<option v-for="option in parseOptions(field.options)" :key="option.value" :value="option.value">
										{{ option.label }}
									</option>
								</select>
							</label>
							<label v-else-if="field.fieldtype === 'Check'" class="vetedge-master-filter">
								<span>{{ field.label }}</span>
								<select v-model="filters[field.fieldname]" class="form-control">
									<option value="">All</option>
									<option value="0">{{ field.fieldname === 'disabled' ? 'Active' : 'No' }}</option>
									<option value="1">{{ field.fieldname === 'disabled' ? 'Disabled' : 'Yes' }}</option>
								</select>
							</label>
							<EdgeLinkField
								v-else-if="field.fieldtype === 'Link'"
								:model-value="filters[field.fieldname] || ''"
								:label="field.label"
								:placeholder="`Filter by ${field.label}`"
								:searcher="(query) => linkSearch(field, query)"
								@update:model-value="(value) => setFilter(field.fieldname, value)"
							/>
							<label v-else class="vetedge-master-filter">
								<span>{{ field.label }}</span>
								<input v-model="filters[field.fieldname]" type="text" class="form-control" />
							</label>
						</template>
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="applyFilters">
							Apply
						</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetFilters">
							Reset
						</button>
					</template>
				</EdgeFilterBar>
			</template>

			<EdgeLoadingState v-if="loading" message="Loading Veterinary masters..." :skeleton="true" />
			<EdgeErrorState
				v-else-if="error"
				title="The Veterinary masters page could not load"
				:message="error"
				action-label="Try again"
				@retry="reloadCurrentView"
			/>

			<template v-else-if="listMode">
				<section class="vetedge-master-summary" aria-label="Master summary">
					<div>
						<span>Total records</span>
						<strong>{{ list.total || 0 }}</strong>
					</div>
					<div>
						<span>Current page</span>
						<strong>{{ currentPage }} of {{ totalPages }}</strong>
					</div>
					<div>
						<span>Master type</span>
						<strong>{{ definition.title || 'Veterinary Masters' }}</strong>
					</div>
				</section>

				<EdgeDataTable
					:columns="definition.columns || []"
					:rows="list.rows || []"
					:actions="rowActions"
					empty-title="No matching master records"
					empty-description="Change the filters or add a new Veterinary master record."
					@row-click="openRow"
					@action="handleRowAction"
				>
					<template #footer>
						<span class="vetedge-master-page-copy">
							Showing {{ firstVisible }}–{{ lastVisible }} of {{ list.total || 0 }}
						</span>
						<div class="vetedge-master-pagination">
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasPrevious" @click="previousPage">
								Previous
							</button>
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasNext" @click="nextPage">
								Next
							</button>
						</div>
					</template>
				</EdgeDataTable>
			</template>

			<template v-else-if="documentReady">
				<EdgeWorkflowBar
					:state="document.state || (document.is_new ? 'New' : 'Active')"
					:docstatus="document.docstatus || 0"
					:dirty="dirty"
					:saving="saving"
					:can-save="canSave"
					:can-delete="canDelete"
					:transitions="[]"
					@save="saveDocument"
					@delete="requestDelete"
					@back="backToList"
				/>

				<EdgeDocumentForm
					:schema="document.schema || { tabs: [] }"
					:model-value="model"
					:errors="fieldErrors"
					:readonly="!canEdit"
					:link-searcher="linkSearch"
					@update:model-value="onModelUpdate"
				/>
			</template>

			<EdgeEmptyState
				v-else
				title="Master record unavailable"
				description="Return to the list and choose another record."
				action-label="Back to list"
				@action="backToList"
			/>
		</EdgePageLayout>

		<EdgeModal
			:open="confirmation.open"
			:title="confirmation.title"
			:subtitle="confirmation.subtitle"
			:busy="confirmation.busy"
			@close="closeConfirmation"
		>
			<p class="vetedge-master-confirmation">{{ confirmation.message }}</p>
			<template #footer>
				<button type="button" class="edge-button" :disabled="confirmation.busy" @click="closeConfirmation">
					Cancel
				</button>
				<button
					type="button"
					:class="['edge-button', confirmation.danger ? 'edge-button--danger' : 'edge-button--primary']"
					:disabled="confirmation.busy"
					@click="confirmPendingAction"
				>
					{{ confirmation.busy ? 'Working…' : confirmation.confirmLabel }}
				</button>
			</template>
		</EdgeModal>
	</EdgeAppShell>
</template>

<script>
const API = Object.freeze({
	definition: "vetedge.services.master_workspace.get_master_definition",
	list: "vetedge.services.master_workspace.get_master_list",
	document: "vetedge.services.master_workspace.get_master_document",
	save: "vetedge.services.master_workspace.save_master_document",
	remove: "vetedge.services.master_workspace.delete_master_document",
	link: "vetedge.services.master_workspace.get_master_link_options",
});

const RESOURCE_OPTIONS = Object.freeze([
	{ value: "species", label: "Species" },
	{ value: "breeds", label: "Breeds" },
	{ value: "symptoms", label: "Symptoms" },
	{ value: "diagnosis-categories", label: "Diagnosis Categories" },
	{ value: "diagnoses", label: "Diagnoses" },
	{ value: "service-types", label: "Service Types" },
	{ value: "consultation-types", label: "Consultation Types" },
]);

function clone(value) {
	return JSON.parse(JSON.stringify(value ?? {}));
}

function errorMessage(error, fallback) {
	return (
		error?.message ||
		error?._server_messages ||
		error?.exc_type ||
		fallback ||
		__("The requested operation could not be completed.")
	);
}

export default {
	name: "VetEdgeMasterWorkspace",
	data() {
		const route = new URLSearchParams(window.location.search || "");
		const requested = route.get("resource") || "species";
		return {
			resource: RESOURCE_OPTIONS.some((option) => option.value === requested) ? requested : "species",
			resourceOptions: RESOURCE_OPTIONS,
			definition: {
				title: "Veterinary Masters",
				singular: "Master",
				subtitle: "Permission-safe Veterinary setup.",
				columns: [],
				filters: [],
				permissions: {},
			},
			list: { rows: [], total: 0, start: 0, page_length: 25 },
			document: {},
			model: {},
			originalModel: "{}",
			fieldErrors: {},
			search: route.get("search") || "",
			filters: {},
			pageLength: 25,
			loading: true,
			saving: false,
			error: "",
			dirty: false,
			mode: route.get("name") || route.get("new") === "1" ? "form" : "list",
			confirmation: {
				open: false,
				title: "Confirm action",
				subtitle: "",
				message: "",
				confirmLabel: "Continue",
				danger: false,
				busy: false,
				handler: null,
			},
		};
	},
	computed: {
		identity() {
			return frappe.boot?.edgesuite_ui_identity?.vetedge || frappe.boot?.vetedge_ui_identity || {};
		},
		branchName() {
			return (
				frappe.boot?.edgesuite_product_menu?.branch ||
				frappe.defaults?.get_user_default?.("branch") ||
				"All Branches"
			);
		},
		userName() {
			const user = frappe.session?.user || "";
			const info = frappe.boot?.user_info?.[user] || {};
			return info.fullname || info.full_name || user;
		},
		listMode() {
			return this.mode === "list";
		},
		documentReady() {
			return Boolean(this.document?.schema);
		},
		pageTitle() {
			if (this.listMode) return this.definition.title || "Veterinary Masters";
			if (this.document.is_new) return `Add ${this.definition.singular || "Master"}`;
			return this.document.title || this.document.name || this.definition.singular || "Veterinary Master";
		},
		pageSubtitle() {
			if (this.listMode) return this.definition.subtitle || "";
			return this.document.name
				? `${this.definition.singular || "Master"} · ${this.document.name}`
				: this.definition.subtitle || "";
		},
		canCreate() {
			return Boolean(this.definition.permissions?.create);
		},
		canEdit() {
			if (this.document.is_new) return Boolean(this.definition.permissions?.create);
			return Boolean(this.document.permissions?.write);
		},
		canSave() {
			return this.canEdit;
		},
		canDelete() {
			return Boolean(!this.document.is_new && this.document.permissions?.delete);
		},
		rowActions() {
			return [{ key: "open", label: "Open", primary: true }];
		},
		currentPage() {
			return Math.floor((this.list.start || 0) / (this.list.page_length || this.pageLength)) + 1;
		},
		totalPages() {
			return Math.max(1, Math.ceil((this.list.total || 0) / (this.list.page_length || this.pageLength)));
		},
		hasPrevious() {
			return (this.list.start || 0) > 0;
		},
		hasNext() {
			return (this.list.start || 0) + (this.list.rows?.length || 0) < (this.list.total || 0);
		},
		firstVisible() {
			return this.list.total ? (this.list.start || 0) + 1 : 0;
		},
		lastVisible() {
			return Math.min((this.list.start || 0) + (this.list.rows?.length || 0), this.list.total || 0);
		},
	},
	mounted() {
		window.addEventListener("popstate", this.handleBrowserNavigation);
		window.addEventListener("beforeunload", this.handleBeforeUnload);
		this.loadCurrentRoute();
	},
	beforeUnmount() {
		window.removeEventListener("popstate", this.handleBrowserNavigation);
		window.removeEventListener("beforeunload", this.handleBeforeUnload);
	},
	methods: {
		async call(method, args = {}) {
			const response = await frappe.call(method, args);
			return response?.message;
		},
		parseOptions(options) {
			return String(options || "")
				.split("\n")
				.map((value) => value.trim())
				.filter(Boolean)
				.map((value) => ({ value, label: value }));
		},
		handleBeforeUnload(event) {
			if (!this.dirty) return;
			event.preventDefault();
			event.returnValue = "";
		},
		confirmDiscard(action) {
			if (!this.dirty) {
				action();
				return;
			}
			this.openConfirmation({
				title: __("Discard unsaved changes?"),
				message: __("You have unsaved changes. Continue without saving them?"),
				confirmLabel: __("Discard Changes"),
				danger: true,
				handler: () => {
					this.dirty = false;
					this.closeConfirmation();
					action();
				},
			});
		},
		async loadCurrentRoute() {
			const route = new URLSearchParams(window.location.search || "");
			const requested = route.get("resource") || this.resource || "species";
			this.resource = RESOURCE_OPTIONS.some((option) => option.value === requested) ? requested : "species";
			this.search = route.get("search") || "";
			this.loading = true;
			this.error = "";
			try {
				await this.loadDefinition();
				const name = route.get("name");
				const isNew = route.get("new") === "1";
				if (name || isNew) {
					this.mode = "form";
					await this.loadDocument(name);
				} else {
					this.mode = "list";
					await this.loadList();
				}
			} catch (error) {
				this.error = errorMessage(error, __("The Veterinary masters page could not be loaded."));
			} finally {
				this.loading = false;
			}
		},
		async loadDefinition() {
			this.definition = await this.call(API.definition, { resource: this.resource });
		},
		async loadList() {
			this.list = await this.call(API.list, {
				resource: this.resource,
				search: this.search,
				filters: JSON.stringify(this.filters),
				start: this.list.start || 0,
				page_length: this.pageLength,
			});
			this.updateListLocation();
		},
		async loadDocument(name = null) {
			const payload = await this.call(API.document, { resource: this.resource, name });
			this.setDocument(payload);
		},
		setDocument(payload) {
			this.document = payload || {};
			this.model = clone(payload?.values || {});
			this.originalModel = JSON.stringify(this.model);
			this.fieldErrors = {};
			this.dirty = false;
		},
		onModelUpdate(next) {
			this.model = next;
			this.dirty = JSON.stringify(next) !== this.originalModel;
		},
		async linkSearch(field, query) {
			return (
				(await this.call(API.link, {
					resource: this.resource,
					fieldname: field.fieldname,
					query,
				})) || []
			);
		},
		setFilter(fieldname, value) {
			this.filters = { ...this.filters, [fieldname]: value || "" };
		},
		async applyFilters() {
			this.list.start = 0;
			await this.withLoading(this.loadList);
		},
		async resetFilters() {
			this.search = "";
			this.filters = {};
			this.list.start = 0;
			await this.withLoading(this.loadList);
		},
		async previousPage() {
			this.list.start = Math.max(0, (this.list.start || 0) - (this.list.page_length || this.pageLength));
			await this.withLoading(this.loadList);
		},
		async nextPage() {
			this.list.start = (this.list.start || 0) + (this.list.page_length || this.pageLength);
			await this.withLoading(this.loadList);
		},
		changeResource() {
			const nextResource = this.resource;
			this.confirmDiscard(async () => {
				this.resource = nextResource;
				this.filters = {};
				this.search = "";
				this.list = { rows: [], total: 0, start: 0, page_length: this.pageLength };
				this.pushLocation({ resource: this.resource });
				await this.loadCurrentRoute();
			});
		},
		openNewDocument() {
			if (!this.canCreate) return;
			this.confirmDiscard(() => {
				this.pushLocation({ resource: this.resource, new: "1" });
				this.loadCurrentRoute();
			});
		},
		openRow(row) {
			if (!row?.name) return;
			this.confirmDiscard(() => {
				this.pushLocation({ resource: this.resource, name: row.name });
				this.loadCurrentRoute();
			});
		},
		handleRowAction({ action, row }) {
			if (action.key === "open") this.openRow(row);
		},
		validateRequired() {
			const errors = {};
			for (const tab of this.document.schema?.tabs || []) {
				for (const section of tab.sections || []) {
					for (const field of section.fields || []) {
						if (field.reqd && [null, undefined, ""].includes(this.model[field.fieldname])) {
							errors[field.fieldname] = __("This field is required.");
						}
					}
				}
			}
			this.fieldErrors = errors;
			return Object.keys(errors).length === 0;
		},
		async saveDocument() {
			if (!this.canSave || this.saving || !this.validateRequired()) return;
			this.saving = true;
			try {
				const payload = await this.call(API.save, {
					resource: this.resource,
					name: this.document.is_new ? null : this.document.name,
					modified: this.document.modified || null,
					values: JSON.stringify(this.model),
				});
				this.setDocument(payload);
				if (payload?.name) this.replaceLocation({ resource: this.resource, name: payload.name });
				frappe.show_alert({ message: __("Master record saved"), indicator: "green" });
			} catch (error) {
				frappe.msgprint({
					title: __("Unable to save"),
					message: errorMessage(error, __("The master record could not be saved.")),
					indicator: "red",
				});
			} finally {
				this.saving = false;
			}
		},
		requestDelete() {
			if (!this.canDelete) return;
			this.openConfirmation({
				title: __("Delete master record"),
				message: __("Delete {0}? Linked records may prevent deletion. This cannot be undone.", [this.document.name]),
				confirmLabel: __("Delete"),
				danger: true,
				handler: this.deleteDocument,
			});
		},
		async deleteDocument() {
			await this.call(API.remove, { resource: this.resource, name: this.document.name });
			frappe.show_alert({ message: __("Master record deleted"), indicator: "green" });
			this.dirty = false;
			this.closeConfirmation();
			this.backToList();
		},
		backToList() {
			this.confirmDiscard(() => {
				this.pushLocation({ resource: this.resource });
				this.loadCurrentRoute();
			});
		},
		reloadCurrentView() {
			this.confirmDiscard(this.loadCurrentRoute);
		},
		handleBrowserNavigation() {
			if (this.dirty) {
				window.history.forward();
				this.confirmDiscard(() => window.history.back());
				return;
			}
			this.loadCurrentRoute();
		},
		openConfirmation({ title, subtitle = "", message, confirmLabel = __("Continue"), danger = false, handler }) {
			this.confirmation = { open: true, title, subtitle, message, confirmLabel, danger, busy: false, handler };
		},
		closeConfirmation() {
			if (this.confirmation.busy) return;
			this.confirmation = {
				open: false,
				title: "Confirm action",
				subtitle: "",
				message: "",
				confirmLabel: "Continue",
				danger: false,
				busy: false,
				handler: null,
			};
		},
		async confirmPendingAction() {
			if (typeof this.confirmation.handler !== "function") return;
			this.confirmation.busy = true;
			try {
				await this.confirmation.handler();
			} catch (error) {
				frappe.msgprint({ title: __("Action failed"), message: errorMessage(error), indicator: "red" });
			} finally {
				this.confirmation.busy = false;
			}
		},
		withLoading(handler) {
			this.loading = true;
			this.error = "";
			return Promise.resolve()
				.then(() => handler.call(this))
				.catch((error) => {
					this.error = errorMessage(error);
				})
				.finally(() => {
					this.loading = false;
				});
		},
		pushLocation(params) {
			const url = new URL(window.location.href);
			url.pathname = "/app/vetedge-master-workspace";
			url.search = new URLSearchParams(params).toString();
			window.history.pushState({}, "", url);
		},
		replaceLocation(params) {
			const url = new URL(window.location.href);
			url.pathname = "/app/vetedge-master-workspace";
			url.search = new URLSearchParams(params).toString();
			window.history.replaceState({}, "", url);
		},
		updateListLocation() {
			const params = { resource: this.resource };
			if (this.search) params.search = this.search;
			this.replaceLocation(params);
		},
		openRoute(route) {
			if (!route) return;
			const adapter = (window.EdgeSuiteUI || window.EdgeUI)?.getAdapter?.("navigation:vetedge");
			if (adapter?.open?.(route) === true) return;
			window.location.assign(route);
		},
	},
};
</script>

<style scoped>
.vetedge-master-filters {
	display: grid;
	gap: 0.75rem;
	grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
	width: 100%;
}

.vetedge-master-filter {
	display: grid;
	gap: 0.3rem;
}

.vetedge-master-filter > span {
	color: var(--edge-color-ink-600, #526579);
	font-size: 0.72rem;
	font-weight: 600;
}

.vetedge-master-filter--resource,
.vetedge-master-filter--search {
	min-width: 14rem;
}

.vetedge-master-summary {
	display: grid;
	gap: 0.75rem;
	grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
	margin-bottom: 1rem;
}

.vetedge-master-summary > div {
	background: var(--edge-color-surface, #fff);
	border: 1px solid var(--edge-color-border, #dce5ef);
	border-radius: 0.85rem;
	display: grid;
	gap: 0.2rem;
	padding: 0.85rem 1rem;
}

.vetedge-master-summary span,
.vetedge-master-page-copy {
	color: var(--edge-color-ink-500, #6b7d90);
	font-size: 0.72rem;
}

.vetedge-master-summary strong {
	color: var(--edge-color-ink-900, #1c2b3b);
	font-size: 1rem;
}

.vetedge-master-pagination {
	display: flex;
	gap: 0.5rem;
}

.vetedge-master-confirmation {
	color: var(--edge-color-ink-700, #40546a);
	line-height: 1.55;
	margin: 0;
}
</style>
