<template>
	<EdgeModal
		:open="openState"
		title="New Veterinary Appointment"
		subtitle="Search existing records or create an owner and patient without leaving Veterinary."
		size="lg"
		:busy="saving"
		@close="close"
	>
		<div v-if="loading" class="vetedge-appointment-quick-state">Loading appointment form...</div>
		<form v-else class="vetedge-appointment-quick-form" @submit.prevent="submit">
			<div v-if="error" class="vetedge-appointment-quick-error" role="alert">{{ error }}</div>
			<div class="vetedge-appointment-quick-grid">
				<EdgeLinkField
					v-model="form.owner"
					:selected-label="labels.owner"
					label="Pet Owner"
					placeholder="Search by owner name, phone or email"
					:searcher="searchOwner"
					:creator="bootstrap.can_create_owner ? createOwnerFromQuery : null"
					:can-create="bootstrap.can_create_owner"
					create-label="Create new owner"
					required
					@select="onOwnerSelected"
					@clear="clearOwner"
					@search-error="handleFieldError"
				/>

				<EdgeLinkField
					v-model="form.patient"
					:selected-label="labels.patient"
					label="Veterinary Patient"
					placeholder="Search the selected owner's patients"
					:searcher="searchPatient"
					:creator="canCreatePatient ? createPatientFromQuery : null"
					:can-create="canCreatePatient"
					:context="{ owner: form.owner, branch: form.branch }"
					:disabled="!form.owner"
					create-label="Create new patient"
					required
					@select="onPatientSelected"
					@clear="clearPatient"
					@search-error="handleFieldError"
				/>

				<EdgeLinkField
					v-model="form.branch"
					:selected-label="labels.branch"
					label="Branch"
					placeholder="Search permitted branches"
					:searcher="searchBranch"
					required
					@select="onBranchSelected"
					@clear="clearBranch"
					@search-error="handleFieldError"
				/>

				<EdgeLinkField
					v-model="form.practitioner"
					:selected-label="labels.practitioner"
					label="Veterinary Practitioner"
					placeholder="Search doctors available for this branch"
					:searcher="searchPractitioner"
					:context="{ branch: form.branch }"
					:disabled="!form.branch"
					required
					@select="onPractitionerSelected"
					@clear="clearPractitioner"
					@search-error="handleFieldError"
				/>

				<label class="vetedge-appointment-quick-field">
					<span>Appointment Date/Time <b>*</b></span>
					<input v-model="form.appointment_datetime" type="datetime-local" class="form-control" required />
				</label>

				<label class="vetedge-appointment-quick-field">
					<span>Appointment Type</span>
					<select v-model="form.appointment_type" class="form-control">
						<option v-for="type in bootstrap.appointment_types" :key="type" :value="type">{{ type }}</option>
					</select>
				</label>
			</div>

			<label class="vetedge-appointment-quick-field vetedge-appointment-quick-field--wide">
				<span>Notes</span>
				<textarea v-model.trim="form.notes" class="form-control" rows="3" placeholder="Reason for visit or front-desk notes"></textarea>
			</label>
		</form>

		<template #footer>
			<button type="button" class="edge-button" :disabled="saving" @click="close">Cancel</button>
			<button type="button" class="edge-button edge-button--primary" :disabled="saving || loading" @click="submit">
				{{ saving ? 'Creating...' : 'Create Appointment' }}
			</button>
		</template>
	</EdgeModal>
</template>

<script>
function emptyForm() {
	return {
		owner: "",
		patient: "",
		branch: "",
		practitioner: "",
		appointment_datetime: "",
		appointment_type: "Consultation",
		notes: "",
	};
}

function emptyLabels() {
	return { owner: "", patient: "", branch: "", practitioner: "" };
}

export default {
	name: "VetEdgeAppointmentQuickCreate",
	emits: ["created"],
	data() {
		return {
			openState: false,
			loading: false,
			saving: false,
			error: "",
			bootstrap: {
				default_branch: "",
				appointment_types: ["Consultation", "Follow Up", "Vaccination", "Grooming", "Boarding", "Other"],
				can_create_owner: false,
				can_create_patient: false,
				can_create_appointment: false,
			},
			form: emptyForm(),
			labels: emptyLabels(),
		};
	},
	computed: {
		canCreatePatient() {
			return Boolean(this.bootstrap.can_create_patient && this.form.owner);
		},
	},
	methods: {
		async open() {
			this.form = emptyForm();
			this.labels = emptyLabels();
			this.error = "";
			this.openState = true;
			this.loading = true;
			try {
				const response = await frappe.call("vetedge.services.appointment_edgeui.get_appointment_form_bootstrap");
				this.bootstrap = { ...this.bootstrap, ...(response.message || {}) };
				if (this.bootstrap.default_branch) {
					this.form.branch = this.bootstrap.default_branch;
					this.labels.branch = this.bootstrap.default_branch;
				}
				if (!this.bootstrap.can_create_appointment) {
					this.error = __("You do not have permission to create Veterinary Appointments.");
				}
			} catch (error) {
				this.error = error?.message || __("The appointment form could not be loaded.");
			} finally {
				this.loading = false;
			}
		},
		close() {
			if (!this.saving) this.openState = false;
		},
		async searchLink(field, query, context = {}) {
			const response = await frappe.call("vetedge.services.appointment_edgeui.search_appointment_link", {
				field,
				txt: query,
				context,
				start: 0,
				page_length: 20,
			});
			return response.message || [];
		},
		searchOwner(query) {
			return this.searchLink("owner", query);
		},
		searchPatient(query) {
			return this.searchLink("patient", query, { owner: this.form.owner, branch: this.form.branch });
		},
		searchBranch(query) {
			return this.searchLink("branch", query);
		},
		searchPractitioner(query) {
			return this.searchLink("practitioner", query, { branch: this.form.branch });
		},
		onOwnerSelected(option) {
			this.form.owner = option.value;
			this.labels.owner = option.label;
			this.clearPatient();
		},
		clearOwner() {
			this.form.owner = "";
			this.labels.owner = "";
			this.clearPatient();
		},
		onPatientSelected(option) {
			this.form.patient = option.value;
			this.labels.patient = option.label;
		},
		clearPatient() {
			this.form.patient = "";
			this.labels.patient = "";
		},
		onBranchSelected(option) {
			const changed = this.form.branch && this.form.branch !== option.value;
			this.form.branch = option.value;
			this.labels.branch = option.label;
			this.clearPractitioner();
			if (changed) this.clearPatient();
		},
		clearBranch() {
			this.form.branch = "";
			this.labels.branch = "";
			this.clearPractitioner();
			this.clearPatient();
		},
		onPractitionerSelected(option) {
			this.form.practitioner = option.value;
			this.labels.practitioner = option.label;
		},
		clearPractitioner() {
			this.form.practitioner = "";
			this.labels.practitioner = "";
		},
		handleFieldError(error) {
			this.error = error?.message || __("A linked record could not be loaded.");
		},
		createOwnerFromQuery(query) {
			return this.openFrappeQuickDialog({
				title: __("Create Pet Owner"),
				fields: [
					{ fieldname: "owner_name", fieldtype: "Data", label: __("Owner Name"), reqd: 1, default: query },
					{ fieldname: "mobile_no", fieldtype: "Phone", label: __("Mobile Number") },
					{ fieldname: "email_id", fieldtype: "Email", label: __("Email") },
				],
				method: "vetedge.services.appointment_edgeui.create_appointment_owner",
				primaryLabel: __("Create Owner"),
			});
		},
		createPatientFromQuery(query) {
			if (!this.form.owner) return Promise.resolve(null);
			return this.openFrappeQuickDialog({
				title: __("Create Veterinary Patient"),
				fields: [
					{ fieldname: "patient_name", fieldtype: "Data", label: __("Patient Name"), reqd: 1, default: query },
					{ fieldname: "primary_owner", fieldtype: "Link", options: "Customer", label: __("Primary Owner"), reqd: 1, default: this.form.owner, read_only: 1 },
					{ fieldname: "default_branch", fieldtype: "Link", options: "Branch", label: __("Default Branch"), default: this.form.branch, read_only: Boolean(this.form.branch) },
					{ fieldname: "species", fieldtype: "Link", options: "Veterinary Species", label: __("Species"), reqd: 1 },
					{ fieldname: "breed", fieldtype: "Link", options: "Veterinary Breed", label: __("Breed") },
					{ fieldname: "sex", fieldtype: "Select", options: "\nMale\nFemale\nUnknown", label: __("Sex") },
					{ fieldname: "microchip_id", fieldtype: "Data", label: __("Microchip ID") },
				],
				method: "vetedge.services.appointment_edgeui.create_appointment_patient",
				primaryLabel: __("Create Patient"),
				configure(dialog) {
					dialog.fields_dict.breed.get_query = () => ({
						filters: { species: dialog.get_value("species"), disabled: 0 },
					});
				},
			});
		},
		openFrappeQuickDialog({ title, fields, method, primaryLabel, configure = null }) {
			return new Promise((resolve) => {
				let settled = false;
				const finish = (value) => {
					if (settled) return;
					settled = true;
					resolve(value || null);
				};
				const dialog = new frappe.ui.Dialog({
					title,
					fields,
					primary_action_label: primaryLabel,
					primary_action: async (values) => {
						dialog.disable_primary_action();
						try {
							const response = await frappe.call(method, { values });
							finish(response.message || null);
							dialog.hide();
						} catch (error) {
							frappe.msgprint({
								title: __("Unable to create record"),
								message: error?.message || __("The linked record could not be created."),
								indicator: "red",
							});
						} finally {
							dialog.enable_primary_action();
						}
					},
				});
				dialog.onhide = () => finish(null);
				dialog.show();
				dialog.$wrapper?.one?.("hidden.bs.modal", () => finish(null));
				configure?.(dialog);
			});
		},
		appointmentPayload() {
			const datetime = String(this.form.appointment_datetime || "").replace("T", " ");
			return {
				patient: this.form.patient,
				branch: this.form.branch,
				practitioner: this.form.practitioner,
				appointment_datetime: datetime.length === 16 ? `${datetime}:00` : datetime,
				appointment_type: this.form.appointment_type,
				notes: this.form.notes,
			};
		},
		async submit() {
			this.error = "";
			if (!this.form.owner || !this.form.patient || !this.form.branch || !this.form.practitioner || !this.form.appointment_datetime) {
				this.error = __("Owner, Patient, Branch, Practitioner and Appointment Date/Time are required.");
				return;
			}
			this.saving = true;
			try {
				const response = await frappe.call("vetedge.services.appointment_edgeui.create_edgeui_appointment", {
					values: this.appointmentPayload(),
				});
				const created = response.message || {};
				frappe.show_alert({ message: __("Veterinary Appointment created"), indicator: "green" });
				this.$emit("created", created);
				this.openState = false;
			} catch (error) {
				this.error = error?.message || __("The Veterinary Appointment could not be created.");
			} finally {
				this.saving = false;
			}
		},
	},
};
</script>

<style scoped>
.vetedge-appointment-quick-form {
	display: grid;
	gap: 1rem;
}

.vetedge-appointment-quick-grid {
	display: grid;
	gap: .9rem;
	grid-template-columns: repeat(2, minmax(0, 1fr));
}

.vetedge-appointment-quick-field {
	display: grid;
	gap: .35rem;
	min-width: 0;
}

.vetedge-appointment-quick-field > span {
	color: var(--edge-color-ink-700, #415469);
	font-size: .75rem;
	font-weight: 700;
}

.vetedge-appointment-quick-field b {
	color: var(--edge-color-danger, #c53a3a);
}

.vetedge-appointment-quick-field--wide {
	grid-column: 1 / -1;
}

.vetedge-appointment-quick-error,
.vetedge-appointment-quick-state {
	border-radius: .65rem;
	font-size: .78rem;
	padding: .75rem .85rem;
}

.vetedge-appointment-quick-error {
	background: color-mix(in srgb, var(--edge-color-danger, #c53a3a) 9%, white);
	border: 1px solid color-mix(in srgb, var(--edge-color-danger, #c53a3a) 28%, white);
	color: var(--edge-color-danger, #c53a3a);
}

.vetedge-appointment-quick-state {
	color: var(--edge-color-ink-500, #6b7d90);
	text-align: center;
}

@media (max-width: 48rem) {
	.vetedge-appointment-quick-grid {
		grid-template-columns: minmax(0, 1fr);
	}
}
</style>
