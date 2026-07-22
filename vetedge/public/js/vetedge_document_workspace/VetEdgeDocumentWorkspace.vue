<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/app/vetedge-document-workspace"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Veterinary Operations"
					:title="pageTitle"
					:subtitle="pageSubtitle"
					:action-label="listMode && canCreate ? `Add ${definition.singular || 'Record'}` : ''"
					@action="openNewDocument"
				/>
			</template>

			<template #filters>
				<EdgeFilterBar v-if="listMode" title="Find records">
					<div class="vetedge-document-filters">
						<label class="vetedge-document-filter vetedge-document-filter--resource">
							<span>Resource</span>
							<select v-model="resource" class="form-control" @change="changeResource">
								<option v-for="option in resourceOptions" :key="option.value" :value="option.value">
									{{ option.label }}
								</option>
							</select>
						</label>
						<label class="vetedge-document-filter vetedge-document-filter--search">
							<span>Search</span>
							<input
								v-model.trim="search"
								type="search"
								class="form-control"
								placeholder="Search visible records"
								@keyup.enter="applyFilters"
							/>
						</label>
						<template v-for="field in definition.filters || []" :key="field.fieldname">
							<label v-if="field.fieldtype === 'Select'" class="vetedge-document-filter">
								<span>{{ field.label }}</span>
								<select v-model="filters[field.fieldname]" class="form-control">
									<option value="">All</option>
									<option v-for="option in parseOptions(field.options)" :key="option.value" :value="option.value">
										{{ option.label }}
									</option>
								</select>
							</label>
							<EdgeLinkField
								v-else-if="field.fieldtype === 'Link'"
								:model-value="filters[field.fieldname] || ''"
								:label="field.label"
								:placeholder="`Filter by ${field.label}`"
								:searcher="(query) => filterLinkSearch(field, query)"
								@update:model-value="(value) => setFilter(field.fieldname, value)"
							/>
							<label v-else class="vetedge-document-filter">
								<span>{{ field.label }}</span>
								<input
									v-model="filters[field.fieldname]"
									:type="filterInputType(field)"
									class="form-control"
								/>
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

			<EdgeLoadingState v-if="loading" message="Loading Veterinary records..." :skeleton="true" />
			<EdgeErrorState
				v-else-if="error"
				title="The Veterinary page could not load"
				:message="error"
				action-label="Try again"
				@retry="reloadCurrentView"
			/>

			<template v-else-if="listMode">
				<section class="vetedge-document-summary" aria-label="Document summary">
					<div>
						<span>Total records</span>
						<strong>{{ list.total || 0 }}</strong>
					</div>
					<div>
						<span>Current page</span>
						<strong>{{ currentPage }} of {{ totalPages }}</strong>
					</div>
					<div>
						<span>Working branch</span>
						<strong>{{ branchName }}</strong>
					</div>
				</section>

				<EdgeDataTable
					:columns="definition.columns || []"
					:rows="list.rows || []"
					:actions="rowActions"
					empty-title="No matching records"
					empty-description="Change the filters or add a new Veterinary record."
					@row-click="openRow"
					@action="handleRowAction"
				>
					<template #footer>
						<span class="vetedge-document-page-copy">
							Showing {{ firstVisible }}–{{ lastVisible }} of {{ list.total || 0 }}
						</span>
						<div class="vetedge-document-pagination">
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
					:state="document.state || (document.is_new ? 'New' : 'Draft')"
					:docstatus="document.docstatus || 0"
					:dirty="dirty"
					:saving="saving"
					:can-save="canSave"
					:can-delete="canDelete"
					:transitions="availableActions"
					:save-label="definition.is_single ? 'Save Settings' : 'Save'"
					@save="saveDocument"
					@delete="requestDelete"
					@transition="handleTransition"
					@back="backToList"
				/>

				<EdgeSettingsLayout
					v-if="definition.is_single"
					:groups="settingsGroups"
					:active="settingsGroup"
					title="Veterinary Settings"
					description="Configure clinic-wide controls using the grouped EdgeSuite settings experience."
					@update:active="settingsGroup = $event"
				>
					<EdgeDocumentForm
						:schema="settingsVisibleSchema"
						:model-value="model"
						:errors="fieldErrors"
						:readonly="!canEdit"
						:link-searcher="linkSearch"
						:child-link-searcher="childLinkSearch"
						@update:model-value="onModelUpdate"
					/>
				</EdgeSettingsLayout>

				<EdgeDocumentForm
					v-else
					:schema="document.schema || { tabs: [] }"
					:model-value="model"
					:errors="fieldErrors"
					:readonly="!canEdit"
					:link-searcher="linkSearch"
					:child-link-searcher="childLinkSearch"
					@update:model-value="onModelUpdate"
				/>
			</template>

			<EdgeEmptyState
				v-else
				title="Document unavailable"
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
			<p class="vetedge-document-confirmation">{{ confirmation.message }}</p>
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
	definition: "vetedge.services.document_workspace.get_resource_definition",
	list: "vetedge.services.document_workspace.get_document_list",
	document: "vetedge.services.document_workspace.get_document",
	save: "vetedge.services.document_workspace.save_document",
	remove: "vetedge.services.document_workspace.delete_document",
	link: "vetedge.services.document_workspace.get_link_options",
	workflow: "vetedge.services.document_workspace.apply_workflow_transition",
	action: "vetedge.services.document_workspace.perform_document_action",
});

const RESOURCE_OPTIONS = Object.freeze([
	{ value: "patients", label: "Patients" },
	{ value: "appointments", label: "Appointments" },
	{ value: "settings", label: "Veterinary Settings" },
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
	name: "VetEdgeDocumentWorkspace",
	data() {
		const route = new URLSearchParams(window.location.search || "");
		const requested = route.get("resource") || "patients";
		return {
			resource: RESOURCE_OPTIONS.some((option) => option.value === requested) ? requested : "patients",
			resourceOptions: RESOURCE_OPTIONS,
			definition: {
				title: "Veterinary Documents",
				singular: "Record",
				subtitle: "Permission-safe Veterinary operations.",
				columns: [],
				filters: [],
				permissions: {},
				is_single: false,
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
			mode: route.get("name") || route.get("new") === "1" || requested === "settings" ? "form" : "list",
			settingsGroup: "",
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
			return this.mode === "list" && !this.definition.is_single;
		},
		documentReady() {
			return Boolean(this.document?.schema);
		},
		pageTitle() {
			if (this.listMode) return this.definition.title || "Veterinary Documents";
			if (this.definition.is_single) return "Veterinary Settings";
			if (this.document.is_new) return `Add ${this.definition.singular || "Record"}`;
			return this.document.title || this.document.name || this.definition.singular || "Veterinary Record";
		},
		pageSubtitle() {
			if (this.listMode || this.definition.is_single) return this.definition.subtitle || "";
			return this.document.name ? `${this.definition.singular || "Record"} · ${this.document.name}` : this.definition.subtitle || "";
		},
		canCreate() {
			return Boolean(this.definition.permissions?.create);
		},
		canEdit() {
			if (this.document.is_new) return Boolean(this.definition.permissions?.create);
			if (this.definition.is_single) return Boolean(this.document.permissions?.write);
			return Boolean(this.document.permissions?.write && Number(this.document.docstatus || 0) === 0);
		},
		canSave() {
			return this.canEdit;
		},
		canDelete() {
			return Boolean(
				!this.definition.is_single &&
				!this.document.is_new &&
				this.document.permissions?.delete &&
				Number(this.document.docstatus || 0) === 0
			);
		},
		rowActions() {
			return [{ key: "open", label: "Open", primary: true }];
		},
		availableActions() {
			const workflow = (this.document.workflow_transitions || []).map((transition) => ({
				...transition,
				source: "workflow",
			}));
			const custom = (this.document.actions || []).map((action) => ({
				...action,
				source: "custom",
			}));
			return [...workflow, ...custom];
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
		settingsGroups() {
			return (this.document.schema?.tabs || []).map((tab) => ({
				key: tab.key,
				label: tab.label,
				description: tab.description || `${tab.sections?.length || 0} settings groups`,
				icon: this.settingsIcon(tab.key),
			}));
		},
		settingsVisibleSchema() {
			const tabs = this.document.schema?.tabs || [];
			const selected = tabs.find((tab) => tab.key === this.settingsGroup) || tabs[0];
			return { tabs: selected ? [selected] : [] };
		},
	},
	mounted() {
		window.addEventListener("popstate", this.handleBrowserNavigation);
		this.loadCurrentRoute();
	},
	beforeUnmount() {
		window.removeEventListener("popstate", this.handleBrowserNavigation);
	},
	methods: {
		async call(method, args = {}) {
			const response = await frappe.call(method, args);
			return response?.message;
		},
		parseOptions(options) {
			if (Array.isArray(options)) {
				return options.map((option) =>
					typeof option === "object"
						? { value: String(option.value ?? option.name ?? ""), label: String(option.label ?? option.title ?? option.value ?? option.name ?? "") }
						: { value: String(option), label: String(option) }
				);
			}
			return String(options || "")
				.split("\n")
				.map((value) => value.trim())
				.filter(Boolean)
				.map((value) => ({ value, label: value }));
		},
		filterInputType(field) {
			return { Date: "date", Datetime: "datetime-local", Int: "number", Float: "number", Currency: "number" }[field.fieldtype] || "text";
		},
		settingsIcon(key) {
			return {
				general_tab: "settings",
				clinical_tab: "activity",
				operations_tab: "clipboard",
				client_experience_tab: "user",
				portal_branding_tab: "palette",
				notifications_tab: "bell",
				admin_controls_tab: "shield",
			}[key] || "settings";
		},
		async loadCurrentRoute() {
			const route = new URLSearchParams(window.location.search || "");
			const requested = route.get("resource") || this.resource || "patients";
			this.resource = RESOURCE_OPTIONS.some((option) => option.value === requested) ? requested : "patients";
			this.search = route.get("search") || "";
			this.loading = true;
			this.error = "";
			try {
				await this.loadDefinition();
				if (this.definition.is_single) {
					this.mode = "form";
					await this.loadDocument();
					return;
				}
				const name = route.get("name");
				const isNew = route.get("new") === "1";
				if (name || isNew) {
					this.mode = "form";
					const defaults = {};
					for (const [key, value] of route.entries()) {
						if (!["resource", "name", "new", "search"].includes(key)) defaults[key] = value;
					}
					await this.loadDocument(name, defaults);
				} else {
					this.mode = "list";
					await this.loadList();
				}
			} catch (error) {
				this.error = errorMessage(error, __("The Veterinary page could not be loaded."));
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
		async loadDocument(name = null, defaults = {}) {
			const payload = await this.call(API.document, {
				resource: this.resource,
				name,
				defaults: JSON.stringify(defaults || {}),
			});
			this.setDocument(payload);
		},
		setDocument(payload) {
			this.document = payload || {};
			this.model = this.normalizeDocumentValues(payload?.schema || {}, payload?.values || {});
			this.originalModel = JSON.stringify(this.model);
			this.fieldErrors = {};
			this.dirty = false;
			if (this.definition.is_single) {
				this.settingsGroup = payload?.schema?.tabs?.[0]?.key || "";
			}
		},
		normalizeDocumentValues(schema, values) {
			const next = clone(values);
			for (const tab of schema.tabs || []) {
				for (const section of tab.sections || []) {
					for (const field of section.fields || []) {
						const value = next[field.fieldname];
						if (field.fieldtype === "Datetime" && typeof value === "string") {
							next[field.fieldname] = value.replace(" ", "T").slice(0, 16);
						}
						if (field.fieldtype === "Table" && Array.isArray(value)) {
							next[field.fieldname] = value.map((row) => {
								const normalized = { ...row };
								for (const child of field.child_fields || []) {
									if (child.fieldtype === "Datetime" && typeof normalized[child.fieldname] === "string") {
										normalized[child.fieldname] = normalized[child.fieldname].replace(" ", "T").slice(0, 16);
									}
								}
								return normalized;
							});
						}
					}
				}
			}
			return next;
		},
		onModelUpdate(next) {
			this.model = next;
			this.dirty = JSON.stringify(next) !== this.originalModel;
		},
		async linkSearch(field, query, values = {}) {
			return (await this.call(API.link, {
				resource: this.resource,
				fieldname: field.fieldname,
				query,
				values: JSON.stringify(values || this.model || {}),
			})) || [];
		},
		async childLinkSearch(field, query) {
			if (!field?.options) return [];
			const response = await frappe.call("frappe.desk.search.search_link", {
				doctype: field.options,
				txt: query || "",
				filters: {},
				page_length: 20,
			});
			return (response?.message || []).map((option) => ({
				value: option.value || option.name,
				label: option.label || option.value || option.name,
				description: option.description || "",
			}));
		},
		filterLinkSearch(field, query) {
			return this.linkSearch(field, query, this.filters);
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
		async changeResource() {
			this.filters = {};
			this.search = "";
			this.list = { rows: [], total: 0, start: 0, page_length: this.pageLength };
			this.pushLocation({ resource: this.resource });
			await this.loadCurrentRoute();
		},
		openNewDocument() {
			if (!this.canCreate) return;
			this.pushLocation({ resource: this.resource, new: "1" });
			this.loadCurrentRoute();
		},
		openRow(row) {
			if (!row?.name) return;
			this.pushLocation({ resource: this.resource, name: row.name });
			this.loadCurrentRoute();
		},
		handleRowAction({ action, row }) {
			if (action.key === "open") this.openRow(row);
		},
		async saveDocument() {
			if (!this.canSave || this.saving) return;
			this.saving = true;
			this.fieldErrors = {};
			try {
				const payload = await this.call(API.save, {
					resource: this.resource,
					name: this.document.is_new || this.definition.is_single ? null : this.document.name,
					modified: this.document.modified || null,
					values: JSON.stringify(this.model),
				});
				this.setDocument(payload);
				if (!this.definition.is_single && payload?.name) {
					this.replaceLocation({ resource: this.resource, name: payload.name });
				}
				frappe.show_alert({ message: this.definition.is_single ? __("Settings saved") : __("Document saved"), indicator: "green" });
			} catch (error) {
				frappe.msgprint({
					title: __("Unable to save"),
					message: errorMessage(error, __("The document could not be saved.")),
					indicator: "red",
				});
			} finally {
				this.saving = false;
			}
		},
		requestDelete() {
			if (!this.canDelete) return;
			this.openConfirmation({
				title: __("Delete document"),
				message: __("Delete {0}? This cannot be undone.", [this.document.name]),
				confirmLabel: __("Delete"),
				danger: true,
				handler: this.deleteDocument,
			});
		},
		async deleteDocument() {
			await this.call(API.remove, { resource: this.resource, name: this.document.name });
			frappe.show_alert({ message: __("Document deleted"), indicator: "green" });
			this.closeConfirmation();
			this.backToList();
		},
		handleTransition(action) {
			if (!action) return;
			if (action.source === "workflow") {
				this.openConfirmation({
					title: action.label || action.action,
					message: __("Apply workflow action {0}?", [action.label || action.action]),
					confirmLabel: action.label || action.action,
					danger: Boolean(action.danger),
					handler: () => this.applyWorkflow(action),
				});
				return;
			}
			if (action.kind === "navigate") {
				this.openRoute(action.route);
				return;
			}
			if (action.confirm) {
				this.openConfirmation({
					title: action.label,
					message: action.confirm,
					confirmLabel: action.label,
					danger: Boolean(action.danger),
					handler: () => this.performCustomAction(action),
				});
				return;
			}
			this.performCustomAction(action);
		},
		async applyWorkflow(action) {
			const payload = await this.call(API.workflow, {
				resource: this.resource,
				name: this.document.name,
				action: action.action,
			});
			this.setDocument(payload);
			this.closeConfirmation();
			frappe.show_alert({ message: __("Workflow updated"), indicator: "green" });
		},
		async performCustomAction(action) {
			this.saving = true;
			try {
				const payload = await this.call(API.action, {
					resource: this.resource,
					name: this.document.name,
					action: JSON.stringify(action),
				});
				if (payload?.document) this.setDocument(payload.document);
				this.closeConfirmation();
				if (payload?.route) this.openRoute(payload.route);
				else frappe.show_alert({ message: __("Action completed"), indicator: "green" });
			} catch (error) {
				frappe.msgprint({ title: __("Action failed"), message: errorMessage(error), indicator: "red" });
			} finally {
				this.saving = false;
			}
		},
		openConfirmation({ title, subtitle = "", message, confirmLabel = __("Continue"), danger = false, handler }) {
			this.confirmation = { open: true, title, subtitle, message, confirmLabel, danger, busy: false, handler };
		},
		closeConfirmation() {
			if (this.confirmation.busy) return;
			this.confirmation = { open: false, title: "", subtitle: "", message: "", confirmLabel: __("Continue"), danger: false, busy: false, handler: null };
		},
		async confirmPendingAction() {
			if (!this.confirmation.handler || this.confirmation.busy) return;
			this.confirmation.busy = true;
			try {
				await this.confirmation.handler();
			} catch (error) {
				this.confirmation.busy = false;
				frappe.msgprint({ title: __("Action failed"), message: errorMessage(error), indicator: "red" });
			}
		},
		backToList() {
			if (this.definition.is_single) {
				this.openRoute("/app/vetedge");
				return;
			}
			this.pushLocation({ resource: this.resource });
			this.loadCurrentRoute();
		},
		openRoute(route) {
			if (!route) return;
			const adapter = (window.EdgeSuiteUI || window.EdgeUI)?.getAdapter?.("navigation:vetedge");
			if (adapter?.open?.(route) === true) return;
			window.location.assign(route);
		},
		updateListLocation() {
			const params = { resource: this.resource };
			if (this.search) params.search = this.search;
			this.replaceLocation(params);
		},
		pushLocation(values) {
			const query = new URLSearchParams();
			Object.entries(values || {}).forEach(([key, value]) => {
				if (value !== null && value !== undefined && value !== "") query.set(key, value);
			});
			window.history.pushState({}, "", `${window.location.pathname}?${query.toString()}`);
		},
		replaceLocation(values) {
			const query = new URLSearchParams();
			Object.entries(values || {}).forEach(([key, value]) => {
				if (value !== null && value !== undefined && value !== "") query.set(key, value);
			});
			window.history.replaceState({}, "", `${window.location.pathname}?${query.toString()}`);
		},
		handleBrowserNavigation() {
			this.loadCurrentRoute();
		},
		async reloadCurrentView() {
			await this.loadCurrentRoute();
		},
		async withLoading(operation) {
			this.loading = true;
			this.error = "";
			try {
				await operation.call(this);
			} catch (error) {
				this.error = errorMessage(error);
			} finally {
				this.loading = false;
			}
		},
	},
};
</script>

<style scoped>
.vetedge-document-filters {
	display: grid;
	gap: var(--edge-card-gap, .75rem);
	grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
	width: 100%;
}

.vetedge-document-filter {
	display: grid;
	gap: .35rem;
	min-width: 0;
}

.vetedge-document-filter > span {
	color: var(--edge-color-ink-700, #415469);
	font-size: .72rem;
	font-weight: 700;
}

.vetedge-document-filter--search {
	grid-column: span 2;
}

.vetedge-document-summary {
	background: var(--edge-color-surface, #fff);
	border: 1px solid var(--edge-color-border, #dce5ef);
	border-radius: var(--edge-radius-lg, 1rem);
	display: grid;
	gap: .75rem;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	margin-bottom: var(--edge-section-gap, 1rem);
	padding: .75rem;
}

.vetedge-document-summary > div {
	background: var(--edge-color-surface-soft, #f8fafc);
	border: 1px solid var(--edge-color-border, #dce5ef);
	border-radius: .75rem;
	display: grid;
	gap: .25rem;
	padding: .7rem .8rem;
}

.vetedge-document-summary span,
.vetedge-document-page-copy {
	color: var(--edge-color-ink-500, #6b7d90);
	font-size: .7rem;
}

.vetedge-document-summary strong {
	color: var(--edge-color-ink-950, #122033);
	font-size: .95rem;
}

.vetedge-document-pagination {
	display: flex;
	gap: .45rem;
}

.vetedge-document-confirmation {
	color: var(--edge-color-ink-700, #415469);
	font-size: .82rem;
	line-height: 1.55;
	margin: 0;
}

@media (max-width: 47.99rem) {
	.vetedge-document-filter--search {
		grid-column: auto;
	}

	.vetedge-document-summary {
		grid-template-columns: minmax(0, 1fr);
	}
}
</style>
