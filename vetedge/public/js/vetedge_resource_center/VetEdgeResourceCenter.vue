<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/desk/vetedge-resource-center"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Veterinary Operations"
					:title="page.title || 'Veterinary Resource Center'"
					:subtitle="page.subtitle || 'Permission-safe records inside the Veterinary workspace.'"
					:action-label="primaryActionLabel"
					@action="runPrimaryAction"
				/>
			</template>

			<template #filters>
				<EdgeFilterBar title="Find records">
					<div
						class="vetedge-resource-filters"
						:class="{
							'is-patient-filters': isPatients,
							'is-clinical-filters': isClinicalResource,
						}"
					>
						<EdgeDropdown
							v-model="resource"
							label="Resource"
							:options="resourceOptions"
							@change="changeResource"
						/>

						<label class="vetedge-resource-field vetedge-resource-field--search">
							<span>Search</span>
							<input
								v-model.trim="search"
								type="search"
								class="form-control"
								placeholder="Name, patient, owner, status or visible field"
								@keyup.enter="applySearch"
							/>
						</label>

						<template v-if="isPatients">
							<EdgeLinkField
								v-model="patientFilters.default_branch"
								:selected-label="patientFilterLabels.default_branch"
								label="Branch"
								placeholder="All visible branches"
								:searcher="searchBranchFilter"
								@select="onPatientFilterSelect('default_branch', $event)"
								@clear="clearPatientFilter('default_branch')"
							/>
							<EdgeDropdown
								v-model="patientFilters.status"
								label="Patient Status"
								:options="patientStatusOptions"
								placeholder="All statuses"
							/>
							<EdgeDropdown
								v-model="patientFilters.registration_status"
								label="Registration"
								:options="registrationStatusOptions"
								placeholder="All registration states"
							/>
							<EdgeLinkField
								v-model="patientFilters.species"
								:selected-label="patientFilterLabels.species"
								label="Species"
								placeholder="All species"
								:searcher="searchSpeciesFilter"
								@select="onPatientFilterSelect('species', $event)"
								@clear="clearPatientFilter('species')"
							/>
						</template>

						<template v-else-if="isClinicalResource">
							<EdgeLinkField
								v-model="clinicalFilters.patient"
								:selected-label="clinicalFilterLabels.patient"
								label="Patient"
								placeholder="All Patients"
								:searcher="(query) => searchLink('Veterinary Patient', query)"
								@select="onClinicalFilterSelect('patient', $event)"
								@clear="clearClinicalFilter('patient')"
							/>
							<EdgeLinkField
								v-model="clinicalFilters.service_branch"
								:selected-label="clinicalFilterLabels.service_branch"
								label="Branch"
								placeholder="All permitted branches"
								:searcher="searchBranchFilter"
								@select="onClinicalFilterSelect('service_branch', $event)"
								@clear="clearClinicalFilter('service_branch')"
							/>
							<EdgeDropdown
								v-model="clinicalFilters.status"
								label="Status"
								placeholder="All statuses"
								:options="clinicalStatusOptions"
							/>
							<EdgeLinkField
								v-if="isLabOrders"
								v-model="clinicalFilters.lab_test"
								:selected-label="clinicalFilterLabels.lab_test"
								label="Lab Test"
								placeholder="All Lab Tests"
								:searcher="(query) => searchLink('Veterinary Lab Test', query)"
								@select="onClinicalFilterSelect('lab_test', $event)"
								@clear="clearClinicalFilter('lab_test')"
							/>
							<EdgeLinkField
								v-else
								v-model="clinicalFilters.vaccine"
								:selected-label="clinicalFilterLabels.vaccine"
								label="Vaccine"
								placeholder="All Vaccines"
								:searcher="(query) => searchLink('Veterinary Vaccine', query)"
								@select="onClinicalFilterSelect('vaccine', $event)"
								@clear="clearClinicalFilter('vaccine')"
							/>
							<EdgeInput v-model="clinicalFilters.from_date" type="date" label="From Date" />
							<EdgeInput v-model="clinicalFilters.to_date" type="date" label="To Date" />
						</template>
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
						<span>{{ page.summary_label || 'Branch Scope' }}</span>
						<strong>{{ page.summary_value || page.context_branch || 'All permitted branches' }}</strong>
					</div>
				</section>

				<EdgeEmptyState
					v-if="!page.rows?.length"
					title="No matching records"
					description="Change the search or filters, or choose another Veterinary resource."
					:action-label="primaryActionLabel"
					@action="runPrimaryAction"
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
										<span :class="cellClass(column, row[column.fieldname], row)">
											{{ formatValue(column, row[column.fieldname], row) }}
										</span>
									</td>
									<td class="vetedge-resource-row-actions" data-label="Actions">
										<button
											v-if="isPatients && row._registration_action?.label"
											type="button"
											class="edge-button edge-button--compact"
											:class="registrationActionClass(row)"
											@click="openRegistrationBilling(row)"
										>
											{{ row._registration_action.label }}
										</button>
										<button
											v-if="isPatients"
											type="button"
											class="edge-button edge-button--compact edge-button--primary"
											@click="openMedicalHistory(row)"
										>
											Medical History
										</button>
										<button
											v-if="isClinicalResource"
											type="button"
											class="edge-button edge-button--compact edge-button--primary"
											@click="openClinicalRecord(row)"
										>
											View / Edit
										</button>
										<template v-if="isAppointments">
											<button
												v-for="action in appointmentActions(row)"
												:key="`${row.name}:${action.key}`"
												type="button"
												class="edge-button edge-button--compact"
												:class="appointmentActionClass(action)"
												:disabled="isAppointmentActionBusy(row, action)"
												@click="runAppointmentAction(row, action)"
											>
												{{ isAppointmentActionBusy(row, action) ? 'Processing…' : action.label }}
											</button>
										</template>
										<button
											v-if="!isClinicalResource && canEditRow(row)"
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
											v-if="!isClinicalResource && canDeleteRow(row)"
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
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasPrevious || loading" @click="previousPage">Previous</button>
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasNext || loading" @click="nextPage">Next</button>
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

const CLINICAL_RESOURCES = Object.freeze({
	"lab-orders": "Veterinary Lab Order",
	vaccinations: "Veterinary Vaccination Record",
});

function emptyPatientFilters() {
	return { default_branch: "", status: "", registration_status: "", species: "" };
}

function emptyPatientFilterLabels() {
	return { default_branch: "", species: "" };
}

function emptyClinicalFilters() {
	return { patient: "", service_branch: "", status: "", from_date: "", to_date: "", vaccine: "", lab_test: "" };
}

function emptyClinicalFilterLabels() {
	return { patient: "", service_branch: "", vaccine: "", lab_test: "" };
}

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
			appointmentActionBusy: "",
			patientFilters: {
				default_branch: parameters.get("branch") || "",
				status: parameters.get("status") || "",
				registration_status: parameters.get("registration_status") || "",
				species: parameters.get("species") || "",
			},
			patientFilterLabels: {
				default_branch: parameters.get("branch") || "",
				species: parameters.get("species") || "",
			},
			clinicalFilters: {
				patient: parameters.get("patient") || "",
				service_branch: parameters.get("service_branch") || parameters.get("branch") || "",
				status: parameters.get("status") || "",
				from_date: parameters.get("from_date") || "",
				to_date: parameters.get("to_date") || "",
				vaccine: parameters.get("vaccine") || "",
				lab_test: parameters.get("lab_test") || "",
			},
			clinicalFilterLabels: {
				patient: parameters.get("patient") || "",
				service_branch: parameters.get("service_branch") || parameters.get("branch") || "",
				vaccine: parameters.get("vaccine") || "",
				lab_test: parameters.get("lab_test") || "",
			},
			page: {
				title: "Veterinary Resource Center",
				subtitle: "Permission-safe Veterinary records.",
				columns: [],
				rows: [],
				total: 0,
				can_create: false,
				can_quick_edit: false,
				can_delete: false,
				full_form_route: "",
				summary_label: "Branch Scope",
				summary_value: "All permitted branches",
			},
			resourceOptions: RESOURCE_OPTIONS,
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
		isPatients() {
			return this.resource === "patients";
		},
		isAppointments() {
			return this.resource === "appointments";
		},
		isLabOrders() {
			return this.resource === "lab-orders";
		},
		isVaccinations() {
			return this.resource === "vaccinations";
		},
		isClinicalResource() {
			return Boolean(CLINICAL_RESOURCES[this.resource]);
		},
		clinicalDoctype() {
			return CLINICAL_RESOURCES[this.resource] || "";
		},
		primaryActionLabel() {
			if (this.resource === "appointments") return "New Appointment";
			if (this.isLabOrders) return "New Lab Order";
			if (this.isVaccinations) return "New Vaccination";
			return this.page.can_create ? "Add Record" : "";
		},
		patientStatusOptions() {
			return ["Active", "Inactive", "Deceased"].map((value) => ({ value, label: value }));
		},
		registrationStatusOptions() {
			return ["Registered", "Awaiting Registration Payment", "Registration Paid"].map((value) => ({ value, label: value }));
		},
		clinicalStatusOptions() {
			const values = this.isLabOrders
				? ["Draft", "Ordered", "Sample Collected", "Sent to Lab", "In Progress", "Result Pending", "Result Entered", "Awaiting Review", "Reviewed", "Completed", "Cancelled"]
				: ["Draft", "Awaiting Payment", "Pending Administration", "Administered", "Cancelled"];
			return values.map((value) => ({ value, label: value }));
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
		async searchLink(doctype, query) {
			const response = await frappe.call("frappe.desk.search.search_link", {
				doctype,
				txt: String(query || ""),
				page_length: 20,
				ignore_user_permissions: 0,
			});
			return response.message || [];
		},
		searchBranchFilter(query) {
			return this.searchLink("Branch", query);
		},
		searchSpeciesFilter(query) {
			return this.searchLink("Veterinary Species", query);
		},
		normalizeLinkSelection(selection) {
			if (!selection) return { value: "", label: "" };
			if (typeof selection === "string") return { value: selection, label: selection };
			return {
				value: selection.value || selection.name || selection.id || "",
				label: selection.label || selection.description || selection.value || selection.name || "",
			};
		},
		onPatientFilterSelect(fieldname, selection) {
			const normalized = this.normalizeLinkSelection(selection);
			this.patientFilters[fieldname] = normalized.value;
			this.patientFilterLabels[fieldname] = normalized.label;
		},
		clearPatientFilter(fieldname) {
			this.patientFilters[fieldname] = "";
			this.patientFilterLabels[fieldname] = "";
		},
		onClinicalFilterSelect(fieldname, selection) {
			const normalized = this.normalizeLinkSelection(selection);
			this.clinicalFilters[fieldname] = normalized.value;
			this.clinicalFilterLabels[fieldname] = normalized.label;
		},
		clearClinicalFilter(fieldname) {
			this.clinicalFilters[fieldname] = "";
			this.clinicalFilterLabels[fieldname] = "";
		},
		updateLocation() {
			const parameters = new URLSearchParams();
			parameters.set("resource", this.resource);
			if (this.search) parameters.set("search", this.search);
			if (this.isPatients) {
				if (this.patientFilters.default_branch) parameters.set("branch", this.patientFilters.default_branch);
				if (this.patientFilters.status) parameters.set("status", this.patientFilters.status);
				if (this.patientFilters.registration_status) parameters.set("registration_status", this.patientFilters.registration_status);
				if (this.patientFilters.species) parameters.set("species", this.patientFilters.species);
			} else if (this.isClinicalResource) {
				for (const key of ["patient", "service_branch", "status", "from_date", "to_date", "vaccine", "lab_test"]) {
					if (this.clinicalFilters[key]) parameters.set(key, this.clinicalFilters[key]);
				}
			}
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
					default_branch: this.isPatients ? this.patientFilters.default_branch : "",
					status: this.isPatients ? this.patientFilters.status : (this.isClinicalResource ? this.clinicalFilters.status : ""),
					registration_status: this.isPatients ? this.patientFilters.registration_status : "",
					species: this.isPatients ? this.patientFilters.species : "",
					patient: this.isClinicalResource ? this.clinicalFilters.patient : "",
					service_branch: this.isClinicalResource ? this.clinicalFilters.service_branch : "",
					from_date: this.isClinicalResource ? this.clinicalFilters.from_date : "",
					to_date: this.isClinicalResource ? this.clinicalFilters.to_date : "",
					vaccine: this.isVaccinations ? this.clinicalFilters.vaccine : "",
					lab_test: this.isLabOrders ? this.clinicalFilters.lab_test : "",
				});
				this.page = response.message || this.page;
				if (this.isPatients && this.page.context_branch && !this.patientFilters.default_branch) {
					this.patientFilters.default_branch = this.page.context_branch;
					this.patientFilterLabels.default_branch = this.page.context_branch;
				}
				if (this.isClinicalResource && this.page.context_branch && !this.clinicalFilters.service_branch) {
					this.clinicalFilters.service_branch = this.page.context_branch;
					this.clinicalFilterLabels.service_branch = this.page.context_branch;
				}
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
			this.patientFilters = emptyPatientFilters();
			this.patientFilterLabels = emptyPatientFilterLabels();
			this.clinicalFilters = emptyClinicalFilters();
			this.clinicalFilterLabels = emptyClinicalFilterLabels();
			this.loadPage();
		},
		applySearch() {
			this.start = 0;
			this.loadPage();
		},
		resetSearch() {
			this.search = "";
			this.patientFilters = emptyPatientFilters();
			this.patientFilterLabels = emptyPatientFilterLabels();
			this.clinicalFilters = emptyClinicalFilters();
			this.clinicalFilterLabels = emptyClinicalFilterLabels();
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
		formatValue(column, value, row = null) {
			const display = row?._display?.[column.fieldname];
			if (display) return String(display);
			if (value === null || value === undefined || value === "") return "—";
			if (column.fieldname === "docstatus") return { 0: "Draft", 1: "Submitted", 2: "Cancelled" }[Number(value)] || String(value);
			if (column.fieldtype === "Check") return Number(value) ? "Yes" : "No";
			if (["Datetime", "Date"].includes(column.fieldtype) && frappe.datetime?.str_to_user) return frappe.datetime.str_to_user(value);
			return String(value);
		},
		cellClass(column, value) {
			if (["status", "docstatus", "registration_status"].includes(column.fieldname)) {
				return `vetedge-resource-status status-${String(this.formatValue(column, value)).toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
			}
			return "";
		},
		registrationActionClass(row) {
			return row?._registration_action?.tone === "primary" ? "edge-button--primary" : "";
		},
		appointmentActions(row) {
			if (!this.isAppointments) return [];
			return row?._appointment_action_state?.actions || [];
		},
		appointmentActionKey(row, action) {
			return `${row?.name || ''}:${action?.key || ''}`;
		},
		isAppointmentActionBusy(row, action) {
			return this.appointmentActionBusy === this.appointmentActionKey(row, action);
		},
		appointmentActionClass(action) {
			return {
				"edge-button--primary": Boolean(action?.primary),
				"edge-button--danger": Boolean(action?.danger),
			};
		},
		async runAppointmentAction(row, action) {
			if (!row?.name || !action?.key || this.appointmentActionBusy) return;
			this.appointmentActionBusy = this.appointmentActionKey(row, action);
			try {
				const response = await frappe.call("vetedge.services.appointment_actions.perform_appointment_action", {
					appointment: row.name,
					action: action.key,
					expected_modified: row.modified,
				});
				const result = response.message || {};
				if (result.message) {
					frappe.show_alert({ message: __(result.message), indicator: "green" });
				}
				if (result.open?.route) {
					window.location.assign(result.open.route);
					return;
				}
				if (result.mutated) {
					await this.loadPage();
				} else if (result.state) {
					row._appointment_action_state = result.state;
				}
			} catch (error) {
				frappe.msgprint({
					title: __("Appointment action unavailable"),
					message: error?.message || __("The appointment action could not be completed."),
					indicator: "red",
				});
			} finally {
				this.appointmentActionBusy = "";
			}
		},
		canEditRow(row) {
			return Boolean(this.page.can_quick_edit && Number(row.docstatus || 0) === 0);
		},
		canDeleteRow(row) {
			return Boolean(this.page.can_delete && Number(row.docstatus || 0) === 0);
		},
		runPrimaryAction() {
			if (this.isClinicalResource) {
				this.openClinicalCreate();
				return;
			}
			this.openEditor();
		},
		openEditor() {
			frappe.msgprint(__("The Veterinary quick editor is unavailable. Refresh the page and try again."));
		},
		openFullRecord(name) {
			if (!this.page.full_form_route || !name) return;
			this.openRoute(`${this.page.full_form_route}/${encodeURIComponent(name)}`);
		},
		billingFrame(doctype, name) {
			return {
				doc: { doctype, name },
				is_new: () => false,
				is_dirty: () => false,
				reload_doc: async () => this.loadPage(),
			};
		},
		openRegistrationBilling(row) {
			if (!row?.name || !window.vetedgeBillingModal?.open) {
				frappe.msgprint(__("The shared VetEdge Billing & Payment modal is unavailable. Refresh the page and try again."));
				return;
			}
			window.vetedgeBillingModal.open(this.billingFrame("Veterinary Patient", row.name));
		},
		openMedicalHistory(row) {
			if (!row?.name) return;
			this.openRoute(`/desk/veterinary-medical-history?patient=${encodeURIComponent(row.name)}`);
		},
		async ensureClinicalEditor() {
			if (window.VetEdgeClinicalRecordEditor?.ready?.()) return window.VetEdgeClinicalRecordEditor;
			await new Promise((resolve) => {
				frappe.require("vetedge_edge_modal_presenter.bundle.js", () => {
					frappe.require("vetedge_clinical_record_editor.bundle.js", resolve);
				});
			});
			if (!window.VetEdgeClinicalRecordEditor?.ready?.()) throw new Error(__("The EdgeSuite clinical editor is unavailable."));
			return window.VetEdgeClinicalRecordEditor;
		},
		async openClinicalCreate() {
			try {
				const editor = await this.ensureClinicalEditor();
				await editor.create(this.clinicalDoctype, () => this.loadPage());
			} catch (error) {
				frappe.msgprint(error?.message || __("The clinical record creator is unavailable."));
			}
		},
		async openClinicalRecord(row) {
			if (!row?.name || !this.clinicalDoctype) return;
			try {
				const editor = await this.ensureClinicalEditor();
				await editor.open({ doctype: this.clinicalDoctype, name: row.name, onSaved: () => this.loadPage() });
			} catch (error) {
				frappe.msgprint(error?.message || __("The clinical record editor is unavailable."));
			}
		},
		deleteRecord(row) {
			frappe.confirm(
				__("Delete {0}? This is only allowed for an unsubmitted record you have permission to delete.", [row.name]),
				async () => {
					try {
						await frappe.call("vetedge.services.resource_center.delete_resource_record", { resource: this.resource, name: row.name });
						frappe.show_alert({ message: __("Record deleted"), indicator: "green" });
						await this.loadPage();
					} catch (error) {
						frappe.msgprint({ title: __("Unable to delete record"), message: error?.message || __("The record could not be deleted."), indicator: "red" });
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
	grid-template-columns: minmax(12rem, .7fr) minmax(18rem, 1.3fr);
	width: 100%;
}

.vetedge-resource-filters.is-patient-filters,
.vetedge-resource-filters.is-clinical-filters {
	grid-template-columns: repeat(3, minmax(12rem, 1fr));
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

.vetedge-resource-summary,
.vetedge-resource-table-card {
	background: var(--edge-color-surface, #fff);
	border: 1px solid var(--edge-color-border, #dce5ef);
	border-radius: var(--edge-radius-lg, 1rem);
	box-shadow: var(--edge-shadow-xs, 0 1px 2px rgb(18 32 51 / 5%));
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

.vetedge-resource-table-card { overflow: hidden; }
.vetedge-resource-table-scroll { overflow-x: auto; }

.vetedge-resource-table {
	border-collapse: collapse;
	min-width: 62rem;
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

.vetedge-resource-table tbody tr:hover { background: var(--edge-color-brand-50, #eef7ff); }
.vetedge-resource-actions-column { min-width: 24rem; }

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
.status-active,
.status-registration-paid,
.status-administered,
.status-reviewed {
	background: #e8f8f0;
	color: #137a50;
}

.status-awaiting-registration-payment,
.status-awaiting-payment,
.status-pending-administration,
.status-result-pending,
.status-draft,
.status-partly-paid {
	background: #fff8e6;
	color: #8a5a00;
}

.status-cancelled,
.status-closed,
.status-deceased {
	background: #fef3f2;
	color: #b42318;
}

@media (max-width: 74rem) {
	.vetedge-resource-filters.is-patient-filters,
	.vetedge-resource-filters.is-clinical-filters {
		grid-template-columns: repeat(2, minmax(12rem, 1fr));
	}
}

@media (max-width: 47.99rem) {
	.vetedge-resource-filters,
	.vetedge-resource-filters.is-patient-filters,
	.vetedge-resource-filters.is-clinical-filters,
	.vetedge-resource-summary {
		grid-template-columns: minmax(0, 1fr);
	}

	.vetedge-resource-pagination {
		align-items: flex-start;
		flex-direction: column;
	}
}
</style>