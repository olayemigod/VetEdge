<template>
	<EdgeModal
		:open="openState"
		title="New Veterinary Appointment"
		subtitle="Select the patient first. VetEdge will derive the pet owner, then you can choose the service branch and practitioner."
		size="lg"
		:busy="saving"
		@close="close"
	>
		<div v-if="loading" class="vetedge-appointment-flow-state">Loading appointment form...</div>

		<div v-else>
			<div v-if="error" class="vetedge-appointment-flow-error" role="alert">{{ error }}</div>

			<form class="vetedge-appointment-flow-form" @submit.prevent="submitAppointment">
				<div class="vetedge-appointment-flow-grid">
					<EdgeLinkField
						v-model="form.patient"
						:selected-label="labels.patient"
						label="Veterinary Patient"
						placeholder="Search patient name, patient ID, owner or microchip"
						:searcher="searchPatient"
						required
						@select="onPatientSelected"
						@clear="clearPatient"
						@search-error="handleFieldError"
					/>

					<label class="vetedge-appointment-flow-field">
						<span>Pet Owner</span>
						<input
							:value="labels.owner || form.owner"
							class="form-control"
							placeholder="Populated from selected patient"
							readonly
						/>
					</label>

					<EdgeLinkField
						v-model="form.branch"
						:selected-label="labels.branch"
						label="Service Branch"
						placeholder="Select the branch providing this service"
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
						placeholder="Search doctors available for this service branch"
						:searcher="searchPractitioner"
						:context="{ branch: form.branch }"
						:disabled="!form.branch"
						required
						@select="onPractitionerSelected"
						@clear="clearPractitioner"
						@search-error="handleFieldError"
					/>

					<label class="vetedge-appointment-flow-field">
						<span>Appointment Date/Time <b>*</b></span>
						<input v-model="form.appointment_datetime" type="datetime-local" class="form-control" required />
					</label>

					<label class="vetedge-appointment-flow-field">
						<span>Appointment Type</span>
						<select v-model="form.appointment_type" class="form-control">
							<option v-for="type in bootstrap.appointment_types" :key="type" :value="type">{{ type }}</option>
						</select>
					</label>
				</div>

				<label class="vetedge-appointment-flow-field vetedge-appointment-flow-field--wide">
					<span>Notes</span>
					<textarea v-model.trim="form.notes" class="form-control" rows="3" placeholder="Reason for visit or front-desk notes"></textarea>
				</label>
			</form>
		</div>

		<template #footer>
			<button type="button" class="edge-button" :disabled="saving" @click="close">Cancel</button>
			<button type="button" class="edge-button edge-button--primary" :disabled="saving || loading" @click="submitAppointment">
				{{ saving ? 'Creating...' : 'Create Appointment' }}
			</button>
		</template>
	</EdgeModal>
</template>

<script>
function emptyForm() {
	return {
		patient: "",
		owner: "",
		branch: "",
		practitioner: "",
		appointment_datetime: "",
		appointment_type: "Consultation",
		notes: "",
	};
}

function emptyLabels() {
	return { patient: "", owner: "", branch: "", practitioner: "" };
}

export default {
	name: "VetEdgeAppointmentFlow",
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
				can_create_appointment: false,
			},
			form: emptyForm(),
			labels: emptyLabels(),
		};
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
			if (this.saving) return;
			this.openState = false;
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
		searchPatient(query) {
			return this.searchLink("patient", query);
		},
		searchBranch(query) {
			return this.searchLink("branch", query);
		},
		searchPractitioner(query) {
			return this.searchLink("practitioner", query, { branch: this.form.branch });
		},
		onPatientSelected(option) {
			const raw = option?.raw || {};
			this.form.patient = option.value;
			this.labels.patient = option.label;
			this.form.owner = raw.primary_owner || option.owner || "";
			this.labels.owner = option.owner_label || raw.primary_owner || option.owner || "";
		},
		clearPatient() {
			this.form.patient = "";
			this.labels.patient = "";
			this.form.owner = "";
			this.labels.owner = "";
		},
		onBranchSelected(option) {
			this.form.branch = option.value;
			this.labels.branch = option.label;
			this.clearPractitioner();
		},
		clearBranch() {
			this.form.branch = "";
			this.labels.branch = "";
			this.clearPractitioner();
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
		async submitAppointment() {
			this.error = "";
			if (!this.bootstrap.can_create_appointment) {
				this.error = __("You do not have permission to create Veterinary Appointments.");
				return;
			}
			if (!this.form.patient || !this.form.branch || !this.form.practitioner || !this.form.appointment_datetime) {
				this.error = __("Patient, Service Branch, Practitioner and Appointment Date/Time are required.");
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
.vetedge-appointment-flow-form {
	display: grid;
	gap: 1rem;
}

.vetedge-appointment-flow-grid {
	display: grid;
	gap: .9rem;
	grid-template-columns: repeat(2, minmax(0, 1fr));
}

.vetedge-appointment-flow-field {
	display: grid;
	gap: .35rem;
	min-width: 0;
}

.vetedge-appointment-flow-field > span {
	color: var(--edge-color-ink-700, #415469);
	font-size: .75rem;
	font-weight: 700;
}

.vetedge-appointment-flow-field--wide {
	grid-column: 1 / -1;
}

.vetedge-appointment-flow-error {
	background: color-mix(in srgb, var(--edge-color-danger, #c53a3a) 10%, white);
	border: 1px solid color-mix(in srgb, var(--edge-color-danger, #c53a3a) 25%, white);
	border-radius: .7rem;
	color: var(--edge-color-danger, #a92f2f);
	font-size: .8rem;
	margin-bottom: 1rem;
	padding: .75rem .85rem;
}

.vetedge-appointment-flow-state {
	color: var(--edge-color-ink-500, #6b7d90);
	padding: 2rem;
	text-align: center;
}

@media (max-width: 47.99rem) {
	.vetedge-appointment-flow-grid {
		grid-template-columns: minmax(0, 1fr);
	}
}
</style>
