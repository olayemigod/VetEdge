<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/app/vetedge-resource-center"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Veterinary Operations"
					:title="page.title || 'Veterinary Resource Center'"
					:subtitle="page.subtitle || 'Permission-safe records inside the Veterinary workspace.'"
					:action-label="page.can_create ? 'Add Record' : ''"
					@action="openEditor()"
				/>
			</template>

			<template #filters>
				<EdgeFilterBar title="Find records">
					<div class="vetedge-resource-filters">
						<label class="vetedge-resource-field">
							<span>Resource</span>
							<select v-model="resource" class="form-control" @change="changeResource">
								<option v-for="option in resourceOptions" :key="option.value" :value="option.value">
									{{ option.label }}
								</option>
							</select>
						</label>
						<label class="vetedge-resource-field vetedge-resource-field--search">
							<span>Search</span>
							<input
								v-model.trim="search"
								type="search"
								class="form-control"
								placeholder="Name, status or visible field"
								@keyup.enter="applySearch"
							/>
						</label>
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="applySearch">
							Apply
						</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetSearch">
							Reset
						</button>
					</template>
				</EdgeFilterBar>
			</template>

			<EdgeLoadingState v-if="loading" message="Loading Veterinary records..." :skeleton="true" />
			<EdgeErrorState
				v-else-if="error"
				title="The resource could not load"
				:message="error"
				action-label="Try again"
				@retry="loadPage"
			/>
			<template v-else>
				<section v-if="page.unsupported_required_fields?.length" class="vetedge-resource-notice">
					<div>
						<strong>Full ERPNext form required for create or edit</strong>
						<p>
							This record contains workflow fields that the quick editor must not simplify:
							{{ page.unsupported_required_fields.join(', ') }}.
						</p>
					</div>
					<button type="button" class="edge-button" @click="openFullList">Open full form in new tab</button>
				</section>

				<section class="vetedge-resource-summary" aria-label="Resource summary">
					<div>
						<span>Total visible records</span>
						<strong>{{ page.total || 0 }}</strong>
					</div>
					<div>
						<span>Current page</span>
						<strong>{{ currentPage }} of {{ totalPages }}</strong>
					</div>
					<div>
						<span>Access</span>
						<strong>{{ accessLabel }}</strong>
					</div>
				</section>

				<EdgeEmptyState
					v-if="!page.rows?.length"
					title="No matching records"
					description="Change the search term or choose another Veterinary resource."
					:action-label="page.can_create ? 'Add Record' : ''"
					@action="openEditor()"
				/>

				<section v-else class="vetedge-resource-table-card">
					<div class="vetedge-resource-table-scroll">
						<table class="vetedge-resource-table">
							<thead>
								<tr>
									<th v-for="column in page.columns" :key="column.fieldname">{{ column.label }}</th>
									<th class="vetedge-resource-actions-column">Actions</th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="row in page.rows" :key="row.name">
									<td v-for="column in page.columns" :key="column.fieldname" :data-label="column.label">
										<span :class="cellClass(column, row[column.fieldname])">
											{{ formatValue(column, row[column.fieldname]) }}
										</span>
									</td>
									<td class="vetedge-resource-row-actions" data-label="Actions">
										<button
											v-if="canEditRow(row)"
											type="button"
											class="edge-button edge-button--compact"
											@click="openEditor(row.name)"
										>
											Quick Edit
										</button>
										<button type="button" class="edge-button edge-button--compact" @click="openFullRecord(row.name)">
											Open Full Form
										</button>
										<button
											v-if="canDeleteRow(row)"
											type="button"
											class="edge-button edge-button--compact edge-button--danger"
											@click="deleteRecord(row)"
										>
											Delete
										</button>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
					<footer class="vetedge-resource-pagination">
						<span>Showing {{ firstVisible }}–{{ lastVisible }} of {{ page.total }}</span>
						<div>
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasPrevious || loading" @click="previousPage">
								Previous
							</button>
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasNext || loading" @click="nextPage">
								Next
							</button>
						</div>
					</footer>
				</section>
			</template>
		</EdgePageLayout>
	</EdgeAppShell>
</template>

<script>
const RESOURCE_OPTIONS = Object.freeze([
	{ value: "patients", label: "Patients" },
	{ value: "appointments", label: "Appointments" },
	{ value: "missed-appointments", label: "Missed Appointments" },
	{ value: "consultations", label: "Consultations" },
	{ value: "lab-orders", label: "Laboratory Orders" },
	{ value: "vaccinations", label: "Vaccination Records" },
	{ value: "grooming", label: "Grooming Appointments" },
	{ value: "boarding", label: "Boarding Bookings" },
	{ value: "kennels", label: "Kennels and Care Locations" },
]);

export default {
	name: "VetEdgeResourceCenter",
	data() {
		const parameters = new URLSearchParams(window.location.search || "");
		const requested = parameters.get("resource") || "patients";
		return {
			loading: true,
			error: "",
			search: parameters.get("search") || "",
			resource: RESOURCE_OPTIONS.some((option) => option.value === requested) ? requested : "patients",
			start: 0,
			pageLength: 25,
			page: {
				title: "Veterinary Resource Center",
				subtitle: "Permission-safe Veterinary records.",
				columns: [],
				rows: [],
				total: 0,
				can_create: false,
				can_quick_edit: false,
				can_delete: false,
				unsupported_required_fields: [],
				full_form_route: "",
			},
			resourceOptions: RESOURCE_OPTIONS,
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
		currentPage() {
			return Math.floor((this.page.start || 0) / (this.page.page_length || this.pageLength)) + 1;
		},
		totalPages() {
			return Math.max(1, Math.ceil((this.page.total || 0) / (this.page.page_length || this.pageLength)));
		},
		hasPrevious() {
			return (this.page.start || 0) > 0;
		},
		hasNext() {
			return (this.page.start || 0) + (this.page.rows?.length || 0) < (this.page.total || 0);
		},
		firstVisible() {
			return this.page.total ? (this.page.start || 0) + 1 : 0;
		},
		lastVisible() {
			return Math.min((this.page.start || 0) + (this.page.rows?.length || 0), this.page.total || 0);
		},
		accessLabel() {
			if (this.page.can_create && this.page.can_quick_edit) return "Create and edit";
			if (this.page.can_quick_edit) return "Edit permitted";
			return "Read only";
		},
	},
	mounted() {
		this.loadPage();
	},
	methods: {
		openRoute(route) {
			const adapter = (window.EdgeSuiteUI || window.EdgeUI)?.getAdapter?.("navigation:vetedge");
			if (adapter?.open?.(route) === true) return;
			window.location.assign(route);
		},
		updateLocation() {
			const parameters = new URLSearchParams();
			parameters.set("resource", this.resource);
			if (this.search) parameters.set("search", this.search);
			window.history.replaceState({}, "", `${window.location.pathname}?${parameters.toString()}`);
		},
		async loadPage() {
			this.loading = true;
			this.error = "";
			try {
				const response = await frappe.call("vetedge.services.resource_center.get_resource_page", {
					resource: this.resource,
					search: this.search,
					start: this.start,
					page_length: this.pageLength,
				});
				this.page = response.message || this.page;
				this.updateLocation();
			} catch (error) {
				this.error = error?.message || __("The Veterinary resource could not be loaded.");
			} finally {
				this.loading = false;
			}
		},
		changeResource() {
			this.start = 0;
			this.search = "";
			this.loadPage();
		},
		applySearch() {
			this.start = 0;
			this.loadPage();
		},
		resetSearch() {
			this.search = "";
			this.start = 0;
			this.loadPage();
		},
		previousPage() {
			this.start = Math.max(0, (this.page.start || 0) - (this.page.page_length || this.pageLength));
			this.loadPage();
		},
		nextPage() {
			this.start = (this.page.start || 0) + (this.page.page_length || this.pageLength);
			this.loadPage();
		},
		formatValue(column, value) {
			if (value === null || value === undefined || value === "") return "—";
			if (column.fieldname === "docstatus") {
				return { 0: "Draft", 1: "Submitted", 2: "Cancelled" }[Number(value)] || String(value);
			}
			if (column.fieldtype === "Check") return Number(value) ? "Yes" : "No";
			if (column.fieldtype === "Datetime" && frappe.datetime?.str_to_user) {
				return frappe.datetime.str_to_user(value);
			}
			if (column.fieldtype === "Date" && frappe.datetime?.str_to_user) {
				return frappe.datetime.str_to_user(value);
			}
			return String(value);
		},
		cellClass(column, value) {
			if (column.fieldname === "status" || column.fieldname === "docstatus") {
				return `vetedge-resource-status status-${String(this.formatValue(column, value)).toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
			}
			return "";
		},
		canEditRow(row) {
			return Boolean(this.page.can_quick_edit && Number(row.docstatus || 0) === 0);
		},
		canDeleteRow(row) {
			return Boolean(this.page.can_delete && Number(row.docstatus || 0) === 0);
		},
		openFullList() {
			if (this.page.full_form_route) window.open(this.page.full_form_route, "_blank", "noopener,noreferrer");
		},
		openFullRecord(name) {
			if (!this.page.full_form_route || !name) return;
			window.open(`${this.page.full_form_route}/${encodeURIComponent(name)}`, "_blank", "noopener,noreferrer");
		},
		fieldDefinition(field) {
			return {
				fieldname: field.fieldname,
				fieldtype: field.fieldtype,
				label: field.label,
				options: field.options || undefined,
				reqd: Boolean(field.reqd),
				description: field.description || undefined,
				default: field.default,
				depends_on: field.depends_on || undefined,
				mandatory_depends_on: field.mandatory_depends_on || undefined,
			};
		},
		async openEditor(name = null) {
			try {
				const response = await frappe.call("vetedge.services.resource_center.get_resource_editor", {
					resource: this.resource,
					name,
				});
				const schema = response.message || {};
				if (!schema.can_save) {
					this.openFullRecord(name);
					return;
				}

				const dialog = new frappe.ui.Dialog({
					title: schema.title || __("Veterinary Record"),
					fields: (schema.fields || []).map(this.fieldDefinition),
					primary_action_label: name ? __("Save Changes") : __("Create Record"),
					primary_action: async (values) => {
						dialog.disable_primary_action();
						try {
							await frappe.call("vetedge.services.resource_center.save_resource_record", {
								resource: this.resource,
								name,
								values,
							});
							dialog.hide();
							frappe.show_alert({ message: name ? __("Record updated") : __("Record created"), indicator: "green" });
							await this.loadPage();
						} catch (error) {
							frappe.msgprint({
								title: __("Unable to save record"),
								message: error?.message || __("The record could not be saved."),
								indicator: "red",
							});
						} finally {
							dialog.enable_primary_action();
						}
					},
				});
				dialog.show();
				dialog.set_values(schema.values || {});
			} catch (error) {
				frappe.msgprint({
					title: __("Quick editor unavailable"),
					message: error?.message || __("Use the full ERPNext form for this record."),
					indicator: "orange",
				});
				if (name) this.openFullRecord(name);
				else this.openFullList();
			}
		},
		deleteRecord(row) {
			frappe.confirm(
				__("Delete {0}? This is only allowed for an unsubmitted record you have permission to delete.", [row.name]),
				async () => {
					try {
						await frappe.call("vetedge.services.resource_center.delete_resource_record", {
							resource: this.resource,
							name: row.name,
						});
						frappe.show_alert({ message: __("Record deleted"), indicator: "green" });
						await this.loadPage();
					} catch (error) {
						frappe.msgprint({
							title: __("Unable to delete record"),
							message: error?.message || __("The record could not be deleted."),
							indicator: "red",
						});
					}
				}
			);
		},
	},
};
</script>

<style scoped>
.vetedge-resource-filters {
	display: grid;
	gap: var(--edge-card-gap, .75rem);
	grid-template-columns: minmax(12rem, .7fr) minmax(16rem, 1.3fr);
	width: 100%;
}

.vetedge-resource-field {
	display: grid;
	gap: .35rem;
	min-width: 0;
}

.vetedge-resource-field > span {
	color: var(--edge-color-ink-700, #415469);
	font-size: .72rem;
	font-weight: 700;
}

.vetedge-resource-notice,
.vetedge-resource-summary,
.vetedge-resource-table-card {
	background: var(--edge-color-surface, #fff);
	border: 1px solid var(--edge-color-border, #dce5ef);
	border-radius: var(--edge-radius-lg, 1rem);
	box-shadow: var(--edge-shadow-xs, 0 1px 2px rgb(18 32 51 / 5%));
}

.vetedge-resource-notice {
	align-items: center;
	display: flex;
	gap: 1rem;
	justify-content: space-between;
	padding: .85rem 1rem;
}

.vetedge-resource-notice p {
	color: var(--edge-color-ink-500, #6b7d90);
	font-size: .78rem;
	margin: .25rem 0 0;
}

.vetedge-resource-summary {
	display: grid;
	gap: var(--edge-card-gap, .75rem);
	grid-template-columns: repeat(3, minmax(0, 1fr));
	margin-bottom: var(--edge-section-gap, 1rem);
	padding: .75rem;
}

.vetedge-resource-summary > div {
	background: var(--edge-color-surface-soft, #f9fbfd);
	border: 1px solid var(--edge-color-border, #dce5ef);
	border-radius: .75rem;
	display: grid;
	gap: .25rem;
	padding: .7rem .8rem;
}

.vetedge-resource-summary span {
	color: var(--edge-color-ink-500, #6b7d90);
	font-size: .68rem;
}

.vetedge-resource-summary strong {
	color: var(--edge-color-ink-950, #122033);
	font-size: 1rem;
}

.vetedge-resource-table-card {
	overflow: hidden;
}

.vetedge-resource-table-scroll {
	overflow-x: auto;
}

.vetedge-resource-table {
	border-collapse: collapse;
	min-width: 58rem;
	width: 100%;
}

.vetedge-resource-table th,
.vetedge-resource-table td {
	border-bottom: 1px solid var(--edge-color-border, #dce5ef);
	font-size: .75rem;
	padding: .65rem .75rem;
	text-align: left;
	vertical-align: middle;
}

.vetedge-resource-table th {
	background: var(--edge-color-surface-soft, #f9fbfd);
	color: var(--edge-color-ink-700, #415469);
	font-size: .68rem;
	font-weight: 780;
	letter-spacing: .025em;
	position: sticky;
	top: 0;
	white-space: nowrap;
}

.vetedge-resource-table tbody tr:hover {
	background: var(--edge-color-brand-50, #eef7ff);
}

.vetedge-resource-actions-column {
	min-width: 17rem;
}

.vetedge-resource-row-actions,
.vetedge-resource-pagination,
.vetedge-resource-pagination > div {
	align-items: center;
	display: flex;
	flex-wrap: wrap;
	gap: .45rem;
}

.edge-button--compact {
	min-height: 2rem;
	padding: .35rem .55rem;
}

.edge-button--danger {
	border-color: #fecdca;
	color: #b42318;
}

.vetedge-resource-pagination {
	justify-content: space-between;
	padding: .7rem .8rem;
}

.vetedge-resource-pagination > span {
	color: var(--edge-color-ink-500, #6b7d90);
	font-size: .72rem;
}

.vetedge-resource-status {
	background: var(--edge-color-surface-muted, #f5f8fc);
	border-radius: 999px;
	display: inline-flex;
	font-size: .68rem;
	font-weight: 700;
	padding: .25rem .5rem;
}

.status-submitted,
.status-completed,
.status-paid,
.status-active {
	background: #e8f8f0;
	color: #137a50;
}

.status-cancelled,
.status-closed {
	background: #fef3f2;
	color: #b42318;
}

@media (max-width: 47.99rem) {
	.vetedge-resource-filters,
	.vetedge-resource-summary {
		grid-template-columns: minmax(0, 1fr);
	}

	.vetedge-resource-notice,
	.vetedge-resource-pagination {
		align-items: flex-start;
		flex-direction: column;
	}
}
</style>
