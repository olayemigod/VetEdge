<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/app/vetedge-pricing-master-workspace"
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
				<EdgeFilterBar v-if="listMode" title="Find pricing and service masters">
					<div class="vetedge-pricing-filters">
						<label class="vetedge-pricing-filter vetedge-pricing-filter--resource">
							<span>Master Type</span>
							<select v-model="resource" class="form-control" @change="changeResource">
								<option v-for="option in resourceOptions" :key="option.value" :value="option.value">
									{{ option.label }}
								</option>
							</select>
						</label>
						<label class="vetedge-pricing-filter vetedge-pricing-filter--search">
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
							<label v-if="field.fieldtype === 'Select'" class="vetedge-pricing-filter">
								<span>{{ field.label }}</span>
								<select v-model="filters[field.fieldname]" class="form-control">
									<option value="">All</option>
									<option v-for="option in parseOptions(field.options)" :key="option.value" :value="option.value">
										{{ option.label }}
									</option>
								</select>
							</label>
							<label v-else-if="field.fieldtype === 'Check'" class="vetedge-pricing-filter">
								<span>{{ field.label }}</span>
								<select v-model="filters[field.fieldname]" class="form-control">
									<option value="">All</option>
									<option value="1">{{ field.fieldname === 'is_active' ? 'Active' : 'Yes' }}</option>
									<option value="0">{{ field.fieldname === 'disabled' ? 'Active' : field.fieldname === 'is_active' ? 'Inactive' : 'No' }}</option>
									<option v-if="field.fieldname === 'disabled'" value="1">Disabled</option>
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
							<label v-else class="vetedge-pricing-filter">
								<span>{{ field.label }}</span>
								<input v-model="filters[field.fieldname]" type="text" class="form-control" />
							</label>
						</template>
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="applyFilters">
							Apply
						</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetFilters">Reset</button>
					</template>
				</EdgeFilterBar>
			</template>

			<EdgeLoadingState v-if="loading" message="Loading pricing and service masters..." :skeleton="true" />
			<EdgeErrorState
				v-else-if="error"
				title="The pricing masters page could not load"
				:message="error"
				action-label="Try again"
				@retry="reloadCurrentView"
			/>

			<template v-else-if="listMode">
				<section v-if="definition.notice" class="vetedge-pricing-notice" aria-label="Pricing safety note">
					<strong>Before you save</strong>
					<p>{{ definition.notice }}</p>
				</section>
				<section class="vetedge-pricing-summary" aria-label="Pricing master summary">
					<div><span>Total records</span><strong>{{ list.total || 0 }}</strong></div>
					<div><span>Current page</span><strong>{{ currentPage }} of {{ totalPages }}</strong></div>
					<div><span>Master type</span><strong>{{ definition.title || 'Pricing Masters' }}</strong></div>
				</section>
				<EdgeDataTable
					:columns="definition.columns || []"
					:rows="list.rows || []"
					:actions="rowActions"
					empty-title="No matching records"
					empty-description="Change the filters or add a new pricing or service master."
					@row-click="openRow"
					@action="handleRowAction"
				>
					<template #footer>
						<span>Showing {{ firstVisible }}–{{ lastVisible }} of {{ list.total || 0 }}</span>
						<div class="vetedge-pricing-pagination">
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasPrevious" @click="previousPage">Previous</button>
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasNext" @click="nextPage">Next</button>
						</div>
					</template>
				</EdgeDataTable>
			</template>

			<template v-else-if="documentReady">
				<section v-if="document.notice" class="vetedge-pricing-notice" aria-label="Save side effects">
					<strong>Save behaviour</strong>
					<p>{{ document.notice }}</p>
				</section>
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
				title="Pricing master unavailable"
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
			<p>{{ confirmation.message }}</p>
			<template #footer>
				<button type="button" class="edge-button" :disabled="confirmation.busy" @click="closeConfirmation">Cancel</button>
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
	definition: "vetedge.services.pricing_master_workspace.get_pricing_master_definition",
	list: "vetedge.services.pricing_master_workspace.get_pricing_master_list",
	document: "vetedge.services.pricing_master_workspace.get_pricing_master_document",
	save: "vetedge.services.pricing_master_workspace.save_pricing_master_document",
	remove: "vetedge.services.pricing_master_workspace.delete_pricing_master_document",
	link: "vetedge.services.pricing_master_workspace.get_pricing_master_link_options",
});

const RESOURCE_OPTIONS = Object.freeze([
	{ value: "treatment-items", label: "Treatment Items" },
	{ value: "treatment-types", label: "Treatment Types" },
	{ value: "lab-tests", label: "Lab Tests" },
	{ value: "vaccines", label: "Vaccines" },
	{ value: "grooming-services", label: "Grooming Services" },
]);

function clone(value) {
	return JSON.parse(JSON.stringify(value ?? {}));
}

function errorMessage(error, fallback) {
	return error?.message || error?._server_messages || error?.exc_type || fallback || __("The operation could not be completed.");
}

export default {
	name: "VetEdgePricingMasterWorkspace",
	data() {
		const route = new URLSearchParams(window.location.search || "");
		const requested = route.get("resource") || "treatment-items";
		return {
			resource: RESOURCE_OPTIONS.some((option) => option.value === requested) ? requested : "treatment-items",
			resourceOptions: RESOURCE_OPTIONS,
			definition: { title: "Pricing Masters", singular: "Master", subtitle: "", columns: [], filters: [], permissions: {} },
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
			confirmation: { open: false, title: "Confirm action", subtitle: "", message: "", confirmLabel: "Continue", danger: false, busy: false, handler: null },
		};
	},
	computed: {
		identity() {
			return frappe.boot?.edgesuite_ui_identity?.vetedge || frappe.boot?.vetedge_ui_identity || {};
		},
		branchName() {
			return frappe.boot?.edgesuite_product_menu?.branch || frappe.defaults?.get_user_default?.("branch") || "All Branches";
		},
		userName() {
			const user = frappe.session?.user || "";
			const info = frappe.boot?.user_info?.[user] || {};
			return info.fullname || info.full_name || user;
		},
		listMode() { return this.mode === "list"; },
		documentReady() { return Boolean(this.document?.schema); },
		pageTitle() {
			if (this.listMode) return this.definition.title || "Pricing Masters";
			if (this.document.is_new) return `Add ${this.definition.singular || "Master"}`;
			return this.document.title || this.document.name || this.definition.singular || "Pricing Master";
		},
		pageSubtitle() {
			if (this.listMode) return this.definition.subtitle || "";
			return this.document.name ? `${this.definition.singular || "Master"} · ${this.document.name}` : this.definition.subtitle || "";
		},
		canCreate() { return Boolean(this.definition.permissions?.create); },
		canEdit() { return this.document.is_new ? Boolean(this.definition.permissions?.create) : Boolean(this.document.permissions?.write); },
		canSave() { return this.canEdit; },
		canDelete() { return Boolean(!this.document.is_new && this.document.permissions?.delete); },
		rowActions() { return [{ key: "open", label: "Open", primary: true }]; },
		currentPage() { return Math.floor((this.list.start || 0) / (this.list.page_length || this.pageLength)) + 1; },
		totalPages() { return Math.max(1, Math.ceil((this.list.total || 0) / (this.list.page_length || this.pageLength))); },
		hasPrevious() { return (this.list.start || 0) > 0; },
		hasNext() { return (this.list.start || 0) + (this.list.rows?.length || 0) < (this.list.total || 0); },
		firstVisible() { return this.list.total ? (this.list.start || 0) + 1 : 0; },
		lastVisible() { return Math.min((this.list.start || 0) + (this.list.rows?.length || 0), this.list.total || 0); },
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
			return String(options || "").split("\n").map((value) => value.trim()).filter(Boolean).map((value) => ({ value, label: value }));
		},
		handleBeforeUnload(event) {
			if (!this.dirty) return;
			event.preventDefault();
			event.returnValue = "";
		},
		confirmDiscard(action) {
			if (!this.dirty) return action();
			this.openConfirmation({
				title: __("Discard unsaved changes?"),
				message: __("You have unsaved changes. Continue without saving them?"),
				confirmLabel: __("Discard Changes"),
				danger: true,
				handler: () => { this.dirty = false; this.closeConfirmation(true); action(); },
			});
		},
		async loadCurrentRoute() {
			const route = new URLSearchParams(window.location.search || "");
			const requested = route.get("resource") || this.resource || "treatment-items";
			this.resource = RESOURCE_OPTIONS.some((option) => option.value === requested) ? requested : "treatment-items";
			this.search = route.get("search") || "";
			this.loading = true;
			this.error = "";
			try {
				this.definition = await this.call(API.definition, { resource: this.resource });
				const name = route.get("name");
				if (name || route.get("new") === "1") {
					this.mode = "form";
					this.setDocument(await this.call(API.document, { resource: this.resource, name }));
				} else {
					this.mode = "list";
					await this.loadList();
				}
			} catch (error) {
				this.error = errorMessage(error, __("The pricing masters page could not be loaded."));
			} finally {
				this.loading = false;
			}
		},
		async loadList() {
			this.list = await this.call(API.list, { resource: this.resource, search: this.search, filters: JSON.stringify(this.filters), start: this.list.start || 0, page_length: this.pageLength });
			this.updateListLocation();
		},
		setDocument(payload) {
			this.document = payload || {};
			this.model = clone(payload?.values || {});
			this.originalModel = JSON.stringify(this.model);
			this.fieldErrors = {};
			this.dirty = false;
		},
		onModelUpdate(next) { this.model = next; this.dirty = JSON.stringify(next) !== this.originalModel; },
		async linkSearch(field, query) {
			return (await this.call(API.link, { resource: this.resource, fieldname: field.fieldname, query })) || [];
		},
		setFilter(fieldname, value) { this.filters = { ...this.filters, [fieldname]: value || "" }; },
		async withLoading(handler) {
			this.loading = true;
			this.error = "";
			try { await handler.call(this); } catch (error) { this.error = errorMessage(error); } finally { this.loading = false; }
		},
		async applyFilters() { this.list.start = 0; await this.withLoading(this.loadList); },
		async resetFilters() { this.search = ""; this.filters = {}; this.list.start = 0; await this.withLoading(this.loadList); },
		async previousPage() { this.list.start = Math.max(0, (this.list.start || 0) - (this.list.page_length || this.pageLength)); await this.withLoading(this.loadList); },
		async nextPage() { this.list.start = (this.list.start || 0) + (this.list.page_length || this.pageLength); await this.withLoading(this.loadList); },
		changeResource() {
			const nextResource = this.resource;
			this.confirmDiscard(async () => { this.resource = nextResource; this.filters = {}; this.search = ""; this.list = { rows: [], total: 0, start: 0, page_length: this.pageLength }; this.pushLocation({ resource: this.resource }); await this.loadCurrentRoute(); });
		},
		openNewDocument() { if (this.canCreate) this.confirmDiscard(() => { this.pushLocation({ resource: this.resource, new: "1" }); this.loadCurrentRoute(); }); },
		openRow(row) { if (row?.name) this.confirmDiscard(() => { this.pushLocation({ resource: this.resource, name: row.name }); this.loadCurrentRoute(); }); },
		handleRowAction({ action, row }) { if (action.key === "open") this.openRow(row); },
		validateRequired() {
			const errors = {};
			for (const tab of this.document.schema?.tabs || []) for (const section of tab.sections || []) for (const field of section.fields || []) if (field.reqd && [null, undefined, ""].includes(this.model[field.fieldname])) errors[field.fieldname] = __("This field is required.");
			this.fieldErrors = errors;
			return Object.keys(errors).length === 0;
		},
		async saveDocument() {
			if (!this.canSave || this.saving || !this.validateRequired()) return;
			this.saving = true;
			try {
				const payload = await this.call(API.save, { resource: this.resource, name: this.document.is_new ? null : this.document.name, modified: this.document.modified || null, values: JSON.stringify(this.model) });
				this.setDocument(payload);
				if (payload?.name) this.replaceLocation({ resource: this.resource, name: payload.name });
				frappe.show_alert({ message: __("Pricing master saved"), indicator: "green" });
			} catch (error) {
				frappe.msgprint({ title: __("Unable to save"), message: errorMessage(error, __("The pricing master could not be saved.")), indicator: "red" });
			} finally { this.saving = false; }
		},
		requestDelete() {
			if (!this.canDelete) return;
			this.openConfirmation({ title: __("Delete pricing master"), message: __("Delete {0}? Linked records may prevent deletion. This cannot be undone.", [this.document.name]), confirmLabel: __("Delete"), danger: true, handler: this.deleteDocument });
		},
		async deleteDocument() {
			await this.call(API.remove, { resource: this.resource, name: this.document.name });
			frappe.show_alert({ message: __("Pricing master deleted"), indicator: "green" });
			this.dirty = false;
			this.closeConfirmation(true);
			this.backToList();
		},
		backToList() { this.confirmDiscard(() => { this.pushLocation({ resource: this.resource }); this.loadCurrentRoute(); }); },
		reloadCurrentView() { this.confirmDiscard(this.loadCurrentRoute); },
		handleBrowserNavigation() { if (this.dirty) { window.history.forward(); this.confirmDiscard(() => window.history.back()); return; } this.loadCurrentRoute(); },
		openConfirmation(config) { this.confirmation = { open: true, title: config.title || __("Confirm action"), subtitle: config.subtitle || "", message: config.message || "", confirmLabel: config.confirmLabel || __("Continue"), danger: Boolean(config.danger), busy: false, handler: config.handler || null }; },
		closeConfirmation(force = false) { if (this.confirmation.busy && !force) return; this.confirmation = { open: false, title: "", subtitle: "", message: "", confirmLabel: __("Continue"), danger: false, busy: false, handler: null }; },
		async confirmPendingAction() {
			if (!this.confirmation.handler || this.confirmation.busy) return;
			this.confirmation.busy = true;
			try { await this.confirmation.handler(); if (this.confirmation.open) this.closeConfirmation(true); } catch (error) { this.confirmation.busy = false; frappe.msgprint({ title: __("Unable to continue"), message: errorMessage(error), indicator: "red" }); }
		},
		pushLocation(params) { window.history.pushState({}, "", this.buildLocation(params)); },
		replaceLocation(params) { window.history.replaceState({}, "", this.buildLocation(params)); },
		buildLocation(params) { const query = new URLSearchParams(); Object.entries(params || {}).forEach(([key, value]) => { if (value !== null && value !== undefined && value !== "") query.set(key, value); }); return `/app/vetedge-pricing-master-workspace?${query.toString()}`; },
		updateListLocation() { const params = { resource: this.resource }; if (this.search) params.search = this.search; this.replaceLocation(params); },
		openRoute(route) { if (route) window.location.assign(route); },
	},
};
</script>

<style scoped>
.vetedge-pricing-filters {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
	gap: 0.85rem;
	width: 100%;
}
.vetedge-pricing-filter { display: grid; gap: 0.35rem; min-width: 0; }
.vetedge-pricing-filter > span { font-size: 0.78rem; font-weight: 700; color: var(--edge-text-muted, #667085); }
.vetedge-pricing-filter--search { grid-column: span 2; }
.vetedge-pricing-notice {
	margin-bottom: 1rem;
	padding: 0.9rem 1rem;
	border: 1px solid color-mix(in srgb, var(--edge-primary, #1769aa) 28%, transparent);
	border-radius: 0.75rem;
	background: color-mix(in srgb, var(--edge-primary, #1769aa) 7%, white);
}
.vetedge-pricing-notice strong { display: block; margin-bottom: 0.2rem; }
.vetedge-pricing-notice p { margin: 0; color: var(--edge-text-muted, #667085); }
.vetedge-pricing-summary {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: 0.8rem;
	margin-bottom: 1rem;
}
.vetedge-pricing-summary > div { display: grid; gap: 0.2rem; padding: 0.85rem 1rem; border: 1px solid var(--edge-border, #e4e7ec); border-radius: 0.75rem; background: var(--edge-surface, white); }
.vetedge-pricing-summary span { font-size: 0.78rem; color: var(--edge-text-muted, #667085); }
.vetedge-pricing-summary strong { font-size: 1rem; }
.vetedge-pricing-pagination { display: flex; gap: 0.5rem; }
@media (max-width: 760px) {
	.vetedge-pricing-filter--search { grid-column: auto; }
	.vetedge-pricing-summary { grid-template-columns: 1fr; }
}
</style>
